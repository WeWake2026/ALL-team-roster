#!/usr/bin/env python3
"""
ShiftFlow Pro - Automated Database Backup Framework
Uses SQLite's online backup API (sqlite3.Connection.backup) for transactionally
consistent point-in-time snapshots, correctly accounting for WAL mode.
Generates SHA-256 checksums and validates integrity.
"""
import os
import sys
import sqlite3
import hashlib
import json
import datetime
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
logger = logging.getLogger("ShiftFlowBackup")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_DB = os.path.join(BASE_DIR, "shiftflow.db")
DEFAULT_BACKUP_DIR = os.path.join(BASE_DIR, "backups", "automated")

def calculate_sha256(filepath: str) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()

def backup_sqlite(source_db: str = DEFAULT_DB, backup_dir: str = DEFAULT_BACKUP_DIR, retention_days: int = 7) -> dict:
    if not os.path.exists(source_db):
        logger.error(f"Source database file not found: {source_db}")
        raise FileNotFoundError(f"Source database does not exist: {source_db}")

    os.makedirs(backup_dir, exist_ok=True)
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"shiftflow_backup_{timestamp_str}.db"
    backup_path = os.path.join(backup_dir, backup_filename)

    logger.info(f"Initiating transactional SQLite online backup: {source_db} -> {backup_path}")

    # Step 1: Open source connection and force WAL checkpoint to ensure disk consistency
    src_conn = sqlite3.connect(source_db, timeout=30.0)
    try:
        cur = src_conn.cursor()
        cur.execute("PRAGMA wal_checkpoint(PASSIVE)")
        checkpoint_result = cur.fetchone()
        logger.info(f"Source WAL checkpoint status: busy={checkpoint_result[0]}, log={checkpoint_result[1]}, checkpointed={checkpoint_result[2]}")

        # Step 2: Open target connection and perform online backup
        dst_conn = sqlite3.connect(backup_path)
        try:
            with dst_conn:
                src_conn.backup(dst_conn, pages=100)
            logger.info("SQLite online backup stream completed successfully.")
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    # Step 3: Validate the generated backup
    val_conn = sqlite3.connect(backup_path)
    try:
        val_cur = val_conn.cursor()
        val_cur.execute("PRAGMA integrity_check")
        integrity_status = val_cur.fetchone()[0]
        if integrity_status != "ok":
            logger.error(f"Backup validation FAILED for {backup_path}: {integrity_status}")
            if os.path.exists(backup_path):
                os.remove(backup_path)
            raise ValueError(f"Integrity check failed: {integrity_status}")

        val_cur.execute("SELECT COUNT(*) FROM users")
        user_count = val_cur.fetchone()[0]
        val_cur.execute("SELECT COUNT(*) FROM roster_entries")
        roster_count = val_cur.fetchone()[0]
    finally:
        val_conn.close()

    file_size = os.path.getsize(backup_path)
    sha256_hash = calculate_sha256(backup_path)

    manifest = {
        "timestamp": datetime.datetime.now().isoformat(),
        "backup_file": backup_filename,
        "backup_path": backup_path,
        "size_bytes": file_size,
        "sha256": sha256_hash,
        "integrity": integrity_status,
        "user_count": user_count,
        "roster_count": roster_count
    }

    manifest_path = os.path.join(backup_dir, f"manifest_{timestamp_str}.json")
    with open(manifest_path, "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, indent=2)

    logger.info(f"Backup SUCCESS: {backup_filename} ({file_size} bytes, SHA256: {sha256_hash[:12]}..., Users: {user_count}, Roster: {roster_count})")

    # Step 4: Retention cleanup (Keep at least 7 daily and 4 weekly recovery points)
    cleanup_old_backups(backup_dir, retention_days)

    return manifest

def cleanup_old_backups(backup_dir: str, retention_days: int = 7):
    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=retention_days)
    for fname in os.listdir(backup_dir):
        if fname.startswith("shiftflow_backup_") and fname.endswith(".db"):
            fpath = os.path.join(backup_dir, fname)
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
            # Keep weekly backup (Sunday) for 30 days, others for retention_days
            is_weekly = mtime.weekday() == 6
            keep_cutoff = now - datetime.timedelta(days=30) if is_weekly else cutoff
            if mtime < keep_cutoff:
                try:
                    os.remove(fpath)
                    m_fpath = os.path.join(backup_dir, fname.replace("shiftflow_backup_", "manifest_").replace(".db", ".json"))
                    if os.path.exists(m_fpath):
                        os.remove(m_fpath)
                    logger.info(f"Expired backup pruned per retention policy: {fname}")
                except Exception as ex:
                    logger.warning(f"Could not prune expired backup {fname}: {ex}")

if __name__ == "__main__":
    manifest = backup_sqlite()
    print(json.dumps(manifest, indent=2))

