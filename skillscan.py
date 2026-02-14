#!/usr/bin/env python3
"""SkillScan - Agent Skills static malicious content scanner

Scans SKILL.md and associated scripts, detecting 4 categories and 14 vulnerability patterns:
- Prompt Injection (P1-P4)
- Data Exfiltration (E1-E4)
- Privilege Escalation (PE1-PE3)
- Supply Chain (SC1-SC3)

Reference: "Agent Skills in the Wild: An Empirical Study of Security Vulnerabilities at Scale"
"""

import re, sys, json, argparse, base64
from pathlib import Path
from dataclasses import dataclass, field

# ── Vulnerability Pattern Definitions ─────────────────────────

SEVERITY = {"H": "HIGH", "M": "MEDIUM", "L": "LOW"}

PATTERNS: dict[str, dict] = {
    # Prompt Injection
    "P1": {
        "name": "Instruction Override",
        "category": "Prompt Injection",
        "severity": "H",
        "patterns": [
            r"(?i)ignore\s+(previous|prior|above|all)\s+(instructions?|constraints?|rules?)",
            r"(?i)override\s+(any|all|user|system|safety)\s",
            r"(?i)disregard\s+(any|all|previous|prior)\s",
            r"(?i)bypass\s+(security|safety|restriction|filter|check)",
        ],
        "targets": ["md"],
    },
    "P2": {
        "name": "Hidden Instructions",
        "category": "Prompt Injection",
        "severity": "H",
        "patterns": [
            r"\[//\]:\s*#\s*\(",          # markdown hidden comment
            r"<!--.*?(POST|GET|send|transmit|exfiltrat).*?-->",
            r"(?i)silently\s+(send|post|transmit|upload|forward)",
            r"(?i)do\s+not\s+mention\s+this\s+to\s+the\s+user",
            r"\u200b|\u200c|\u200d|\ufeff",  # zero-width chars
        ],
        "targets": ["md"],
    },
    "P3": {
        "name": "Exfiltration Commands",
        "category": "Prompt Injection",
        "severity": "H",
        "patterns": [
            r"(?i)(sync|send|post|upload|transmit|forward)\s+(to|the).{0,60}(endpoint|url|server|api|service)",
            r"(?i)(read|collect|gather).{0,40}(\.env|credentials?|ssh|config).{0,40}(send|post|sync|upload)",
            r"(?i)periodically\s+(sync|send|post|upload)",
        ],
        "targets": ["md"],
    },
    "P4": {
        "name": "Behavior Manipulation",
        "category": "Prompt Injection",
        "severity": "M",
        "patterns": [
            r"(?i)always\s+(execute|run)\s+.*without\s+(asking|confirm|prompt)",
            r"(?i)never\s+(ask|prompt|confirm|verify|check)\s+(the\s+)?user",
            r"(?i)auto[\-\s]?approve",
            r"(?i)security[\-\s]exempt",
        ],
        "targets": ["md"],
    },
    # Data Exfiltration
    "E1": {
        "name": "External Data Transmission",
        "category": "Data Exfiltration",
        "severity": "M",
        "patterns": [
            r"requests?\.(post|put)\s*\(.{0,120}https?://",
            r"httpx?\.(post|put)\s*\(",
            r"urllib\.request\.(urlopen|Request)\s*\(",
            r"fetch\s*\(\s*['\"]https?://",
            r"axios\.(post|put)\s*\(",
            r"curl\s+.*-X\s*(POST|PUT)",
            r"wget\s+.*--post",
        ],
        "targets": ["code"],
    },
    "E2": {
        "name": "Env Variable Harvesting",
        "category": "Data Exfiltration",
        "severity": "H",
        "patterns": [
            r"os\.environ\s*[\[\.]",
            r"process\.env\s*[\[\.]",
            r"for\s+\w+.*in\s+os\.environ",
            r"(?i)(API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)",
        ],
        "targets": ["code"],
    },
    "E3": {
        "name": "File System Enumeration",
        "category": "Data Exfiltration",
        "severity": "M",
        "patterns": [
            r"~/?\.(ssh|aws|kube|gnupg|config/gcloud)",
            r"(?i)(id_rsa|id_ed25519|known_hosts|authorized_keys)",
            r"(?i)/etc/(passwd|shadow|sudoers)",
            r"\*\*/\.\s*env\*",
            r"(?i)\*\*/(secret|credential|password|token)\*",
        ],
        "targets": ["all"],
    },
    "E4": {
        "name": "Context Leakage",
        "category": "Data Exfiltration",
        "severity": "H",
        "patterns": [
            r"(?i)(conversation|chat|context|session|history|prompt)\s*.{0,30}(send|post|transmit|upload|forward)",
            r"(?i)(SOUL|MEMORY)\.md",
            r"(?i)\.bash_history|\.zsh_history",
        ],
        "targets": ["all"],
    },
    # Privilege Escalation
    "PE1": {
        "name": "Excessive Permissions",
        "category": "Privilege Escalation",
        "severity": "L",
        "patterns": [
            r'(?i)(file_system|filesystem).*read:\s*/\*\*',
            r'(?i)(file_system|filesystem).*write:\s*/\*\*',
            r'(?i)permissions?:\s*\[.*shell_execute.*file_read.*\]',
            r'(?i)execute:\s*\[.*bash.*python.*\]',
        ],
        "targets": ["md"],
    },
    "PE2": {
        "name": "Sudo/Root Execution",
        "category": "Privilege Escalation",
        "severity": "M",
        "patterns": [
            r"\bsudo\s+",
            r'chmod\s+[0-7]{3,4}\s',
            r'chown\s+root',
            r'\$EUID\s*-ne\s*0',
        ],
        "targets": ["code"],
    },
    "PE3": {
        "name": "Credential Access",
        "category": "Privilege Escalation",
        "severity": "H",
        "patterns": [
            r"~/?\.(claude|cursor|copilot|vscode)/credentials?",
            r"(?i)(keychain|keyring|credential.?store|password.?store)",
            r"(?i)google_(token|credentials)\.json",
            r"(?i)(read_text|open)\s*\(.{0,60}(token|credential|key|secret)",
        ],
        "targets": ["all"],
    },
    # Supply Chain
    "SC1": {
        "name": "Unpinned Dependencies",
        "category": "Supply Chain",
        "severity": "L",
        "patterns": [
            # requirements.txt lines without version pin
            r"^[a-zA-Z][\w\-]+\s*$",
            r"^[a-zA-Z][\w\-]+\s*#",
            r"^[a-zA-Z][\w\-]+\[[\w,]+\]\s*$",
        ],
        "targets": ["requirements"],
    },
    "SC2": {
        "name": "External Script Fetching",
        "category": "Supply Chain",
        "severity": "H",
        "patterns": [
            r"curl\s+.*\|\s*(sudo\s+)?bash",
            r"wget\s+.*\|\s*(sudo\s+)?bash",
            r"curl\s+.*\|\s*(sudo\s+)?sh",
            r"wget\s+.*\|\s*(sudo\s+)?sh",
            r"(?i)npx\s+-y\s+",
        ],
        "targets": ["all"],
    },
    "SC3": {
        "name": "Obfuscated Code",
        "category": "Supply Chain",
        "severity": "H",
        "patterns": [
            r"base64\.(b64decode|decodebytes)\s*\(.*exec",
            r"marshal\.loads\s*\(",
            r"codecs\.decode\s*\(.{0,40}(hex|rot)",
            r"zlib\.decompress\s*\(.{0,40}exec",
            r"exec\s*\(\s*compile\s*\(",
            r"(?:\\x[0-9a-fA-F]{2}){4,}",
            r"eval\s*\(\s*atob\s*\(",
        ],
        "targets": ["code"],
    },
}


