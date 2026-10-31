# Changelog — ShiftFlow Pro Upgrade
 
All notable changes to the ShiftFlow Pro application are documented in this file.

## [2.2.0] - 2026-10-31 — Location-First Authentication, User Profile Editor & Leave Master Control

### 🚀 Added
- **Location-First Authentication Experience (`/login`):**
  - Modern station cards showing real-time active staff counts for Mumbai, Pune, Nagpur, and Headquarters.
  - Interactive login modal popup locking the user into their chosen branch context.
  - Direct post-login redirection to the location roster desk (`/roster/location?location_id=X`).
  - Browser `localStorage` and `active_location_id` session preservation.
- **Comprehensive User Profile & Quota Editor Modal (`/admin/users`):**
  - Clickable User Unique ID (e.g. `AIPLCC175`) and Info (`i`) button triggers detailed profile editor.
  - Direct modification of Name, Email, Unique ID, ECN, BM ID, CRM ID, Role, Access Level, and Active/Offboarded status.
  - Branch transfer selector that instantly reconciles operational station headcounts.
  - Granular leave quota balance editor for CL, SL, PL, and Comp-Off (CO).
  - Built-in instant password reset input within the editor.
- **Excel/CSV Leave Master Ingestion & Ledger Sync (`/admin/leave-master`):**
  - Automated processing of monthly leave statement spreadsheets.
  - Match and update balances by Unique ID / ECN / Email.
  - Generates immutable ledger balance snapshots for audit compliance.
- **Admin Leave Authorization & Delegation Governance (`/admin/assignments`):**
  - Granular permission flags (`can_approve`, `can_edit`) allowing administrators to define who handles leave approvals and schedule edits.

---

## [2.1.0] - 2026-10-26 — Comprehensive Leave Management System Upgrade

### 🚀 Added
- **Leave Application Engine (`/leaves/apply`):**
  - Unique Leave Application ID generation (`LA-YYYYMMDD-XXXX`).
  - Multi-file evidence attachment support (medical certificates, bills, prescriptions, invitation cards).
  - Overlap detection preventing duplicate or overlapping requests on existing active leave periods.
  - Duration calculation engine supporting full-day (1.0) and half-day (0.5) deductions with balance pre-validation.
- **Application Amendment / Edit Workflow (`/leaves/edit`):**
  - Edit modal for eligible applications (Draft, Pending Approval, Rejected).
  - Snapshot auditing before and after edits in `leave_history`.
- **Cancellation & Withdrawal Engine (`/leaves/cancel`):**
  - Automatic balance refunding and roster restoration upon cancellation approval.
- **Self-Approval Guard:**
  - Server-side validation ensuring managers and team leaders cannot approve their own leave applications.

---

## [2.0.0] - 2026-10-26 — Roster Architecture & Assignments Console

### 🚀 Added
- **Database Architecture:**
  - Added `locations`, `departments`, `teams`, `user_assignments`, and `audit_logs` tables.
- **Location-Wise Roster Module (`/roster/location`):**
  - Location switcher, department/team filters, and staffing shortage detector.
- **Combined Roster Module (`/roster/combined`):**
  - Multi-location consolidated roster view with headcount metrics.
- **Admin User & Data Assignment Console (`/admin/assignments`):**
  - Permission flags: `can_view`, `can_create`, `can_edit`, `can_approve`, `can_export`.
