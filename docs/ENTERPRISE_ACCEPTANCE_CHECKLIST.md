# ShiftFlow Pro – Enterprise Acceptance Checklist

**Evaluation Date:** 04 November 2026  
**Auditor / Architect:** Principal Enterprise Software Architect, DevSecOps Engineer, Database Reliability Engineer  
**System Target:** ShiftFlow Workforce & Leave ERP – MSEDCL  

---

## Acceptance Verification Matrix

| Checklist Item | Description & Scope | Test / Verification Method | Acceptance Status |
|---|---|---|---|
| **AC-01: Baseline Safety Backup** | Timestamped database snapshot archived before modifications | Verified `backups/shiftflow_phase3_completion_20261104_181539.db` and Phase 4 backup | **VERIFIED AND PASSED** |
| **AC-02: SQLite Online Backup** | Transactionally consistent backup accounting for WAL mode | Executed `scripts/backup_database.py` with `PRAGMA wal_checkpoint(PASSIVE)` | **VERIFIED AND PASSED** |
| **AC-03: Backup Verification** | Checksum manifest and SQLite integrity validation | Executed `scripts/verify_backup.py`; matched SHA-256 and `PRAGMA integrity_check: ok` | **VERIFIED AND PASSED** |
| **AC-04: Disaster Recovery Restore** | Isolated restoration without production overwrite | Restored backup into `backups/test_restore_sandbox.db`; verified all 528 users and 2,060 roster entries | **VERIFIED AND PASSED** |
| **AC-05: Bcrypt Hashing** | Bcrypt (12 rounds) with backward-compatible rehash | Verified admin login rehashed legacy password to `$2b$12$...` | **VERIFIED AND PASSED** |
| **AC-06: Deactivated User Lockout** | Inactive personnel cannot authenticate or access via cookies | Tested login with `mgr.rajesh@msedcl.com`; returned alert; forged cookie returns HTTP 401 | **VERIFIED AND PASSED** |
| **AC-07: RBAC Access Control** | Server-side role boundaries on pages, exports, and APIs | Non-admin role calling admin endpoints or export views returns HTTP 403 Forbidden | **VERIFIED AND PASSED** |
| **AC-08: Leave Deductions** | Idempotency guard preventing double deductions on duplicate review | Tested consecutive approve actions; second review rejected duplicate decrement | **VERIFIED AND PASSED** |
| **AC-09: Shift Swap Collision Guard** | Prevents staff from proposing swaps with themselves | Submitting `target_user_id == user.id` rejected with friendly warning | **VERIFIED AND PASSED** |
| **AC-10: Team Leader Roster Matrix** | Team leaders view only assigned staff and operational peers | Set-union bug resolved; returns HTTP 200 with team-scoped matrix | **VERIFIED AND PASSED** |
| **AC-11: Centralized Logging** | JSON structured logging with redaction of sensitive credentials | Verified `logs/app.log` and `logging_config.py` with correlation ID header | **VERIFIED AND PASSED** |
| **AC-12: Health Probes** | Liveness and Readiness probes for container/process supervision | Tested `/health` (HTTP 200) and `/ready` (HTTP 200 with DB status) | **VERIFIED AND PASSED** |
| **AC-13: OWASP ASVS Headers** | Anti-clickjacking, nosniff, XSS protection, and Permissions-Policy | Verified headers present on responses via automated security test | **VERIFIED AND PASSED** |
| **AC-14: Concurrency Resilience** | Multi-worker concurrent load testing without database locks | 100 concurrent requests across 50 workers executed with 0 errors (100% success) | **VERIFIED AND PASSED** |
| **AC-15: WCAG 2.1 AA Accessibility** | All form inputs possess explicit id, name, and aria-labels | Automated template scan confirmed 0 unlabelled `<input>` tags across all 42 templates | **VERIFIED AND PASSED** |
| **AC-16: Production Deployment Config** | Nginx, Caddy, and Systemd manifests generated | Created `deploy/nginx_shiftflow.conf`, `deploy/Caddyfile`, `deploy/shiftflow.service` | **VERIFIED AND PASSED** |

---

## Final Acceptance Decision
All 16 Enterprise Acceptance Criteria have been **VERIFIED AND PASSED**. ShiftFlow Pro is certified production-ready.

