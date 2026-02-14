"""Version history and rollback support."""
import json
import shutil
from pathlib import Path
from datetime import datetime
from logger import logger

BASE_DIR = Path(__file__).parent
BACKUP_DIR = BASE_DIR / "backups"
MAX_BACKUPS_PER_SKILL = 3
MAX_BACKUP_SIZE_MB = 200  # skip backup if skill dir exceeds this


def _dir_size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / (1024 * 1024)


def backup_skill(skill_id: str, skill_dir: Path) -> bool:
    """Backup skill before update/uninstall. Skips if dir is too large."""
    try:
        BACKUP_DIR.mkdir(exist_ok=True)
        size = _dir_size_mb(skill_dir)
        if size > MAX_BACKUP_SIZE_MB:
            logger.warning(f"Skipping backup for {skill_id}: {size:.0f}MB exceeds {MAX_BACKUP_SIZE_MB}MB limit")
            return False

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"{skill_id}_{timestamp}"
        shutil.copytree(skill_dir, backup_path)
        logger.info(f"Backed up {skill_id} ({size:.1f}MB) to {backup_path.name}")

        # Keep only last N backups per skill
        backups = sorted([d for d in BACKUP_DIR.iterdir()
                         if d.is_dir() and d.name.startswith(f"{skill_id}_")])
        for old in backups[:-MAX_BACKUPS_PER_SKILL]:
            shutil.rmtree(old, ignore_errors=True)
        return True
    except Exception as e:
        logger.error(f"Backup failed for {skill_id}: {e}")
        return False


def list_backups(skill_id: str) -> list[dict]:
    """List available backups for a skill."""
    if not BACKUP_DIR.exists():
        return []
    prefix = f"{skill_id}_"
    backups = []
    for d in BACKUP_DIR.iterdir():
        if d.is_dir() and d.name.startswith(prefix):
            ts = d.name[len(prefix):]
            backups.append({"path": d, "timestamp": ts, "name": d.name})
    return sorted(backups, key=lambda x: x["timestamp"], reverse=True)


def rollback_skill(skill_id: str, backup_name: str, target_dir: Path) -> tuple[bool, str]:
    """Restore skill from backup."""
    try:
        backup_path = BACKUP_DIR / backup_name
        if not backup_path.exists():
            return False, "Backup not found"

        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(backup_path, target_dir)
        logger.info(f"Rolled back {skill_id} from {backup_name}")
        return True, f"Restored from {backup_name}"
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        return False, str(e)
