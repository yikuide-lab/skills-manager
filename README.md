# ⚡ Skills Manager

A GUI application for discovering, downloading, and managing AI Agent Skills — with one-click deployment to Claude Code, Kiro CLI, and Gemini CLI.

No external dependencies — Python standard library only (tkinter + sqlite3).

[中文](README_zh.md) | [한국어](README_ko.md) | [日本語](README_ja.md)

## Quick Start

```bash
python3 run.py
```

Or install with pip:

```bash
pip install -e .
skills-manager
```

## Features

- **Auto-discovery**: Fetches skills from remote registry, falls back to local `registry.json`
- **Install/Uninstall**: One-click install with progress indicator
- **Update detection**: Highlights skills with newer versions available
- **Search & filter**: Fuzzy search with relevance scoring; filter by installed/available/category
- **Pagination**: SQLite-backed paginated queries — handles thousands of skills smoothly
- **Auto-backup**: Automatic version backup before updates/uninstalls
- **Security scan**: Static analysis for malicious patterns (prompt injection, data exfiltration, privilege escalation, supply chain)
- **Pre-scan**: Scan uninstalled skills before installing — downloads to temp, scans, discards
- **Scan tracker**: Real-time scan progress dialog with scrollable result log
- **Proxy support**: Configurable HTTP/HTTPS proxy for network access
- **Dark theme GUI**: Clean, modern Catppuccin Mocha interface with tooltips
- **Deploy to AI tools**: Symlink installed skills to Claude Code, Kiro CLI, Gemini CLI
- **Keyboard shortcuts**: Ctrl+F (search), Ctrl+R (refresh), Ctrl+I (installed), Escape (clear)

## Deploy Skills to AI Tools

After installing skills via the GUI, deploy them to your AI coding assistants:

```bash
python3 deploy_skills.py              # deploy to all detected tools
python3 deploy_skills.py --target kiro  # deploy to specific tool
python3 deploy_skills.py --dry-run    # preview without changes
python3 deploy_skills.py --clean      # remove deployed symlinks
```

Supported targets:
| Tool | Skills Directory |
|------|------------------|
| Claude Code | `~/.claude/skills/` |
| Kiro CLI | `~/.kiro/skills/` |
| Gemini CLI | `~/.gemini/skills/` |

Skills are symlinked (not copied), so they stay in sync and use no extra disk space.

## Security Scanning

Scan skills for malicious content — from the GUI or command line:

```bash
python3 skillscan.py ./my-skill/                 # scan a skill directory
python3 skillscan.py --auto                       # scan all installed skills
python3 skillscan.py --auto --min-severity HIGH   # show only high-risk findings
python3 skillscan.py --auto -o report.txt         # write results to file
python3 skillscan.py --auto --json                # JSON output
```

Detects 4 categories of threats: Prompt Injection, Data Exfiltration, Privilege Escalation, Supply Chain attacks.

In the GUI, use **🛡 Security Scan** on installed skills or **🛡 Pre-scan** on uninstalled skills to evaluate risk before installing.

## Proxy Configuration

Click **⚙ Proxy** in the header to configure HTTP/HTTPS proxy. Settings persist in `settings.json`.

All network requests (registry fetch, GitHub API, skill downloads) go through the configured proxy.

## Architecture

```
skills_manager/
├── run.py              # Entry point
├── gui.py              # tkinter GUI (pagination, scan tracker, tooltips)
├── skill_core.py       # Core logic (fetch, install, scan, proxy)
├── db.py               # SQLite storage backend (paginated queries)
├── deploy_skills.py    # Deploy skills to Claude/Kiro/Gemini
├── skillscan.py        # Security scanner (14 patterns, 4 categories)
├── logger.py           # Logging system
├── version_manager.py  # Backup & rollback
├── registry.json       # Local fallback registry
├── settings.json       # User settings (proxy, etc.) — auto-created
├── skills.db           # SQLite database — auto-created
├── installed_skills/   # Installed skills + manifest
├── logs/               # Operation logs
└── backups/            # Skill version backups
```

## Custom Registry

Edit `registry.json` or point `REMOTE_REGISTRIES` in `skill_core.py` to your own registry URL.

## License

MIT