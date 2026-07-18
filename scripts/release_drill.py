"""Local migration, backup/restore, and schema rollback rehearsal."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


def run(*args: str, env: dict[str, str]) -> None:
    subprocess.run(args, check=True, env=env, capture_output=True, text=True)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="orbit-release-drill-") as directory:
        database = Path(directory) / "preproduction.db"
        backup = Path(directory) / "backup.db"
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite+pysqlite:///{database}"
        alembic = (sys.executable, "-m", "alembic", "-c", str(root / "services/api/alembic.ini"))
        run(*alembic, "upgrade", "head", env=env)
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE release_drill_marker (value TEXT NOT NULL)")
            connection.execute("INSERT INTO release_drill_marker VALUES ('verified-backup')")
            connection.commit()
            with sqlite3.connect(backup) as target:
                connection.backup(target)
        database.unlink()
        shutil.copy2(backup, database)
        with sqlite3.connect(database) as restored:
            marker = restored.execute("SELECT value FROM release_drill_marker").fetchone()
        if marker != ("verified-backup",):
            raise RuntimeError("backup restore marker did not survive")
        run(*alembic, "downgrade", "-1", env=env)
        run(*alembic, "upgrade", "head", env=env)
        print(
            json.dumps(
                {
                    "deployment": "migration-upgrade-complete",
                    "backupRestore": "verified",
                    "applicationRollback": "schema-down-up-complete",
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
