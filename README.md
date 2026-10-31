# ShiftFlow Pro — MSEDCL Workforce, Location & Combined Roster Management System

ShiftFlow Pro is an enterprise-grade workforce management, employee scheduling, and role-based roster management portal built for MSEDCL operations across Maharashtra.

---

## 🌟 Key Features

1. **Location-First Authentication Experience:**
   - **Step 1: Visual Station Selection**: Select operational branch (Mumbai, Pune, Nagpur, Headquarters) on a sleek dashboard displaying live active headcount metrics.
   - **Step 2: Interactive Security Modal Pop-up**: Modal appears with the target location pre-selected and locked.
   - **Step 3: Direct Roster Destination**: On login, managers and administrators are routed immediately to that station's schedule matrix (`/roster/location?location_id=X`).
   - Remembers preferred station via browser `localStorage` and `active_location_id` session cookie.

2. **Full Employee Details & Comprehensive Profile Editor:**
   - **One-Click Info (`i`) & User ID Inspection**: Clicking any User ID (e.g. `AIPLCC175`) or the info icon in the management console pops up a comprehensive detail editor.
   - **Live Data Modification**: Edit Name, Email, Unique ID, ECN, BM ID, CRM ID, Designation, System Access Level, and Active/Offboarded status.
   - **Instant Station Headcount Reconciliation**: Transfer staff between branches (Mumbai, Pune, Nagpur, HQ) or adjust their active status to instantly update live station counts.
   - **Leave Quota Balances**: Direct adjustments for Casual Leave (CL), Sick Leave (SL), Privilege Leave (PL), and Comp-Off (CO).

3. **Leave Audit Master & Bulk Excel/CSV Sync:**
   - URL: `/admin/leave-master` and `/admin/sync`
   - Ingests official monthly leave balance statement sheets (Excel, CSV, PDF).
   - Matches and updates profiles by `Unique ID` / `ECN` / `Email`, provisions new staff, and generates immutable ledger snapshots.

4. **Dedicated Location-Wise Roster Module:**
   - URL: `/roster/location`
   - Scope-restricted roster view for each authorized work location (Mumbai, Pune, Nagpur, Headquarters).
   - Dynamic location selector, department and team filters, shift and date range toggles.
   - Staffing shortage detector (< 5 active staff alert banner).
   - Inline shift editing for authorized supervisors with server-side validation.

5. **Consolidated Combined Roster Module:**
   - URL: `/roster/combined`
   - Multi-location aggregation consolidating data from all locations authorized for the logged-in user.
   - Cross-location staffing comparison cards and headcount breakdown.
   - Multi-criteria client-side dynamic search and instant filtering.

6. **Granular RBAC & Leave Editing Authority Governance:**
   - URL: `/admin/assignments`
   - Administrators delegate who can edit and approve leave records via `can_approve` and `can_edit` flags.
   - Granular scoping across Locations, Departments, and Teams.

7. **Security, Governance & Compliance:**
   - Immutable Audit Logs recording all administrative actions, assignment modifications, and roster updates.
   - Server-side IDOR prevention denying cross-location access attempts.
   - Salted SHA-256 password hashing.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+ (using local virtual environment in `./venv`)
- SQLite 3 (or PostgreSQL via SQLAlchemy connection URL)

### 2. Start Application
```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### 3. Access Portal
Open `http://127.0.0.1:8000/login` in your web browser.

---

## 👥 Default Personas for Testing

| Persona / Role | Email / Unique ID | Password | Scope / Capabilities |
| :--- | :--- | :--- | :--- |
| **System Administrator** | `admin@msedcl.com` (`ADMIN001`) | `password123` | Full universal access across all locations, user details editor, headcount manager, leave master & assignments |
| **Operational Staff** | `shashi.kurhade@arceus.in` (`AIPLCC175`) | `Welcome@123` | Mumbai branch operational staff, personal schedule and leave portal |
| **Team Leader** | `poonam.gaikwad@arceus.in` (`AIPLCC114`) | `Welcome@123` | Team-scoped roster view, shift approvals, and subordinate scheduling |
| **Branch Employee** | `bhakti.chavan@arceus.in` (`AIPLCC899`) | `Welcome@123` | Schedule matrix & leave balance review |

---

## 🧪 Running Automated Tests
```powershell
.\venv\Scripts\python.exe run_audit_tests.py
```
