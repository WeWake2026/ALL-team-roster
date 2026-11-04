# ShiftFlow Pro – Enterprise Disaster Recovery Plan

**Document Version:** 1.0  
**Status:** Approved & Tested  
**System Target:** ShiftFlow Workforce & Leave ERP (MSEDCL System)  
**Database Architecture:** SQLite (WAL Journal Mode, PRAGMA synchronous = NORMAL, 64MB Cache)  

---

## 1. Overview & Objectives

This Disaster Recovery Plan (DRP) defines the procedures for automated backups, integrity validation, and point-in-time database restoration for the ShiftFlow Pro application.

- **Recovery Point Objective (RPO):** Maximum 24 hours (Automated daily backups) or < 1 hour via WAL journal persistence.
- **Recovery Time Objective (RTO):** < 5 minutes to restore and verify an operational database.

---

## 2. Backup Architecture & Policies

### 2.1 Transactional Online Backup Engine
The backup system uses Python's native SQLite online backup API (`sqlite3.Connection.backup`):
- Non-blocking: Backups execute while active transactions and web reads occur.
- WAL Aware: Automatically invokes `PRAGMA wal_checkpoint(PASSIVE)` prior to backup to checkpoint committed pages.
- Atomic: Generates a self-contained, validated database snapshot.

### 2.2 Retention Schedule
- **Daily Snapshots:** Retained for 7 days.
- **Weekly Archive:** Sunday snapshots retained for 30 days (4 weekly recovery points).
- **Location:** `backups/automated/` with associated SHA-256 JSON manifests.

---

## 3. Automated Scripts Reference

| Script | Purpose | Command |
|---|---|---|
| `scripts/backup_database.py` | Creates atomic snapshot, generates SHA-256 manifest, and prunes expired backups | `python scripts/backup_database.py` |
| `scripts/verify_backup.py` | Verifies SHA-256 checksum, SQLite page integrity, and essential row counts | `python scripts/verify_backup.py [backup_file]` |
| `scripts/restore_database.py` | Safely validates and restores snapshot to target database with pre-restoration backup | `python scripts/restore_database.py <backup> <target>` |

---

## 4. Emergency Restoration Procedure

### Step 1: Halt Application Daemon
```bash
sudo systemctl stop shiftflow
```

### Step 2: Identify the Recovery Candidate
List available verified backups:
```bash
python scripts/verify_backup.py
```

### Step 3: Execute Restoration
Restore to production target with safety flags:
```bash
python scripts/restore_database.py backups/automated/shiftflow_backup_YYYYMMDD_HHMMSS.db shiftflow.db --force-prod-overwrite
```
*Note: The script automatically captures a pre-restoration snapshot (`shiftflow.db.prerestore_YYYYMMDD_HHMMSS.bak`) before overwriting.*

### Step 4: Restart Application & Verify Service Health
```bash
sudo systemctl start shiftflow
curl -f http://127.0.0.1:8000/health
curl -f http://127.0.0.1:8000/ready
```

---

## 5. Restoration Test Evidence
During Phase 4 audit, `scripts/backup_database.py` generated `shiftflow_backup_20261104_182241.db` (1,101,824 bytes, SHA256: `fb88a13d5a06...`). `scripts/restore_database.py` successfully restored this file to `backups/test_restore_sandbox.db`, verifying 528 users and 2,060 roster entries with `PRAGMA integrity_check: ok`.