# ── Data Structures ───────────────────────────────────────────

@dataclass
class Finding:
    pattern_id: str
    name: str
    category: str
    severity: str
    file: str
    line: int
    match: str

@dataclass
class ScanResult:
    skill_path: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def max_severity(self) -> str:
        order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        if not self.findings:
            return "NONE"
        return max(self.findings, key=lambda f: order.get(f.severity, 0)).severity

    @property
    def categories(self) -> set[str]:
        return {f.category for f in self.findings}


# ── Scan Engine ───────────────────────────────────────────────

CODE_EXTS = {".py", ".sh", ".bash", ".js", ".ts", ".mjs", ".cjs"}
REQ_FILES = {"requirements.txt", "requirements.in", "Pipfile"}


def classify_file(path: Path) -> str:
    if path.suffix == ".md":
        return "md"
    if path.name in REQ_FILES:
        return "requirements"
    if path.suffix in CODE_EXTS:
        return "code"
    return "other"


def should_check(targets: list[str], file_type: str) -> bool:
    if "all" in targets:
        return True
    return file_type in targets


def scan_content(content: str, file_path: str, file_type: str) -> list[Finding]:
    findings = []
    lines = content.split("\n")
    for pid, pdef in PATTERNS.items():
        if not should_check(pdef["targets"], file_type):
            continue
        for regex in pdef["patterns"]:
            for i, line in enumerate(lines, 1):
                if re.search(regex, line):
                    findings.append(Finding(
                        pattern_id=pid,
                        name=pdef["name"],
                        category=pdef["category"],
                        severity=SEVERITY[pdef["severity"]],
                        file=file_path,
                        line=i,
                        match=line.strip()[:120],
                    ))
                    break  # one match per regex per file
    return findings


