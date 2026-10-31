# Database Architecture & Migration Guide

## 1. Schema Overview

ShiftFlow Pro uses a normalized relational architecture compatible with both SQLite and PostgreSQL.

### Core Tables & Entity Relationships

1. `locations`:
   - `id`: INTEGER PRIMARY KEY AUTOINCREMENT
   - `name`: VARCHAR(100) UNIQUE (e.g., 'Mumbai', 'Pune', 'Nagpur', 'Headquarters')
   - `code`: VARCHAR(20) UNIQUE (e.g., 'MUM', 'PUN', 'NAG', 'HQ')
   - `address`: TEXT
   - `is_active`: BOOLEAN DEFAULT 1

2. `departments`:
   - `id`: INTEGER PRIMARY KEY
   - `location_id`: FOREIGN KEY -> `locations.id`
   - `name`: VARCHAR(100)
   - `code`: VARCHAR(20)

3. `teams`:
   - `id`: INTEGER PRIMARY KEY
   - `department_id`: FOREIGN KEY -> `departments.id`
   - `name`: VARCHAR(100)
   - `team_lead_id`: FOREIGN KEY -> `users.id`

4. `users`:
   - `id`: INTEGER PRIMARY KEY
   - `unique_id`: VARCHAR(50) UNIQUE (e.g., `AIPLCC175`)
   - `name`: VARCHAR(120)
   - `email`: VARCHAR(120) UNIQUE
   - `access_level`: VARCHAR(50) ('Super Admin', 'Admin', 'HR', 'Location Manager', 'Team Leader', 'Employee')
   - `location_id`: FOREIGN KEY -> `locations.id`
   - `department_id`: FOREIGN KEY -> `departments.id`
   - `team_id`: FOREIGN KEY -> `teams.id`
   - `team_lead_id`: FOREIGN KEY -> `users.id`
   - `hashed_password`: VARCHAR(255)
   - `is_active`: BOOLEAN DEFAULT 1

5. `user_assignments`:
   - `id`: INTEGER PRIMARY KEY
   - `user_id`: FOREIGN KEY -> `users.id`
   - `location_id`: FOREIGN KEY -> `locations.id`
   - `department_id`: FOREIGN KEY -> `departments.id`
   - `team_id`: FOREIGN KEY -> `teams.id`
   - `team_lead_id`: FOREIGN KEY -> `users.id`
   - `assigned_employee_id`: FOREIGN KEY -> `users.id`
   - `can_view`, `can_create`, `can_edit`, `can_approve`, `can_export`: BOOLEAN
   - `effective_from`, `effective_to`: DATE
   - `status`: VARCHAR(20) ('Active', 'Suspended', 'Revoked')

6. `roster_entries`:
   - `id`: INTEGER PRIMARY KEY
   - `user_id`: FOREIGN KEY -> `users.id`
   - `location_id`: FOREIGN KEY -> `locations.id`
   - `date`: DATE (YYYY-MM-DD)
   - `shift_code_or_time`: VARCHAR(50)
   - `status`: VARCHAR(20)
   - `approval_status`: VARCHAR(20) DEFAULT 'Approved'
   - `version`: INTEGER DEFAULT 1

7. `leave_requests`:
   - `id`: INTEGER PRIMARY KEY AUTOINCREMENT
   - `application_number`: VARCHAR(50) UNIQUE (e.g., `LA-20261026-0001`)
   - `user_id`: FOREIGN KEY -> `users.id`
   - `leave_type`: VARCHAR(20) ('CL', 'SL', 'Comp-Off', 'PL', 'Unpaid')
   - `day_part`: VARCHAR(20) ('full', 'half_first', 'half_second')
   - `start_date`, `end_date`: DATE
   - `duration_days`: FLOAT (supports 0.5 fractional days)
   - `reason`: TEXT
   - `status`: VARCHAR(30) ('Draft', 'Pending Approval', 'Under Review', 'Approved', 'Rejected', 'Cancellation Requested', 'Cancelled', 'Withdrawn')
   - `reviewer_comment`: TEXT
   - `reviewed_by`: VARCHAR(100)
   - `cancellation_reason`: TEXT
   - `cancellation_requested_at`, `cancelled_at`: DATETIME
   - `cancelled_by`: VARCHAR(100)
   - `created_at`, `updated_at`, `reviewed_at`: DATETIME

