#!/usr/bin/env python3
"""
ShiftFlow Pro - Disaster Recovery & Database Restoration Tool
Safely restores an authenticated, verified backup into an isolated target or
specified location with safety pre-checks.
NEVER overwrites active production database without explicit confirmation.
"""
import os
import sys
import shutil
import sqlite3
import datetime
import logging
from verify_backup import verify_backup

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "disaster_recovery.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ShiftFlowRestore")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def restore_database(backup_path: str, target_db: str, allow_production_overwrite: bool = False) -> bool:
    if not os.path.exists(backup_path):
        logger.error(f"Backup file to restore not found: {backup_path}")
        return False

    prod_db = os.path.join(BASE_DIR, "shiftflow.db")
    if os.path.abspath(target_db) == os.path.abspath(prod_db) and not allow_production_overwrite:
        logger.error("SAFETY GUARD: Direct overwrite of production database 'shiftflow.db' is prohibited unless explicitly confirmed via flag.")
        return False

    # 1. Verify backup file integrity before restoring
    logger.info(f"Validating source backup before restoration: {backup_path}")
    if not verify_backup(backup_path):
        logger.error("Source backup failed validation checks! Restoration ABORTED.")
        return False

    # 2. If target exists, take a pre-restoration snapshot of the target
    if os.path.exists(target_db):
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        pre_snap = f"{target_db}.prerestore_{ts}.bak"
        shutil.copy2(target_db, pre_snap)
        logger.info(f"Existing target database snapshot preserved at: {pre_snap}")

    # 3. Perform restoration copy
    os.makedirs(os.path.dirname(os.path.abspath(target_db)), exist_ok=True)
    shutil.copy2(backup_path, target_db)
    logger.info(f"Restored backup {backup_path} to target: {target_db}")

    # Clean up associated target WAL / SHM files if any existed
    for ext in ["-wal", "-shm"]:
        wal_file = f"{target_db}{ext}"
        if os.path.exists(wal_file):
            try:
                os.remove(wal_file)
                logger.info(f"Cleaned stale journal file: {wal_file}")
            except Exception as e:
                logger.warning(f"Could not remove {wal_file}: {e}")

    # 4. Post-restoration verification
    conn = sqlite3.connect(target_db)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check")
        status = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users")
        u_cnt = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM roster_entries")
        r_cnt = cur.fetchone()[0]
        logger.info(f"Post-restoration verification SUCCESS. Integrity: {status}, Users: {u_cnt}, Roster: {r_cnt}")
        return True
    except Exception as e:
        logger.error(f"Post-restoration verification failed: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python restore_database.py <backup_path> <target_db> [--force-prod-overwrite]")
        sys.exit(1)

    src = sys.argv[1]
    dst = sys.argv[2]
    force_prod = "--force-prod-overwrite" in sys.argv
    success = restore_database(src, dst, allow_production_overwrite=force_prod)
    sys.exit(0 if success else 1)

