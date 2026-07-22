"""List orphan/old-render artifacts; delete only when --apply is explicitly provided."""

import argparse
import sqlite3
from pathlib import Path

from app.config import get_settings
from app.constants import RENDER_VERSION


def candidates(database_path: Path, artifact_root: Path) -> list[Path]:
    root = artifact_root.resolve()
    if not root.is_dir():
        return []
    connection = sqlite3.connect(database_path)
    try:
        known = {
            (root / row[0]).resolve()
            for row in connection.execute(
                "SELECT relative_path FROM artifacts WHERE render_version = ?", (RENDER_VERSION,)
            )
        }
    finally:
        connection.close()
    return sorted(path for path in root.rglob("*.png") if path.resolve() not in known)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Ro'yxatdagi fayllarni o'chiradi")
    args = parser.parse_args()
    settings = get_settings()
    files = candidates(settings.database_path, settings.artifact_dir)
    for path in files:
        print(path)
    if args.apply:
        for path in files:
            path.unlink()
    result = "o'chirildi" if args.apply else "topildi (dry-run)"
    print(f"{len(files)} ta fayl {result}")


if __name__ == "__main__":
    main()
