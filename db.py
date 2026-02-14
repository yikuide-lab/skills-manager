"""
SQLite storage backend for Skills Manager.
Replaces manifest.json, scan_results.json, and registry.json with a single DB.
Provides paginated queries for GUI performance.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "skills.db"

_conn: Optional[sqlite3.Connection] = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _init_tables(_conn)
    return _conn


def _init_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version TEXT DEFAULT '',
            author TEXT DEFAULT '',
            description TEXT DEFAULT '',
            category TEXT DEFAULT '',
            repo TEXT DEFAULT '',
            url TEXT DEFAULT '',
            size TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            extra TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS installed (
            skill_id TEXT PRIMARY KEY,
            name TEXT DEFAULT '',
            version TEXT DEFAULT '',
            author TEXT DEFAULT '',
            category TEXT DEFAULT '',
            repo TEXT DEFAULT '',
            installed_path TEXT DEFAULT '',
            installed_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS scan_results (
            skill_id TEXT PRIMARY KEY,
            severity TEXT DEFAULT 'NONE',
            findings_count INTEGER DEFAULT 0,
            categories TEXT DEFAULT '[]',
            findings TEXT DEFAULT '[]',
            scanned_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS sources (
            repo TEXT PRIMARY KEY,
            name TEXT DEFAULT '',
            url TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category);
        CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);
        CREATE INDEX IF NOT EXISTS idx_scan_severity ON scan_results(severity);
    """)


# ── Skills (registry) ─────────────────────────────────────────

def upsert_skills(skills: list[dict]):
    conn = get_conn()
    conn.executemany("""
        INSERT OR REPLACE INTO skills (id, name, version, author, description,
            category, repo, url, size, tags, extra)
        VALUES (:id, :name, :version, :author, :description,
            :category, :repo, :url, :size, :tags, :extra)
    """, [
        {
            "id": s["id"], "name": s.get("name", ""), "version": s.get("version", ""),
            "author": s.get("author", ""), "description": s.get("description", ""),
            "category": s.get("category", ""), "repo": s.get("repo", ""),
            "url": s.get("url", ""), "size": s.get("size", ""),
            "tags": json.dumps(s.get("tags", [])),
            "extra": json.dumps({k: v for k, v in s.items()
                                 if k not in ("id","name","version","author","description",
                                              "category","repo","url","size","tags")}),
        }
        for s in skills if s.get("id")
    ])
    conn.commit()


def _row_to_skill(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags", "[]"))
    extra = json.loads(d.pop("extra", "{}"))
    d.update(extra)
    return d


def query_skills(query: str = "", category: str = "", filter_type: str = "all",
                 sort: str = "name", offset: int = 0, limit: int = 50) -> tuple[list[dict], int]:
    """Paginated skill query. Returns (skills, total_count)."""
    conn = get_conn()

    where = []
    params = {}

    if query:
        tokens = query.lower().split()
        for i, t in enumerate(tokens):
            k = f"q{i}"
            where.append(f"(LOWER(s.name) LIKE :{k} OR LOWER(s.description) LIKE :{k} "
                         f"OR LOWER(s.tags) LIKE :{k})")
            params[k] = f"%{t}%"

    if category:
        where.append("s.category = :cat")
        params["cat"] = category

    if filter_type == "installed":
        where.append("i.skill_id IS NOT NULL")
    elif filter_type == "available":
        where.append("i.skill_id IS NULL")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    # Sort
    order_map = {
        "name": "s.name ASC",
        "category": "s.category ASC, s.name ASC",
        "risk": "CASE COALESCE(sc.severity,'NONE') "
                "WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 "
                "WHEN 'LOW' THEN 2 ELSE 3 END ASC, "
                "COALESCE(sc.findings_count,0) DESC, s.name ASC",
    }
    order_sql = order_map.get(sort, "s.name ASC")

    base_sql = f"""
        FROM skills s
        LEFT JOIN installed i ON s.id = i.skill_id
        LEFT JOIN scan_results sc ON s.id = sc.skill_id
        {where_sql}
    """

    # Count
    total = conn.execute(f"SELECT COUNT(*) {base_sql}", params).fetchone()[0]

    # Fetch page
    rows = conn.execute(f"""
        SELECT s.*, i.skill_id AS _installed, i.version AS _inst_version,
               sc.severity AS _scan_severity, sc.findings_count AS _scan_findings,
               sc.scanned_at AS _scan_time, sc.categories AS _scan_cats,
               sc.findings AS _scan_details
        {base_sql}
        ORDER BY {order_sql}
        LIMIT :limit OFFSET :offset
    """, {**params, "limit": limit, "offset": offset}).fetchall()

    skills = []
    for row in rows:
        s = _row_to_skill(row)
        # Attach install/scan info
        s["_installed"] = row["_installed"] is not None
        s["_inst_version"] = row["_inst_version"] or ""
        s["_scan"] = None
        if row["_scan_severity"]:
            s["_scan"] = {
                "severity": row["_scan_severity"],
                "findings_count": row["_scan_findings"] or 0,
                "categories": json.loads(row["_scan_cats"] or "[]"),
                "timestamp": row["_scan_time"] or "",
                "findings": json.loads(row["_scan_details"] or "[]"),
            }
        skills.append(s)

    return skills, total


def get_categories() -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT category FROM skills WHERE category != '' ORDER BY category"
    ).fetchall()
    return [r[0] for r in rows]


