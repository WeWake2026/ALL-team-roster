#!/usr/bin/env python3
"""
ShiftFlow Pro - Backup Verification Framework
Verifies SQLite database integrity, schema tables, row counts, and SHA-256 manifest hashes.
"""
import os
import sys
import sqlite3
import hashlib
import json
import logging

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "backups.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ShiftFlowVerifyBackup")

def calculate_sha256(filepath: str) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()

def verify_backup(backup_path: str, manifest_path: str = None) -> bool:
    if not os.path.exists(backup_path):
        logger.error(f"Target backup file not found: {backup_path}")
        return False

    logger.info(f"Starting verification of backup: {backup_path}")

    # Check Manifest SHA-256 match if provided or found
    if not manifest_path:
        base_dir = os.path.dirname(backup_path)
        base_name = os.path.basename(backup_path)
        candidate_manifest = os.path.join(base_dir, base_name.replace("shiftflow_backup_", "manifest_").replace(".db", ".json"))
        if os.path.exists(candidate_manifest):
            manifest_path = candidate_manifest

    if manifest_path and os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as mf:
            m_data = json.load(mf)
        expected_sha = m_data.get("sha256")
        actual_sha = calculate_sha256(backup_path)
        if expected_sha != actual_sha:
            logger.error(f"SHA-256 Checksum Mismatch! Expected: {expected_sha}, Actual: {actual_sha}")
            return False
        logger.info(f"SHA-256 Checksum matched: {actual_sha}")

    # Connect to SQLite file and perform deep integrity checks
    try:
        conn = sqlite3.connect(backup_path)
        cur = conn.cursor()

        cur.execute("PRAGMA integrity_check")
        res = cur.fetchone()[0]
        if res != "ok":
            logger.error(f"PRAGMA integrity_check failed: {res}")
            return False
        logger.info(f"PRAGMA integrity_check: {res}")

        cur.execute("PRAGMA foreign_key_check")
        fk_violations = cur.fetchall()
        if fk_violations:
            logger.error(f"Foreign key violations found: {len(fk_violations)}")
            return False
        logger.info("PRAGMA foreign_key_check: 0 violations")

        # Essential table check
        required_tables = ["users", "roster_entries", "leave_requests", "locations", "shifts", "branches", "departments"]
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = set(r[0] for r in cur.fetchall())

        missing = [t for t in required_tables if t not in existing_tables]
        if missing:
            logger.error(f"Missing essential tables in backup: {missing}")
            return False

        cur.execute("SELECT COUNT(*) FROM users")
        u_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM roster_entries")
        r_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM leave_requests")
        l_count = cur.fetchone()[0]

        logger.info(f"Essential Counts: Users={u_count}, RosterEntries={r_count}, LeaveRequests={l_count}")
        conn.close()

        logger.info(f"Verification of {backup_path} completed successfully: VERIFIED_VALID")
        return True
    except Exception as e:
        logger.error(f"Error validating SQLite backup {backup_path}: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        # Default to latest in backups/automated
        auto_dir = os.path.join(os.path.dirname(__file__), "..", "backups", "automated")
        backups = [os.path.join(auto_dir, f) for f in os.listdir(auto_dir) if f.startswith("shiftflow_backup_") and f.endswith(".db")]
        if not backups:
            print("No automated backups found to verify.")
            sys.exit(1)
        target = sorted(backups)[-1]

    ok = verify_backup(target)
    sys.exit(0 if ok else 1)