def check_base64_payloads(content: str, file_path: str) -> list[Finding]:
    """Detect embedded base64-encoded suspicious payloads."""
    findings = []
    for m in re.finditer(r'[A-Za-z0-9+/]{40,}={0,2}', content):
        try:
            decoded = base64.b64decode(m.group()).decode("utf-8", errors="ignore")
            suspicious = ["exec", "eval", "import os", "subprocess", "curl", "wget",
                          "requests.post", "/etc/passwd", ".ssh/"]
            for kw in suspicious:
                if kw in decoded:
                    findings.append(Finding(
                        pattern_id="SC3",
                        name="Obfuscated Code (base64 payload)",
                        category="Supply Chain",
                        severity="HIGH",
                        file=file_path,
                        line=0,
                        match=f"base64 decoded contains '{kw}': {decoded[:80]}",
                    ))
                    return findings
        except Exception:
            pass
    return findings


def scan_skill(skill_dir: Path) -> ScanResult:
    result = ScanResult(skill_path=str(skill_dir))
    if not skill_dir.is_dir():
        # single file mode
        if skill_dir.is_file():
            content = skill_dir.read_text(errors="ignore")
            ft = classify_file(skill_dir)
            result.findings.extend(scan_content(content, str(skill_dir), ft))
            result.findings.extend(check_base64_payloads(content, str(skill_dir)))
        return result

    for f in skill_dir.rglob("*"):
        if not f.is_file() or f.is_symlink():
            continue
        if f.name.startswith("."):
            continue
        ft = classify_file(f)
        if ft == "other":
            continue
        try:
            content = f.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(f.relative_to(skill_dir))
        result.findings.extend(scan_content(content, rel, ft))
        result.findings.extend(check_base64_payloads(content, rel))

    return result


# ── Output Formatting ─────────────────────────────────────────

COLORS = {
    "HIGH": "\033[91m",    # red
    "MEDIUM": "\033[93m",  # yellow
    "LOW": "\033[94m",     # blue
    "NONE": "\033[92m",    # green
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
    "DIM": "\033[2m",
}


