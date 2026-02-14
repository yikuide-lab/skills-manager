"""
Skills Manager - Core logic for discovering, installing, and managing skills.
Supports local registry, remote registries, and GitHub API auto-discovery.
v4 — optimized: smarter cache, robust downloads, better search, temp cleanup.
"""

import copy
import json
import os
import shutil
import urllib.request
import urllib.error
import zipfile
import tempfile
import re
import time
from pathlib import Path
from typing import Optional
from logger import logger
from version_manager import backup_skill
import db as skilldb

# Directories
BASE_DIR = Path(__file__).parent
INSTALLED_DIR = BASE_DIR / "installed_skills"
INSTALLED_MANIFEST = INSTALLED_DIR / "manifest.json"
SCAN_RESULTS_FILE = INSTALLED_DIR / "scan_results.json"
LOCAL_REGISTRY = BASE_DIR / "registry.json"
DISCOVERY_CACHE = BASE_DIR / "discovery_cache.json"

REMOTE_REGISTRIES = [
    "https://raw.githubusercontent.com/skills-registry/index/main/registry.json",
]

GITHUB_DISCOVERY_QUERIES = [
    "awesome-agent-skills",
    "SKILL.md agent skills",
    "claude-skills collection",
    "agent-skills repository",
]

# Keywords that indicate a repo is actually skill-related
_RELEVANCE_KEYWORDS = {
    "skill", "skills", "agent", "agents", "plugin", "plugins",
    "claude", "codex", "copilot", "mcp", "llm", "prompt",
    "ai-agent", "agent-skill", "skill.md",
}

GITHUB_API = "https://api.github.com"
USER_AGENT = "SkillsManager/4.0"

# ── Proxy Configuration ────────────────────────────────────────

SETTINGS_FILE = BASE_DIR / "settings.json"
_opener: urllib.request.OpenerDirector | None = None


def _load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_settings(data: dict):
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(SETTINGS_FILE)


def get_proxy_config() -> dict:
    """Return {"enabled": bool, "http": str, "https": str}."""
    s = _load_settings()
    return s.get("proxy", {"enabled": False, "http": "", "https": ""})


def set_proxy_config(enabled: bool, http: str = "", https: str = ""):
    """Save proxy config and rebuild opener."""
    global _opener
    s = _load_settings()
    s["proxy"] = {"enabled": enabled, "http": http.strip(), "https": https.strip()}
    _save_settings(s)
    _opener = None  # force rebuild
    _ensure_opener()


def _ensure_opener():
    """Install a global urllib opener with proxy settings."""
    global _opener
    if _opener is not None:
        return
    cfg = get_proxy_config()
    if cfg.get("enabled") and (cfg.get("http") or cfg.get("https")):
        proxies = {}
        if cfg["http"]:
            proxies["http"] = cfg["http"]
        if cfg["https"]:
            proxies["https"] = cfg["https"]
        handler = urllib.request.ProxyHandler(proxies)
    else:
        handler = urllib.request.ProxyHandler({})  # no proxy / direct
    _opener = urllib.request.build_opener(handler)
    urllib.request.install_opener(_opener)


# Apply on import
_ensure_opener()


# ── Manifest Cache ─────────────────────────────────────────────

class _ManifestCache:
    """In-memory cache for the installed-skills manifest.
    
    Returns the raw cached dict for read-only lookups (get_readonly),
    or a deep copy for mutation (get). This avoids unnecessary copies
    on hot paths like is_installed().
    """

    def __init__(self):
        self._data: Optional[dict] = None
        self._mtime: float = 0.0

    def _refresh(self) -> dict:
        try:
            current_mtime = INSTALLED_MANIFEST.stat().st_mtime
        except FileNotFoundError:
            ensure_dirs()
            current_mtime = INSTALLED_MANIFEST.stat().st_mtime

        if self._data is None or current_mtime != self._mtime:
            self._data = json.loads(INSTALLED_MANIFEST.read_text())
            self._mtime = current_mtime
        return self._data

    def get(self) -> dict:
        """Return a deep copy (safe for mutation)."""
        return copy.deepcopy(self._refresh())

    def get_readonly(self) -> dict:
        """Return cached dict directly (DO NOT mutate)."""
        return self._refresh()

    def invalidate(self):
        self._data = None
        self._mtime = 0.0


_manifest_cache = _ManifestCache()


