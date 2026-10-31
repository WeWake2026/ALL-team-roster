# Changelog — ShiftFlow Pro Upgrade
 
All notable changes to the ShiftFlow Pro application are documented in this file.

## [2.1.0] - 2026-10-26 — Comprehensive Leave Management System Upgrade

### 🚀 Added
- **Leave Application Engine (`/leaves/apply`):**
  - Unique Leave Application ID generation (`LA-YYYYMMDD-XXXX`).
  - Multi-file evidence attachment support (medical certificates, bills, prescriptions, invitation cards).
  - Configurable document categorization (`Medical Certificate / Doctor Note`, `Medical Bill / Prescription`, `Hospital Discharge Summary`, `Invitation / Marriage Card`, etc.).
  - Overlap detection preventing duplicate or overlapping requests on existing active leave periods.
  - Duration calculation engine supporting full-day (1.0) and half-day (0.5) deductions with balance pre-validation.
- **Application Amendment / Edit Workflow (`/leaves/edit`):**
  - Edit modal for eligible applications (Draft, Pending Approval, Rejected).
  - Restriction on direct modification of Approved leave (requires supervisor cancellation/resubmission).
  - Snapshot auditing before and after edits in `leave_history`.
- **Cancellation & Withdrawal Engine (`/leaves/cancel`):**
  - Instant direct withdrawal for Pending / Draft / Under Review applications.
  - Multi-step cancellation request workflow for Approved leave.
  - Modal prompt with mandatory cancellation justification.
  - Automatic balance refunding and roster restoration upon cancellation approval (`Scheduled` / `09:00 To 18:00`).
- **Secure Confidential Evidence Vault (`/leaves/evidence/{attachment_id}`):**
  - Protected binary streaming endpoint with access control (applicant and authorized reviewers only).
  - No direct or public URL file exposure.
  - Supported file formats: PDF, JPG, JPEG, PNG.
- **Audit History & Compliance Modal (`/leaves/{request_id}/details`):**
  - Chronological timeline tracking `APPLIED`, `EDITED`, `APPROVED`, `REJECTED`, `CANCEL_REQUESTED`, `CANCELLED`, `WITHDRAWN`.
- **Self-Approval Guard:**
  - Strict server-side validation ensuring managers and team leaders cannot approve their own leave applications.

---

## [2.0.0] - 2026-10-26

### 🚀 Added
- **Database Architecture:**
  - Added `locations`, `departments`, `teams`, `user_assignments`, and `audit_logs` tables.
  - Linked `users` table to `location_id`, `department_id`, `team_id`, and `team_lead_id`.
  - Linked `roster_entries` table to `location_id`, `approval_status`, `approved_by`, and `version`.
- **Location-Wise Roster Module (`/roster/location`):**
  - Location switcher for all authorized work locations.
  - Department, team, and shift filters with dynamic instant client-side updates.
  - Staffing shortage detector identifying days with fewer than 5 active staff members.
  - Inline interactive modal for quick shift modification with permission enforcement.
- **Combined Roster Module (`/roster/combined`):**
  - Multi-location consolidated roster view.
  - Location comparison metric cards showing real-time headcount per center.
  - Cross-location search and multi-criteria filtering.
- **Admin User & Data Assignment Console (`/admin/assignments`):**
  - Interface for assigning users to locations, departments, teams, team leaders, and specific employees.
  - Granular permission flags: `can_view`, `can_create`, `can_edit`, `can_approve`, `can_export`.
  - Effective date validity management (`effective_from`, `effective_to`).
  - Temporary suspension and permanent revocation workflows.
- **Audit Logs Module (`/audit-logs`):**
  - Persistent immutable audit log console tracking assignment grants, suspensions, and modifications.
- **Reports & Analytics Module (`/reports`):**
  - Executive KPI cards for active staff, scheduled today, on leave, and week-offs.
  - Location-wise headcount distribution with visual progress bars.
  - Shift-wise headcount breakdown and export links.
- **Automated Test Suite (`run_audit_tests.py`):**
  - Automated integration and security tests validating RBAC, IDOR prevention, assignment scoping, and roster data integrity.

### 🛡️ Security Fixes
- Added server-side IDOR prevention rejecting requests for unassigned locations with `HTTP 403 Forbidden`.
- Implemented least-privilege scoping ensuring Team Leaders only access assigned direct reports.
- Added persistent audit logging for administrative mutations.

### 💾 Preserved Data
- 100% of existing users (including `ADMIN001` and all 38 employees) preserved.
- 100% of existing historical roster entries (497 entries) preserved and mapped to location references.
- Created point-in-time safety database backup: `shiftflow_backup_20261026.db`.