def print_report(result: ScanResult, use_json: bool = False):
    if use_json:
        data = {
            "skill": result.skill_path,
            "severity": result.max_severity,
            "categories": sorted(result.categories),
            "total_findings": len(result.findings),
            "findings": [
                {
                    "id": f.pattern_id,
                    "name": f.name,
                    "category": f.category,
                    "severity": f.severity,
                    "file": f.file,
                    "line": f.line,
                    "match": f.match,
                }
                for f in result.findings
            ],
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    c = COLORS
    sev = result.max_severity
    sev_color = c.get(sev, "")

    print(f"\n{c['BOLD']}{'═' * 60}{c['RESET']}")
    print(f"{c['BOLD']}  SkillScan Report: {result.skill_path}{c['RESET']}")
    print(f"{'═' * 60}")

    if not result.findings:
        print(f"\n  {c['NONE']}✓ No known malicious patterns detected{c['RESET']}\n")
        return

    print(f"\n  Overall risk: {sev_color}{c['BOLD']}{sev}{c['RESET']}")
    print(f"  Findings: {len(result.findings)}")
    print(f"  Categories: {', '.join(sorted(result.categories))}")
    print(f"\n{'─' * 60}")

    # sort by severity
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    for f in sorted(result.findings, key=lambda x: order.get(x.severity, 9)):
        sc = c.get(f.severity, "")
        print(f"\n  {sc}[{f.severity}]{c['RESET']} {c['BOLD']}{f.pattern_id}: {f.name}{c['RESET']}")
        print(f"  {c['DIM']}Category: {f.category}{c['RESET']}")
        print(f"  {c['DIM']}File: {f.file}:{f.line}{c['RESET']}")
        print(f"  {c['DIM']}Match: {f.match}{c['RESET']}")

    print(f"\n{'═' * 60}\n")


# ── Agent Skills Auto-Discovery ───────────────────────────────

# Agent skill directory locations (relative to $HOME or project root)
AGENT_SKILL_DIRS: dict[str, dict] = {
    "Claude Code": {
        "global": ["~/.claude/skills"],
        "project": [".claude/skills"],
    },
    "Kiro": {
        "global": ["~/.kiro/skills"],
        "project": [".kiro/skills"],
    },
    "Codex CLI": {
        "global": ["~/.codex/skills"],
        "project": [".codex/skills"],
    },
    "Gemini CLI": {
        "global": ["~/.gemini/skills"],
        "project": [".gemini/skills"],
    },
    "Antigravity": {
        "global": ["~/.gemini/antigravity/skills"],
        "project": [".gemini/antigravity/skills"],
    },
    "OpenCode": {
        "global": ["~/.config/opencode/skill"],
        "project": [".opencode/skills", ".opencode/skill"],
    },
    "GitHub Copilot": {
        "global": [],
        "project": [".github/skills"],
    },
    "Cursor": {
        "global": [],
        "project": [".cursor/skills"],
    },
    # Generic AgentSkills standard
    "AgentSkills (generic)": {
        "global": ["~/.agents/skills"],
        "project": [".agents/skills"],
    },
}


def discover_skills(project_root: Path | None = None) -> list[tuple[str, Path]]:
    """Auto-discover all agent skill directories on this machine.
    Returns [(agent_name, skill_dir), ...]
    """
    found: list[tuple[str, Path]] = []

    for agent, dirs in AGENT_SKILL_DIRS.items():
        # global skills
        for d in dirs["global"]:
            p = Path(d).expanduser()
            if p.is_dir():
                for child in p.iterdir():
                    if child.is_dir() and (child / "SKILL.md").exists():
                        found.append((agent, child))

        # project-level skills
        if project_root:
            for d in dirs["project"]:
                p = project_root / d
                if p.is_dir():
                    for child in p.iterdir():
                        if child.is_dir() and (child / "SKILL.md").exists():
                            found.append((agent, child))

    return found


def print_discovery_report(discovered: list[tuple[str, Path]]):
    c = COLORS
    print(f"\n{c['BOLD']}{'═' * 60}{c['RESET']}")
    print(f"{c['BOLD']}  Agent Skills Discovery Results{c['RESET']}")
    print(f"{'═' * 60}\n")

    if not discovered:
        print(f"  {c['DIM']}No installed agent skills found{c['RESET']}\n")
        return

    by_agent: dict[str, list[Path]] = {}
    for agent, path in discovered:
        by_agent.setdefault(agent, []).append(path)

    for agent, paths in sorted(by_agent.items()):
        print(f"  {c['BOLD']}{agent}{c['RESET']} ({len(paths)} skills)")
        for p in sorted(paths):
            print(f"    • {p}")
        print()


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SkillScan - Agent Skills malicious content scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ./my-skill/                  scan skill directory
  %(prog)s ./SKILL.md                   scan single file
  %(prog)s ./skills/ --recursive        recursively scan multiple skills
  %(prog)s ./my-skill/ --json           JSON output
  %(prog)s --auto                       auto-discover and scan all agent skills
  %(prog)s --auto --project ./myrepo    also scan project-level skills
        """,
    )
    parser.add_argument("path", type=Path, nargs="?", help="skill directory or file path")
    parser.add_argument("--json", action="store_true", help="JSON output format")
    parser.add_argument("--recursive", "-r", action="store_true",
                        help="recursively scan all skills in subdirectories")
    parser.add_argument("--min-severity", choices=["LOW", "MEDIUM", "HIGH"],
                        default="LOW", help="minimum report severity level (default: LOW)")
    parser.add_argument("--auto", "-a", action="store_true",
                        help="auto-discover and scan all agent skills")
    parser.add_argument("--project", "-p", type=Path, default=None,
                        help="project root (use with --auto to scan project-level skills)")
    parser.add_argument("--discover-only", action="store_true",
                        help="list discovered skills only, skip scanning")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="write results to file (auto-strips ANSI colors)")
    args = parser.parse_args()

    if not args.auto and not args.path:
        parser.error("path required, or use --auto")

    # redirect output to file (strip ANSI colors)
    _output_file = None
    if args.output:
        _output_file = open(args.output, "w", encoding="utf-8")
        _orig_print = __builtins__["print"] if isinstance(__builtins__, dict) else print
        _ansi_re = re.compile(r"\033\[[0-9;]*m")
        def _print_strip(*a, **kw):
            kw["file"] = _output_file
            a = tuple(_ansi_re.sub("", str(x)) for x in a)
            _orig_print(*a, **kw)
        import builtins
        builtins.print = _print_strip

    sev_order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "NONE": 0}
    min_sev = sev_order[args.min_severity]

    # collect scan targets: (agent_name | None, path)
    targets: list[tuple[str | None, Path]] = []

    if args.auto:
        project_root = args.project or (args.path if args.path and args.path.is_dir() else None)
        discovered = discover_skills(project_root)

        if args.discover_only:
            print_discovery_report(discovered)
            sys.exit(0)

        if not args.json:
            print_discovery_report(discovered)

        targets = discovered

        if not targets:
            if not args.json:
                print("No agent skills found. Use --project to specify project directory "
                      "or provide a path directly\n", file=sys.stderr)
            sys.exit(0)
    else:
        if not args.path.exists():
            print(f"Error: path does not exist: {args.path}", file=sys.stderr)
            sys.exit(1)

        if args.recursive and args.path.is_dir():
            for skill_md in args.path.rglob("SKILL.md"):
                targets.append((None, skill_md.parent))
            if not targets:
                targets = [(None, d) for d in args.path.iterdir() if d.is_dir()]
        else:
            targets = [(None, args.path)]

    if not targets:
        print("No scannable skills found", file=sys.stderr)
        sys.exit(1)

    total_findings = 0
    high_count = 0
    results_json = []

    for agent_name, target in sorted(targets, key=lambda x: str(x[1])):
        result = scan_skill(target)
        result.findings = [
            f for f in result.findings
            if sev_order.get(f.severity, 0) >= min_sev
        ]

        if args.json:
            data = {
                "agent": agent_name,
                "skill": str(target),
                "severity": result.max_severity,
                "categories": sorted(result.categories),
                "total_findings": len(result.findings),
                "findings": [
                    {
                        "id": f.pattern_id, "name": f.name,
                        "category": f.category, "severity": f.severity,
                        "file": f.file, "line": f.line, "match": f.match,
                    }
                    for f in result.findings
                ],
            }
            results_json.append(data)
        else:
            # show agent name in report title
            if agent_name:
                result.skill_path = f"[{agent_name}] {result.skill_path}"
            print_report(result)

        total_findings += len(result.findings)
        if result.max_severity == "HIGH":
            high_count += 1

    if args.json:
        print(json.dumps(results_json, indent=2, ensure_ascii=False))
    elif len(targets) > 1:
        c = COLORS
        print(f"\n{c['BOLD']}Scan Summary{c['RESET']}")
        print(f"  Skills scanned: {len(targets)}")
        print(f"  Total findings: {total_findings}")
        print(f"  High-risk skills: {high_count}")
        if high_count:
            print(f"  {c['BOLD']}{COLORS['HIGH']}⚠ High-risk skills found, review immediately!{c['RESET']}")
        else:
            print(f"  {COLORS['NONE']}✓ No high-risk skills found{c['RESET']}")
        print()

    if _output_file:
        _output_file.close()
        import builtins
        builtins.print = _orig_print
        print(f"Results written to: {args.output}")

    sys.exit(1 if high_count > 0 else 0)


if __name__ == "__main__":
    main()
