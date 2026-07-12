from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
BACKUP_ROOT = PROJECT_ROOT / "backups"


def copy_if_exists(source: Path, destination: Path) -> bool:
    if not source.exists():
        print(f"[SKIP] Missing: {source}")
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)

    if source.is_dir():
        shutil.copytree(
            source,
            destination,
            dirs_exist_ok=True,
        )
    else:
        shutil.copy2(source, destination)

    print(f"[BACKED UP] {source} -> {destination}")
    return True


def remove_old_backups(keep: int = 30) -> None:
    backup_folders = sorted(
        (
            folder
            for folder in BACKUP_ROOT.iterdir()
            if folder.is_dir()
        ),
        key=lambda folder: folder.stat().st_mtime,
        reverse=True,
    )

    for old_folder in backup_folders[keep:]:
        shutil.rmtree(old_folder)
        print(f"[REMOVED OLD BACKUP] {old_folder.name}")


def main() -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_dir = BACKUP_ROOT / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 68)
    print("CREATING SPORTS DATABASE BACKUP")
    print("=" * 68)
    print(f"Backup folder: {backup_dir}")

    copied = 0

    copied += copy_if_exists(
        DATA_DIR / "sports.db",
        backup_dir / "sports.db",
    )

    copied += copy_if_exists(
        DATA_DIR / "exports",
        backup_dir / "exports",
    )

    copied += copy_if_exists(
        DATA_DIR / "mlb",
        backup_dir / "mlb",
    )

    copied += copy_if_exists(
        DATA_DIR / "wnba",
        backup_dir / "wnba",
    )

    if copied == 0:
        print("No generated sports data was available to back up.")
        shutil.rmtree(backup_dir)
        return

    remove_old_backups(keep=30)

    print("=" * 68)
    print("BACKUP COMPLETE")
    print("=" * 68)


if __name__ == "__main__":
    main()
