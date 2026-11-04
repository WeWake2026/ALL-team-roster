# ShiftFlow Pro – Enterprise Security Hardening & OWASP ASVS v4.0.3 Report

**Audit Date:** 04 November 2026  
**Standards:** OWASP Application Security Verification Standard (ASVS) v4.0.3, NIST SP 800-63B  
**Target:** ShiftFlow Workforce & Leave ERP (MSEDCL System)  

---

## 1. Security Architecture & Controls Matrix

| ASVS Category | Requirement & Control | Implementation in ShiftFlow Pro | Verification Result |
|---|---|---|---|
| **V2: Authentication** | Secure password hashing algorithm | Upgraded to **Bcrypt (work factor 12)** with transparent, backward-compatible automatic rehash upon successful login. | **VERIFIED & PASSED** |
| **V2: Account Lifecycle** | Deactivated user lockout | Both `/login` authentication and `require_auth` dependency check `user.is_active == True`. Offboarded staff are blocked immediately. | **VERIFIED & PASSED** |
| **V3: Session Management** | Session invalidation on logout | `/logout` records logout timestamp, computes elapsed duration, and unsets active session flags. | **VERIFIED & PASSED** |
| **V3: Cookie Security** | Dynamic production cookie flags | Cookies enforce `HttpOnly=True`, `SameSite=Lax`, and `Secure=True` when `ENVIRONMENT=production`. | **VERIFIED & PASSED** |
| **V4: Access Control (RBAC)** | Server-side authorization | Enforced via FastAPI dependencies (`require_auth`, `require_admin`, `get_user_perms`). Direct API tampering by regular employees returns HTTP 403. | **VERIFIED & PASSED** |
| **V5: Malicious Input** | SQL Injection defense | All database queries use SQLAlchemy ORM with parameterized query bindings; zero raw SQL string concatenation. | **VERIFIED & PASSED** |
| **V8: Data Protection** | Sensitive data redaction | Logging module (`logging_config.py`) redacts passwords, session IDs, and authorization tokens before writing to disk. | **VERIFIED & PASSED** |
| **V14: Configuration** | Security Headers | Middleware injects `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `X-XSS-Protection: 1; mode=block`, and `Permissions-Policy`. | **VERIFIED & PASSED** |

---

## 2. Automated Security Test Evidence
Automated suite in [tests/test_security.py](file:///c:/Users/Vivek/Downloads/MSEDCL_Quality_Audit_System_Starter/New%20folder/tests/test_security.py) executed 4 critical validation checks:
1. `test_security_headers_and_cookies`: Confirmed all 5 ASVS security headers present on responses.
2. `test_auth_and_bcrypt_migration`: Confirmed user password hash upgraded to `$2b$12$...` in database.
3. `test_deactivated_account_rejection`: Confirmed deactivated user `mgr.rajesh@msedcl.com` cannot authenticate.
4. `test_rbac_unauthorized_access`: Confirmed regular employees calling `/admin/control-center`, `/api/admin/system/health`, or `/api/admin/organization/update` receive **HTTP 403 Forbidden**.

