#!/usr/bin/env python3
"""
Deploy installed skills to Claude Code, Kiro CLI, and Gemini CLI skill directories.

Each tool expects: <skills_dir>/<skill-name>/SKILL.md (+ optional scripts/, references/)
This script finds the real SKILL.md inside nested installed_skills dirs and creates
symlinks in each tool's skills directory.

Usage:
    python3 deploy_skills.py                    # detect & deploy to all available tools
    python3 deploy_skills.py --target claude    # deploy to Claude only
    python3 deploy_skills.py --target gemini    # deploy to Gemini only
    python3 deploy_skills.py --target kiro      # deploy to Kiro only
    python3 deploy_skills.py --dry-run          # preview without changes
    python3 deploy_skills.py --clean            # remove deployed symlinks
"""

import argparse
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
INSTALLED_DIR = BASE_DIR / "installed_skills"

# Tool skill directories (global)
TARGETS = {
    "claude": Path.home() / ".claude" / "skills",
    "kiro":   Path.home() / ".kiro" / "skills",
    "gemini": Path.home() / ".gemini" / "skills",
}


def find_skill_dirs(installed_dir: Path) -> dict[str, Path]:
    """Find the actual skill directory (containing SKILL.md) for each installed skill.
    
    Returns {skill_name: path_to_dir_containing_SKILL.md}
    """
    skills = {}
    for skill_md in installed_dir.rglob("SKILL.md"):
        skill_dir = skill_md.parent
        name = skill_dir.name

        # Skip if SKILL.md has no frontmatter (placeholder files)
        try:
            content = skill_md.read_text(errors="ignore")[:200]
            if not content.strip().startswith("---") and "# " not in content[:50]:
                continue
        except OSError:
            continue

        # Prefer deeper nested paths (real content) over top-level placeholders
        if name in skills:
            if len(str(skill_dir)) > len(str(skills[name])):
                skills[name] = skill_dir
        else:
            skills[name] = skill_dir

    return skills


def deploy(target_name: str, target_dir: Path, skills: dict[str, Path], dry_run: bool) -> int:
    """Create symlinks in target_dir for each skill. Returns count of new links."""
    if not target_dir.parent.exists():
        print(f"  ⏭  {target_name}: config dir {target_dir.parent} not found, skipping")
        return 0

    target_dir.mkdir(parents=True, exist_ok=True)
    created = 0
    skipped = 0

    for name, src in sorted(skills.items()):
        link = target_dir / name
        if link.exists() or link.is_symlink():
            skipped += 1
            continue
        if dry_run:
            print(f"  [dry-run] {name} -> {src}")
        else:
            link.symlink_to(src)
        created += 1

    action = "would create" if dry_run else "created"
    print(f"  ✅ {target_name}: {action} {created} symlinks, {skipped} already exist")
    return created


def clean(target_name: str, target_dir: Path, skills: dict[str, Path], dry_run: bool) -> int:
    """Remove symlinks that point into our installed_skills dir."""
    if not target_dir.exists():
        return 0
    removed = 0
    for link in sorted(target_dir.iterdir()):
        if link.is_symlink():
            real = Path(os.readlink(link))
            if not real.is_absolute():
                real = (link.parent / real).resolve()
            if str(INSTALLED_DIR) in str(real):
                if dry_run:
                    print(f"  [dry-run] remove {link.name}")
                else:
                    link.unlink()
                removed += 1
    action = "would remove" if dry_run else "removed"
    print(f"  🧹 {target_name}: {action} {removed} symlinks")
    return removed


def main():
    parser = argparse.ArgumentParser(description="Deploy skills to AI tool directories")
    parser.add_argument("--target", choices=["claude", "kiro", "gemini"], help="Deploy to specific tool only")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    parser.add_argument("--clean", action="store_true", help="Remove deployed symlinks")
    args = parser.parse_args()

    targets = {args.target: TARGETS[args.target]} if args.target else TARGETS

    print(f"Scanning {INSTALLED_DIR} for skills...")
    skills = find_skill_dirs(INSTALLED_DIR)
    print(f"Found {len(skills)} deployable skills\n")

    if not skills and not args.clean:
        print("No skills found.")
        return

    for name, target_dir in targets.items():
        if args.clean:
            clean(name, target_dir, skills, args.dry_run)
        else:
            deploy(name, target_dir, skills, args.dry_run)


if __name__ == "__main__":
    main()
