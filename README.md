# ShiftFlow Pro — MSEDCL Workforce, Location & Combined Roster Management System

ShiftFlow Pro is an enterprise-grade workforce management, employee scheduling, and role-based roster management portal built for MSEDCL operations across Maharashtra.

---

## 🌟 Key Features

1. **Centralized Administration & RBAC:**
   - Granular Role-Based Access Control supporting Super Admin, Admin, HR, Location Manager, Team Leader, and Employee.
   - Least-privilege access enforced server-side.
   - Dedicated "User & Data Assignment" console for granular scoping of locations, departments, teams, team leaders, and employees with separate view/create/edit/approve/export flags.
2. **Dedicated Location-Wise Roster Module:**
   - URL: `/roster/location`
   - Scope-restricted roster view for each authorized work location (Mumbai, Pune, Nagpur, Headquarters).
   - Dynamic location selector, department and team filters, shift and date range toggles.
   - Staffing shortage detector (< 5 active staff alert banner).
   - Inline shift editing for authorized supervisors with server-side validation.
3. **Consolidated Combined Roster Module:**
   - URL: `/roster/combined`
   - Multi-location aggregation consolidating data from all locations authorized for the logged-in user.
   - Cross-location staffing comparison cards and headcount breakdown.
   - Multi-criteria client-side dynamic search and instant filtering.
4. **Employee Master & User Provisioning:**
   - Centralized employee profiles preserving original Unique IDs (e.g. `AIPLCC175`, `AIPLCC114`), ECN, CRM ID, and BM ID.
   - Deactivation/offboarding lifecycle preservation with exit dates and reasons.
   - Company official fractional leave balance ledger (CL, SL, CO) statement integration.
5. **Security, Governance & Compliance:**
   - Immutable Audit Logs recording all administrative actions, assignment modifications, and roster updates.
   - Server-side IDOR prevention denying cross-location access attempts.
   - SHA-256 salted password hashing.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+ (using the local virtual environment in `./venv`)
- SQLite 3 (or PostgreSQL via SQLAlchemy connection URL)

### 2. Start Application
```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Access Portal
Open `http://127.0.0.1:8000` in your web browser.

---

## 👥 Default Personas for Testing

| Persona / Role | Email / Identifier | Password | Access Scope |
| :--- | :--- | :--- | :--- |
| **System Administrator** | `admin@msedcl.com` | `Welcome@123` | Universal access to all locations, rosters, user assignments, and settings |
| **HR Officer** | `hr.sneha@msedcl.com` | `Welcome@123` | HR management, leave master ledger, authorized organizational scope |
| **Operations Manager** | `mgr.rajesh@msedcl.com` | `Welcome@123` | Operations management, location-level shift and roster editing |
| **Team Leader** | `tl.poonam@msedcl.com` | `Welcome@123` | Team-scoped roster view and inline editing for assigned staff |
| **Agent / Employee** | `shashi.kurhade@arceus.in` | `Welcome@123` | Personal dashboard, schedule, and leave requests |

---

## 🧪 Running Automated Tests
```powershell
.\venv\Scripts\python.exe run_audit_tests.py
```
