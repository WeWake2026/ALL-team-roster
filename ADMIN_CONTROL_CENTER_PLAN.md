# Implementation Plan - Complete Enterprise Admin Control Center

Build the enterprise-level **Admin Control Center** for ShiftFlow Employee Roster Management System supporting the exact 7-tier organizational hierarchy:
$$\text{Organization} \rightarrow \text{Global Settings} \rightarrow \text{Location} \rightarrow \text{Branch} \rightarrow \text{Department} \rightarrow \text{Team} \rightarrow \text{Employee}$$

---

### Phase 1: Database Architecture & Safe Migrations
Extend the existing SQLite database without resetting or altering historical data:
1. `organizations`: Organization profile, logo, code, email, contact, address, timezone, date_format, financial_year.
2. `branches`: Branches under locations (`location_id`, `name`, `code`, `address`, `manager_id`, `is_active`, `created_at`).
3. `employee_transfer_history`: Track movements across locations, branches, departments, teams, managers with effective dates and audit trails.
4. `config_overrides`: Multi-tier configuration inheritance (`scope_level`: GLOBAL, LOCATION, BRANCH, TEAM, EMPLOYEE, `scope_id`, `key`, `value`, `is_customized`, `updated_by`).
5. Update `users` table to link `branch_id`, `reporting_manager_id`, `employment_status` ('ACTIVE', 'NOTICE_PERIOD', 'RESIGNED', 'TERMINATED'), `last_working_date`.
6. Update `models.py` with corresponding SQLAlchemy models and relationships.

---

### Phase 2: Role-Based & Scope-Based Authorization Engine
Enhance `auth.py`:
- Support all roles: Super Admin, Admin, Location Admin, Branch Manager, Department Manager, Team Leader, HR, Employee.
- Enforce data visibility boundaries:
  - Super Admin: Universal access.
  - Location Admin: Assigned location and its branches.
  - Branch Manager: Assigned branch only.
  - Department Manager: Assigned department only.
  - Team Leader: Assigned team only.
  - Employee: Self-only.

---

### Phase 3: Admin Control Center Unified Dashboard & Navigation
1. Create `/admin/control-center` with full enterprise sidebar navigation covering all 21 modules:
   - Overview & Workforce Metrics
   - Organization Profile & Global Configuration
   - Location Management (Add/Edit/Status/Copy Config)
   - Branch Management (Add/Edit/Assign Teams)
   - Department & Team Management
   - Employee Directory & Status Lifecycle
   - Shift Master & Rotations
   - Location-Wise Roster Settings
   - Monthly Roster Operations
   - Attendance Engine & Grace Periods
   - Leave Policies & Approval Workflows
   - Holiday Calendars
   - Employee Transfer Center
   - Workforce Reports (Individual vs Aggregated)
   - Notifications & Email SMTP
   - Bulk Excel Import / Export
   - Admin Activity Audit Trail
   - System Diagnostics & Database Health
2. Modern, responsive dashboard cards, filters (Location, Branch, Dept, Team, Shift, Status, Date Range), and real database counts.

---

### Phase 4: Implementation of Backend Services & Handlers
In `admin_control_service.py` and `main.py`:
- Complete CRUD operations for Organizations, Branches, Locations, Departments, Teams, Shifts, and Transfers.
- Location Override inheritance resolver (Global -> Location -> Branch -> Team -> Employee).
- Database backup snapshot and health metrics.

---

### Phase 5: Verification & Automated Tests
- Test Super Admin universal control.
- Test Location Admin restricted to Mumbai or Nagpur.
- Test Branch Manager and Team Leader isolation.
- Test Employee restriction (cannot access Admin Control Center).
- Verify roster generation, holiday isolation, and Excel/PDF report exports.
