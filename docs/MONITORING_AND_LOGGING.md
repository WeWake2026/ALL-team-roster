# ShiftFlow Pro – Centralized Logging & Health Monitoring Specification

**Document Version:** 1.0  
**Status:** Implemented & Verified  
**Target:** ShiftFlow Workforce & Leave ERP (MSEDCL System)  

---

## 1. Overview

ShiftFlow Pro incorporates structured JSON application logging and health probe endpoints to support production operation under Kubernetes, Docker, or systemd supervisor suites.

---

## 2. Structured Application Logging (`logging_config.py`)

### 2.1 Configuration & Storage
- **File Location:** `logs/app.log`
- **Rotation Policy:** 15 MB max file size, 5 backup generations (75 MB total maximum disk usage).
- **Format:** JSON structure containing ISO-8601 timestamp, log level, module name, and structured event payload.
- **Console Mirroring:** Output mirrored to standard output for `systemd journalctl` collection.

### 2.2 Sensitive Data Redaction
All logging methods filter against `SENSITIVE_KEYS` (`password`, `secret`, `token`, `cookie`, `hashed_password`, `authorization`). Any match is replaced with `"REDACTED"` before serialization.

### 2.3 Correlation IDs
The HTTP middleware generates or passes through a unique `X-Correlation-ID` header for every request (e.g., `bf589923`). This enables tracing a transaction from reverse proxy through FastAPI endpoints to database commits.

---

## 3. Health & Readiness Endpoints

| Endpoint | Target Consumer | Purpose | Expected Response |
|---|---|---|---|
| `GET /health` | Container runtime / Load balancer | Liveness probe: confirms event loop and ASGI server are responsive | `200 OK {"status": "ok", "service": "shiftflow-pro"}` |
| `GET /ready` | Reverse proxy / Ingress router | Readiness probe: confirms database read/write availability without leaking sensitive schemas | `200 OK {"status": "ready", "database": "connected", "journal_mode": "WAL"}` |
| `GET /api/admin/system/health` | Authenticated Administrators | Administrative telemetry (active connections, record counts) | `200 OK` (Requires Admin session cookie) |

