from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

import sqlite3


def backup_sqlite_db(db_path: Path, out_dir: Path, *, as_sql: bool) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outputs: list[Path] = []

    db_backup_path = out_dir / f"backup_{timestamp}_{db_path.name}"
    shutil.copy2(db_path, db_backup_path)
    outputs.append(db_backup_path)

    if as_sql:
        sql_backup_path = out_dir / f"backup_{timestamp}_{db_path.stem}.sql"
        connection = sqlite3.connect(str(db_path))
        try:
            dump = "\n".join(connection.iterdump())
        finally:
            connection.close()
        sql_backup_path.write_text(dump, encoding="utf-8")
        outputs.append(sql_backup_path)

    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup SQLite database file.")
    parser.add_argument("--db", default="data/app.db", help="Path to SQLite DB file.")
    parser.add_argument(
        "--out",
        default="backups",
        help="Output directory for backups (default: backups).",
    )
    parser.add_argument(
        "--sql",
        action="store_true",
        help="Also create a .sql dump using sqlite3 iterdump().",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB file not found: {db_path}")

    out_dir = Path(args.out)
    outputs = backup_sqlite_db(db_path, out_dir, as_sql=bool(args.sql))
    for path in outputs:
        print(path.resolve())


if __name__ == "__main__":
    main()