8. `leave_attachments`:
   - `id`: INTEGER PRIMARY KEY AUTOINCREMENT
   - `leave_request_id`: FOREIGN KEY -> `leave_requests.id`
   - `file_name`: VARCHAR(255)
   - `stored_path`: VARCHAR(500)
   - `file_type`: VARCHAR(50) ('pdf', 'jpg', 'jpeg', 'png')
   - `file_size_bytes`: INTEGER
   - `doc_category`: VARCHAR(80) (Medical Certificate, Bill, Prescription, Invitation, etc.)
   - `uploaded_by_id`: FOREIGN KEY -> `users.id`
   - `is_active`: BOOLEAN DEFAULT 1
   - `uploaded_at`: DATETIME DEFAULT CURRENT_TIMESTAMP

9. `leave_history`:
   - `id`: INTEGER PRIMARY KEY AUTOINCREMENT
   - `leave_request_id`: FOREIGN KEY -> `leave_requests.id`
   - `action`: VARCHAR(80) ('APPLIED', 'EDITED', 'APPROVED', 'REJECTED', 'CANCEL_REQUESTED', 'CANCELLED', 'WITHDRAWN')
   - `actor_id`: FOREIGN KEY -> `users.id`
   - `actor_name`: VARCHAR(120)
   - `previous_state`, `new_state`: TEXT (JSON serialized snapshots)
   - `remarks`: TEXT
   - `timestamp`: DATETIME DEFAULT CURRENT_TIMESTAMP

10. `audit_logs`:
   - `id`: INTEGER PRIMARY KEY
   - `actor_id`: FOREIGN KEY -> `users.id`
   - `action`: VARCHAR(80)
   - `resource_type`: VARCHAR(50)
   - `resource_id`: VARCHAR(50)
   - `details`: TEXT
   - `ip_address`: VARCHAR(50)
   - `timestamp`: DATETIME DEFAULT CURRENT_TIMESTAMP

11. `shifts`:
   - `id`: INTEGER PRIMARY KEY AUTOINCREMENT
   - `name`: VARCHAR(50) (e.g., 'Morning Shift', 'General Shift', 'Afternoon Shift', 'Night Shift')
   - `code`: VARCHAR(50) (e.g., '07:00 To 16:00')
   - `start_time`: VARCHAR(10) ('07:00')
   - `end_time`: VARCHAR(10) ('16:00')
   - `is_overnight`: BOOLEAN DEFAULT 0 (True for shifts spanning midnight, e.g. 22:00 to 06:00)
   - `break_duration_mins`: INTEGER DEFAULT 45
   - `color_code`: VARCHAR(30) ('blue', 'green', 'orange', 'purple', etc.)
   - `applicable_locations`: VARCHAR(255) ('All' or comma-separated location names)
   - `effective_from`: DATE
   - `is_active`: BOOLEAN DEFAULT 1

12. `shift_change_history`:
   - `id`: INTEGER PRIMARY KEY AUTOINCREMENT
   - `user_id`: FOREIGN KEY -> `users.id` (Target Employee)
   - `roster_date`: DATE (Target roster date)
   - `previous_shift`, `new_shift`: VARCHAR(50)
   - `previous_timings`, `new_timings`: VARCHAR(50)
   - `previous_location_id`, `new_location_id`: FOREIGN KEY -> `locations.id`
   - `changed_by_id`: FOREIGN KEY -> `users.id`
   - `changed_by_name`: VARCHAR(120)
   - `change_reason`: TEXT
   - `approval_status`: VARCHAR(30) DEFAULT 'Approved'
   - `created_at`: DATETIME DEFAULT CURRENT_TIMESTAMP

13. `roster_view_logs`:
   - `id`: INTEGER PRIMARY KEY AUTOINCREMENT
   - `user_id`: FOREIGN KEY -> `users.id`
   - `user_name`: VARCHAR(120)
   - `user_role`: VARCHAR(50)
   - `view_type`: VARCHAR(50) ('Location Roster', 'Combined Roster', 'My Team Roster')
   - `location_id`: FOREIGN KEY -> `locations.id`
   - `location_name`: VARCHAR(80)
   - `team_context`: VARCHAR(100)
   - `view_timestamp`: DATETIME DEFAULT CURRENT_TIMESTAMP

---

## 2. Safe Migration Procedure

The migration scripts `migrate_db.py`, `migrate_leaves.py`, and `migrate_shifts_and_tracking.py` use idempotent SQL statements:
- Uses `CREATE TABLE IF NOT EXISTS` for all structural tables.
- Checks `PRAGMA table_info` before applying `ALTER TABLE ADD COLUMN`.
- Configures default shift colors: Morning (Blue), General (Green), Afternoon (Orange), Night (Purple - Overnight).
- Backfills team memberships and links Team Leaders without rewriting historical roster schedules.
- Preserves all employee IDs, active roster entries, and leave records.
