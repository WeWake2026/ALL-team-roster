# User Roles, Assignment Scoping & Permissions Guide

ShiftFlow Pro implements fine-grained Role-Based Access Control (RBAC) combined with administrative data scoping.

---

## 1. Role Hierarchy & Responsibilities

### 👑 Super Admin / Admin
- **Visibility:** Universal access to all work locations, departments, teams, employees, rosters, and audit trails.
- **Administrative Rights:**
  - Create, modify, offboard, and reactivate user accounts.
  - Grant and revoke granular location, team, and employee assignments.
  - Access system configuration and audit logs.
  - Export reports across all locations.

### 💼 Human Resources (HR)
- **Visibility:** Authorized organizational locations and departments.
- **Operations:**
  - View employee master ledger and leave audit statements.
  - Approve or reject leave applications.
  - Edit authorized employee demographic details.
  - Export authorized workforce reports.

### 🏢 Location Manager / Operations Manager
- **Visibility:** Assigned work locations (e.g., Mumbai Operations Center).
- **Operations:**
  - View location shift schedules and daily capacity trackers.
  - Manage shifts, overtime, and weekend rotations within assigned locations.
  - Cannot access unassigned locations (enforced server-side).

### 👔 Team Leader (TL)
- **Visibility:** Assigned teams, squads, and direct reports only.
- **Operations:**
  - View team weekly and monthly roster schedules.
  - Perform inline shift modifications for subordinates if `can_edit` is granted.
  - Cannot access other Team Leaders' teams or unassigned employees.

### 👤 Employee / Agent
- **Visibility:** Strictly personal schedule, shift timing, and approved leaves.
- **Operations:**
  - View personal monthly roster.
  - Apply for Casual Leave (CL), Sick Leave (SL), or Comp-Off (CO).
  - No access to administrative tables, credentials console, or other employees' confidential records.

---

## 2. Granular Assignment Model (`UserAssignment`)

Through the **User & Data Assignment** console (`/admin/assignments`), Admins configure:

- **Target User**: The user receiving the delegation.
- **Location Scope**: Single location or all locations.
- **Department Scope**: Specific department or all departments.
- **Team Scope**: Specific squad or all teams.
- **Assigned Employee**: Specific target staff member (optional).
- **Effective Dates**: `effective_from` to `effective_to`.
- **Permissions Flags**:
  - `can_view`: View access to the scoped data.
  - `can_create`: Create new roster schedules or user records.
  - `can_edit`: Modify existing shift assignments and statuses.
  - `can_approve`: Approve shift changes or leave requests.
  - `can_export`: Download XLSX/CSV reports for the scoped data.
