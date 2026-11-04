import os
import sys
import sqlite3
import shutil

# Include scripts folder in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
from backup_database import backup_sqlite
from verify_backup import verify_backup
from restore_database import restore_database

def test_backup_and_recovery_lifecycle():
    # 1. Trigger online backup
    manifest = backup_sqlite()
    backup_file = manifest["backup_path"]
    assert os.path.exists(backup_file), f"Backup file not generated: {backup_file}"
    assert manifest["integrity"] == "ok"
    assert manifest["user_count"] > 0

    # 2. Verify generated backup
    valid = verify_backup(backup_file)
    assert valid, "verify_backup returned False on freshly generated backup"

    # 3. Test restoration into isolated sandbox
    sandbox_db = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backups", "sandbox_test_restore.db"))
    restored = restore_database(backup_file, sandbox_db)
    assert restored, "restore_database failed"
    assert os.path.exists(sandbox_db)

    # Validate sandbox table counts
    conn = sqlite3.connect(sandbox_db)
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check")
    assert cur.fetchone()[0] == "ok"
    cur.execute("SELECT COUNT(*) FROM users")
    assert cur.fetchone()[0] == manifest["user_count"]
    cur.execute("SELECT COUNT(*) FROM roster_entries")
    assert cur.fetchone()[0] == manifest["roster_count"]
    conn.close()

    if os.path.exists(sandbox_db):
        os.remove(sandbox_db)

if __name__ == "__main__":
    test_backup_and_recovery_lifecycle()
    print("ALL DATABASE RECOVERY AUTOMATED TESTS PASSED!")