def ensure_dirs():
    INSTALLED_DIR.mkdir(parents=True, exist_ok=True)
    if not INSTALLED_MANIFEST.exists():
        INSTALLED_MANIFEST.write_text(json.dumps({"installed": {}}, indent=2))


def load_manifest(readonly: bool = False) -> dict:
    """Load manifest. Use readonly=True for lookups (no deep copy)."""
    ensure_dirs()
    return _manifest_cache.get_readonly() if readonly else _manifest_cache.get()


def save_manifest(manifest: dict):
    ensure_dirs()
    tmp = INSTALLED_MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2))
    tmp.replace(INSTALLED_MANIFEST)  # atomic on POSIX
    _manifest_cache.invalidate()


# ── Registry Loading ───────────────────────────────────────────

def _load_local_registry() -> dict:
    """Load local registry.json, returning empty structure on failure."""
    if LOCAL_REGISTRY.exists():
        try:
            return json.loads(LOCAL_REGISTRY.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Corrupt registry.json: {e}")
    return {"registry_version": "2.0.0", "sources": [], "skills": []}


def _save_local_registry(data: dict):
    """Atomically write registry.json."""
    tmp = LOCAL_REGISTRY.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(LOCAL_REGISTRY)


def fetch_registry(timeout: int = 10) -> list[dict]:
    skills = []
    for url in REMOTE_REGISTRIES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
                logger.info(f"Fetched registry from {url}")
                skills = data.get("skills", [])
                break
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            continue
    if not skills and LOCAL_REGISTRY.exists():
        logger.info("Using local registry fallback")
        data = _load_local_registry()
        skills = data.get("skills", [])
    if skills:
        skilldb.upsert_skills(skills)
    elif not skills:
        logger.error("No registry available")
    return skills


def get_registry_sources() -> list[dict]:
    return _load_local_registry().get("sources", [])


def get_all_categories(skills: list[dict]) -> list[str]:
    """Extract sorted unique categories from a skill list."""
    cats = sorted({s.get("category", "") for s in skills if s.get("category")})
    return cats


# ── Installed Skills (cached) ─────────────────────────────────

def get_installed_skills() -> dict:
    return load_manifest(readonly=True).get("installed", {})


def get_installed_snapshot() -> dict:
    """Return a snapshot dict for batch lookups (avoids repeated calls)."""
    return dict(get_installed_skills())


def is_installed(skill_id: str, _snapshot: Optional[dict] = None) -> bool:
    src = _snapshot if _snapshot is not None else get_installed_skills()
    return skill_id in src


def get_installed_version(skill_id: str, _snapshot: Optional[dict] = None) -> Optional[str]:
    src = _snapshot if _snapshot is not None else get_installed_skills()
    info = src.get(skill_id)
    return info.get("version") if info else None


def has_update(skill: dict, _snapshot: Optional[dict] = None) -> bool:
    ver = get_installed_version(skill["id"], _snapshot)
    if ver is None:
        return False
    return ver != skill.get("version")


# ── GitHub Auto-Discovery (with relevance filtering) ──────────

def _github_request(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github.v3+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _relevance_score(repo: dict) -> int:
    """Score how relevant a repo is to agent skills. Higher = more relevant."""
    score = 0
    text = " ".join([
        repo.get("name", ""),
        repo.get("description", ""),
        " ".join(repo.get("topics", [])),
    ]).lower()

    for kw in _RELEVANCE_KEYWORDS:
        if kw in text:
            score += 10

    # Bonus for repos with "skill" in the name
    if "skill" in repo.get("name", "").lower():
        score += 30

    # Bonus for topics
    for topic in repo.get("topics", []):
        if topic in _RELEVANCE_KEYWORDS:
            score += 15

    return score


def discover_github_repos(timeout: int = 10) -> list[dict]:
    """
    Search GitHub for new skill repositories.
    Filters by relevance to avoid noise from generic repos.
    """
    known_repos = {s["repo"].lower() for s in get_registry_sources()}
    discovered = {}

    for query in GITHUB_DISCOVERY_QUERIES:
        try:
            encoded_q = urllib.request.quote(query)
            url = (
                f"{GITHUB_API}/search/repositories"
                f"?q={encoded_q}+in:name,description,readme"
                f"&sort=stars&order=desc&per_page=15"
            )
            data = _github_request(url, timeout)
            for repo in data.get("items", []):
                full_name = repo["full_name"].lower()
                if full_name in known_repos or full_name in discovered:
                    continue

                entry = {
                    "repo": repo["full_name"],
                    "name": repo["name"],
                    "description": repo.get("description", ""),
                    "stars": repo.get("stargazers_count", 0),
                    "url": repo["html_url"],
                    "owner": repo["owner"]["login"],
                    "updated_at": repo.get("updated_at", ""),
                    "language": repo.get("language", ""),
                    "topics": repo.get("topics", []),
                }
                entry["_relevance"] = _relevance_score(entry)

                # Only include repos with some relevance
                if entry["_relevance"] >= 10:
                    discovered[full_name] = entry
        except Exception:
            continue

    # Sort by relevance first, then stars
    results = sorted(
        discovered.values(),
        key=lambda r: (r["_relevance"], r["stars"]),
        reverse=True,
    )

    try:
        DISCOVERY_CACHE.write_text(json.dumps({
            "discovered": results,
            "count": len(results),
            "cached_at": time.time(),
        }, indent=2))
    except Exception:
        pass

    return results


def get_cached_discoveries() -> list[dict]:
    if DISCOVERY_CACHE.exists():
        try:
            data = json.loads(DISCOVERY_CACHE.read_text())
            return data.get("discovered", [])
        except Exception:
            pass
    return []


# ── Source Management ──────────────────────────────────────────

def add_source_to_registry(repo: str, name: str, url: str):
    data = _load_local_registry()
    sources = data.get("sources", [])
    if not any(s.get("repo", "").lower() == repo.lower() for s in sources):
        sources.append({"name": name, "repo": repo, "url": url, "type": "github"})
        data["sources"] = sources
        _save_local_registry(data)


def remove_source_from_registry(repo: str) -> bool:
    """Remove a source repo. Returns True if removed."""
    data = _load_local_registry()
    sources = data.get("sources", [])
    new_sources = [s for s in sources if s.get("repo", "").lower() != repo.lower()]
    if len(new_sources) == len(sources):
        return False
    data["sources"] = new_sources
    _save_local_registry(data)
    return True


def fetch_skills_from_github_repo(repo: str, timeout: int = 10) -> list[dict]:
    skills = []
    try:
        url = f"{GITHUB_API}/repos/{repo}/git/trees/main?recursive=1"
        data = _github_request(url, timeout)
        tree = data.get("tree", [])

        skill_dirs = set()
        for item in tree:
            path = item.get("path", "")
            if path.endswith("SKILL.md") or path.endswith("skill.md"):
                parent = str(Path(path).parent)
                if parent != ".":
                    skill_dirs.add(parent)

        owner = repo.split("/")[0]
        for skill_dir in sorted(skill_dirs):
            skill_name = Path(skill_dir).name
            skill_id = f"{owner}-{skill_name}".lower()
            skill_id = re.sub(r"[^a-z0-9\-]", "-", skill_id)
            skills.append({
                "id": skill_id,
                "name": skill_name.replace("-", " ").replace("_", " ").title(),
                "version": "latest",
                "author": owner,
                "description": f"Skill from {repo}: {skill_name}",
                "category": "Community",
                "repo": repo,
                "url": f"https://github.com/{repo}/tree/main/{skill_dir}",
                "size": "~10 KB",
                "tags": ["community", owner.lower(), skill_name.lower()],
            })
    except Exception as e:
        logger.warning(f"Failed to fetch skills from {repo}: {e}")
    return skills


def merge_discovered_skills(new_skills: list[dict]) -> int:
    data = _load_local_registry()
    existing_ids = {s["id"] for s in data.get("skills", [])}
    added = 0
    for skill in new_skills:
        if skill["id"] not in existing_ids:
            data["skills"].append(skill)
            existing_ids.add(skill["id"])
            added += 1
    if added > 0:
        _save_local_registry(data)
    return added


# ── Download Helper ────────────────────────────────────────────

def _download_and_extract(download_url: str, dest_dir: Path, progress_cb=None,
                          progress_pct: int = 50, msg: str = "Extracting...") -> bool:
    """Download a zip from URL and extract to dest_dir. Returns True on success."""
    tmp_path = None
    try:
        req = urllib.request.Request(download_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            zip_data = resp.read()
        if progress_cb:
            progress_cb(progress_pct, msg)
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(zip_data)
            tmp_path = tmp.name
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extractall(dest_dir)
        return True
    except (urllib.error.URLError, zipfile.BadZipFile, OSError) as e:
        logger.warning(f"Download failed from {download_url}: {e}")
        return False
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ── Install / Uninstall ───────────────────────────────────────

def install_skill(skill: dict, progress_cb=None) -> tuple[bool, str]:
    ensure_dirs()
    skill_id = skill["id"]
    skill_dir = INSTALLED_DIR / skill_id
    url = skill.get("url", "")
    repo = skill.get("repo", "")

def install_skill(skill: dict, progress_cb=None) -> tuple[bool, str]:
    ensure_dirs()
    skill_id = skill["id"]
    skill_dir = INSTALLED_DIR / skill_id
    url = skill.get("url", "")
    repo = skill.get("repo", "")

    try:
        # Backup if updating existing skill
        if skill_dir.exists():
            backup_skill(skill_id, skill_dir)

        if progress_cb:
            progress_cb(10, f"Downloading {skill['name']}...")

        downloaded = False

        if repo:
            zip_url = f"https://github.com/{repo}/archive/refs/heads/main.zip"
            downloaded = _download_and_extract(
                zip_url, skill_dir, progress_cb, 50, "Extracting from GitHub...")

        if url and not downloaded:
            downloaded = _download_and_extract(
                url, skill_dir, progress_cb, 50, "Extracting...")

        if not downloaded:
            logger.warning(f"No downloadable source for {skill_id}, creating placeholder")
            if skill_dir.exists():
                shutil.rmtree(skill_dir)
            skill_dir.mkdir(parents=True, exist_ok=True)
            meta = {
                "id": skill_id, "name": skill["name"],
                "version": skill["version"],
                "description": skill.get("description", ""),
                "author": skill.get("author", ""), "repo": repo, "url": url,
            }
            (skill_dir / "skill.json").write_text(json.dumps(meta, indent=2))
            (skill_dir / "SKILL.md").write_text(
                f"# {skill['name']}\n\n{skill.get('description', '')}\n\nSource: {url or repo}\n"
            )

        if progress_cb:
            progress_cb(80, "Updating manifest...")

        manifest = load_manifest()
        manifest["installed"][skill_id] = {
            "name": skill["name"], "version": skill["version"],
            "author": skill.get("author", ""), "category": skill.get("category", ""),
            "repo": repo, "installed_path": str(skill_dir),
        }
        save_manifest(manifest)

        skilldb.mark_installed(skill_id, {
            "name": skill["name"], "version": skill["version"],
            "author": skill.get("author", ""), "category": skill.get("category", ""),
            "repo": repo, "installed_path": str(skill_dir),
        })

        if progress_cb:
            progress_cb(100, "Done!")
        logger.info(f"Installed {skill['name']} v{skill['version']} ({skill_id})")
        return True, f"Successfully installed {skill['name']} v{skill['version']}"
    except Exception as e:
        logger.error(f"Install failed for {skill_id}: {e}")
        return False, f"Installation failed: {e}"


def uninstall_skill(skill_id: str) -> tuple[bool, str]:
    if not is_installed(skill_id):
        logger.warning(f"Uninstall failed: {skill_id} not installed")
        return False, f"Skill '{skill_id}' is not installed."
    skill_dir = INSTALLED_DIR / skill_id
    
    # Backup before uninstall
    if skill_dir.exists():
        backup_skill(skill_id, skill_dir)
        shutil.rmtree(skill_dir)
    
    manifest = load_manifest()
    name = manifest["installed"].get(skill_id, {}).get("name", skill_id)
    manifest["installed"].pop(skill_id, None)
    save_manifest(manifest)

    # Clean up scan result
    scan_data = _load_scan_results()
    if skill_id in scan_data:
        del scan_data[skill_id]
        _save_scan_results(scan_data)

    skilldb.mark_uninstalled(skill_id)

    logger.info(f"Uninstalled {name} ({skill_id})")
    return True, f"Successfully uninstalled {name}"


def search_skills(skills: list[dict], query: str) -> list[dict]:
    if not query.strip():
        return skills
    q = query.lower()
    tokens = q.split()

    def score_skill(s: dict) -> int:
        """Score a skill against query. 0 = no match."""
        searchable = " ".join([
            s.get("name", ""), s.get("description", ""),
            s.get("category", ""), s.get("author", ""),
            s.get("repo", ""), " ".join(s.get("tags", [])),
        ]).lower()

        # Exact full query match
        if q in searchable:
            return 100

        # All tokens present (AND match)
        if all(t in searchable for t in tokens):
            return 80

        # Fuzzy: sequential character match
        text_idx = 0
        matched = 0
        for char in q:
            while text_idx < len(searchable) and searchable[text_idx] != char:
                text_idx += 1
            if text_idx >= len(searchable):
                return 0
            matched += 1
            text_idx += 1
        return matched * 10

    results = []
    for s in skills:
        sc = score_skill(s)
        if sc > 0:
            results.append((sc, s))

    results.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in results]


# ── Security Scan Integration ──────────────────────────────────

def _load_scan_results() -> dict:
    """Load persisted scan results {skill_id: {severity, findings_count, categories, timestamp}}."""
    try:
        return json.loads(SCAN_RESULTS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_scan_results(data: dict):
    tmp = SCAN_RESULTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(SCAN_RESULTS_FILE)


def _find_skill_dir(skill_id: str) -> Optional[Path]:
    """Find the actual skill directory (containing SKILL.md) for an installed skill."""
    base = INSTALLED_DIR / skill_id
    if not base.is_dir():
        return None
    # Check nested structure first (most common)
    for md in base.rglob("SKILL.md"):
        return md.parent
    return base


def scan_single_skill(skill_id: str) -> Optional[dict]:
    """Scan one installed skill, persist result, return summary dict."""
    skill_dir = _find_skill_dir(skill_id)
    if not skill_dir:
        return None

    from skillscan import scan_skill as _scan
    result = _scan(skill_dir)

    summary = {
        "severity": result.max_severity,
        "findings_count": len(result.findings),
        "categories": sorted(result.categories),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "findings": [
            {"id": f.pattern_id, "name": f.name, "severity": f.severity,
             "file": f.file, "line": f.line, "match": f.match}
            for f in result.findings
        ],
    }

    all_results = _load_scan_results()
    all_results[skill_id] = summary
    _save_scan_results(all_results)
    skilldb.save_scan_result(skill_id, summary)
    return summary


def scan_remote_skill(skill: dict) -> Optional[dict]:
    """Download an uninstalled skill to a temp dir, scan it, persist result, clean up."""
    repo = skill.get("repo", "")
    url = skill.get("url", "")
    if not repo and not url:
        return None

    tmp_dir = Path(tempfile.mkdtemp(prefix="skillscan_"))
    try:
        downloaded = False
        if repo:
            zip_url = f"https://github.com/{repo}/archive/refs/heads/main.zip"
            downloaded = _download_and_extract(zip_url, tmp_dir)
        if url and not downloaded:
            downloaded = _download_and_extract(url, tmp_dir)
        if not downloaded:
            return None

        # Find SKILL.md inside extracted content
        scan_dir = tmp_dir
        for md in tmp_dir.rglob("SKILL.md"):
            scan_dir = md.parent
            break

        from skillscan import scan_skill as _scan
        result = _scan(scan_dir)

        summary = {
            "severity": result.max_severity,
            "findings_count": len(result.findings),
            "categories": sorted(result.categories),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "findings": [
                {"id": f.pattern_id, "name": f.name, "severity": f.severity,
                 "file": f.file, "line": f.line, "match": f.match}
                for f in result.findings
            ],
        }

        skill_id = skill["id"]
        all_results = _load_scan_results()
        all_results[skill_id] = summary
        _save_scan_results(all_results)
        skilldb.save_scan_result(skill_id, summary)
        return summary
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def scan_all_installed(progress_cb=None) -> dict:
    """Scan all installed skills. Returns full scan results dict."""
    installed = get_installed_snapshot()
    total = len(installed)
    all_results = {}

    for i, skill_id in enumerate(installed):
        if progress_cb:
            progress_cb(i, total, skill_id)
        summary = scan_single_skill(skill_id)
        if summary:
            all_results[skill_id] = summary

    if progress_cb:
        progress_cb(total, total, "")
    return all_results


def get_scan_results() -> dict:
    """Get all persisted scan results."""
    return _load_scan_results()


def get_skill_scan(skill_id: str) -> Optional[dict]:
    """Get persisted scan result for a single skill."""
    return _load_scan_results().get(skill_id)