def get_stats() -> dict:
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
    installed = conn.execute("SELECT COUNT(*) FROM installed").fetchone()[0]
    scanned = conn.execute("SELECT COUNT(*) FROM scan_results").fetchone()[0]
    high = conn.execute(
        "SELECT COUNT(*) FROM scan_results WHERE severity='HIGH'"
    ).fetchone()[0]
    return {"total": total, "installed": installed, "scanned": scanned, "high_risk": high}


# ── Installed ──────────────────────────────────────────────────

def mark_installed(skill_id: str, info: dict):
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO installed
            (skill_id, name, version, author, category, repo, installed_path, installed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (skill_id, info.get("name",""), info.get("version",""),
          info.get("author",""), info.get("category",""), info.get("repo",""),
          info.get("installed_path",""), time.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()


def mark_uninstalled(skill_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM installed WHERE skill_id=?", (skill_id,))
    conn.execute("DELETE FROM scan_results WHERE skill_id=?", (skill_id,))
    conn.commit()


def is_installed(skill_id: str) -> bool:
    conn = get_conn()
    return conn.execute(
        "SELECT 1 FROM installed WHERE skill_id=?", (skill_id,)
    ).fetchone() is not None


def get_installed_version(skill_id: str) -> str:
    conn = get_conn()
    row = conn.execute(
        "SELECT version FROM installed WHERE skill_id=?", (skill_id,)
    ).fetchone()
    return row[0] if row else ""


def get_all_installed() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM installed").fetchall()
    return {r["skill_id"]: dict(r) for r in rows}


# ── Scan Results ───────────────────────────────────────────────

def save_scan_result(skill_id: str, result: dict):
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO scan_results
            (skill_id, severity, findings_count, categories, findings, scanned_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (skill_id, result.get("severity","NONE"), result.get("findings_count",0),
          json.dumps(result.get("categories",[])),
          json.dumps(result.get("findings",[])),
          result.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S"))))
    conn.commit()


def get_scan_result(skill_id: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM scan_results WHERE skill_id=?", (skill_id,)
    ).fetchone()
    if not row:
        return None
    return {
        "severity": row["severity"],
        "findings_count": row["findings_count"],
        "categories": json.loads(row["categories"]),
        "findings": json.loads(row["findings"]),
        "timestamp": row["scanned_at"],
    }


# ── Sources ────────────────────────────────────────────────────

def get_sources() -> list[dict]:
    conn = get_conn()
    return [dict(r) for r in conn.execute("SELECT * FROM sources").fetchall()]


def add_source(repo: str, name: str, url: str):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO sources (repo, name, url) VALUES (?,?,?)",
                 (repo, name, url))
    conn.commit()


def remove_source(repo: str):
    conn = get_conn()
    conn.execute("DELETE FROM sources WHERE repo=?", (repo,))
    conn.commit()


# ── Migration from JSON ───────────────────────────────────────

def migrate_from_json():
    """One-time migration from manifest.json + scan_results.json to SQLite."""
    from pathlib import Path
    base = Path(__file__).parent
    manifest_path = base / "installed_skills" / "manifest.json"
    scan_path = base / "installed_skills" / "scan_results.json"
    registry_path = base / "registry.json"

    conn = get_conn()

    # Migrate registry
    if registry_path.exists():
        try:
            data = json.loads(registry_path.read_text())
            skills = data.get("skills", [])
            if skills:
                upsert_skills(skills)
            sources = data.get("sources", [])
            for s in sources:
                add_source(s.get("repo",""), s.get("name",""), s.get("url",""))
        except Exception:
            pass

    # Migrate installed manifest
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text())
            for sid, info in data.get("installed", {}).items():
                mark_installed(sid, info)
        except Exception:
            pass

    # Migrate scan results
    if scan_path.exists():
        try:
            data = json.loads(scan_path.read_text())
            for sid, result in data.items():
                save_scan_result(sid, result)
        except Exception:
            pass

    conn.commit()
