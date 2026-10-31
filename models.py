from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from database import Base

class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True) # e.g. Mumbai, Pune, Nagpur, Headquarters
    code = Column(String(20), unique=True, nullable=False, index=True) # e.g. MUM, PUN, NAG, HQ
    address = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    departments = relationship("Department", back_populates="location")
    users = relationship("User", back_populates="work_location")
    assignments = relationship("UserAssignment", back_populates="location")

class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True, index=True)
    name = Column(String(100), nullable=False) # Operations, Quality Audit, IT Support, Human Resources, Billing
    code = Column(String(20), nullable=False) # e.g. OPS, QA, IT, HR, BILL
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    location = relationship("Location", back_populates="departments")
    teams = relationship("Team", back_populates="department")
    users = relationship("User", back_populates="dept_rel")
    assignments = relationship("UserAssignment", back_populates="department")

class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    name = Column(String(100), nullable=False) # e.g. Alpha Response, Billing Audit, Night Operations, Floor Sup A
    code = Column(String(30), nullable=True)
    team_lead_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    department = relationship("Department", back_populates="teams")
    team_lead = relationship("User", foreign_keys=[team_lead_id], back_populates="led_teams")
    members = relationship("User", foreign_keys="User.team_id", back_populates="team_rel")
    assignments = relationship("UserAssignment", back_populates="team")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    unique_id = Column(String(50), unique=True, index=True, nullable=False) # e.g. AIPLCC222
    crm_id = Column(String(50), nullable=True)
    bm_id = Column(String(50), nullable=True)
    ecn = Column(String(50), nullable=True)
    name = Column(String(120), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    role_title = Column(String(80), default="Agent") # e.g. QA Auditor, Senior Agent, Team Leader
    access_level = Column(String(50), default="Employee") # Super Admin, Admin, HR, Location Manager, Team Leader, Roster Coordinator, Employee
    
    # Text fallback legacy fields for direct backward compatibility
    department = Column(String(80), default="Operations")
    location = Column(String(80), default="Mumbai")
    gender = Column(String(20), default="Not Specified")
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    exit_date = Column(Date, nullable=True) # Separation / Exit Date for offboarding
    exit_reason = Column(Text, nullable=True) # Offboarding reason / remarks
    
    # Normalized relationship links (nullable to safeguard legacy records)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True)
    team_lead_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Company Monthly Leave Ledger Fields
    doj = Column(Date, nullable=True) # Date of Joining
    eod = Column(Date, nullable=True) # Confirmation / End of probation date
    eligible_cl = Column(Float, default=12.0)
    eligible_sl = Column(Float, default=9.0)
    taken_cl = Column(Float, default=0.0)
    taken_sl = Column(Float, default=0.0)
    balance_cl = Column(Float, default=12.0)
    balance_sl = Column(Float, default=9.0)
    balance_co = Column(Float, default=0.0)

    # Legacy/Backwards-compatible Quota Fields
    cl_balance = Column(Float, default=12.0)
    sl_balance = Column(Float, default=9.0)
    co_balance = Column(Float, default=0.0)
    pl_balance = Column(Float, default=0.0)
    unpaid_taken = Column(Float, default=0.0)

    # Relationships
    work_location = relationship("Location", back_populates="users", foreign_keys=[location_id])
    dept_rel = relationship("Department", back_populates="users", foreign_keys=[department_id])
    team_rel = relationship("Team", foreign_keys=[team_id], back_populates="members")
    led_teams = relationship("Team", foreign_keys="Team.team_lead_id", back_populates="team_lead")
    assigned_leader = relationship("User", remote_side=[id], foreign_keys=[team_lead_id], backref="subordinates")

    roster_entries = relationship("RosterEntry", back_populates="user", cascade="all, delete-orphan", foreign_keys="RosterEntry.user_id")
    leave_requests = relationship("LeaveRequest", back_populates="user", cascade="all, delete-orphan")
    leave_balances = relationship("LeaveBalance", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

    # Assignment Relationships
    user_assignments = relationship("UserAssignment", foreign_keys="UserAssignment.user_id", back_populates="user", cascade="all, delete-orphan")
    targeted_assignments = relationship("UserAssignment", foreign_keys="UserAssignment.assigned_employee_id", back_populates="assigned_employee")
    assigned_as_leader = relationship("UserAssignment", foreign_keys="UserAssignment.team_lead_id", back_populates="team_lead")
    created_audit_logs = relationship("AuditLog", back_populates="actor")

class UserAssignment(Base):
    """
    Granular Admin-controlled assignments of Locations, Departments, Teams, 
    Team Leaders, and specific Employees with dedicated CRUD/Export permissions.
    """
    __tablename__ = "user_assignments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True) # The user receiving the assignment
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True)
    team_lead_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True) # Optional supervisor mapping
    assigned_employee_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True) # Specific targeted employee

    # Granular Configurable Permissions
    can_view = Column(Boolean, default=True)
    can_create = Column(Boolean, default=False)
    can_edit = Column(Boolean, default=False)
    can_approve = Column(Boolean, default=False)
    can_export = Column(Boolean, default=False)

    # Date validity and lifecycle
    effective_from = Column(Date, nullable=False, default=date.today)
    effective_to = Column(Date, nullable=True) # Nullable = indefinitely active
    status = Column(String(20), default="Active") # Active, Suspended, Revoked, Expired
    notes = Column(Text, nullable=True)
    
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="user_assignments")
    location = relationship("Location", back_populates="assignments")
    department = relationship("Department", back_populates="assignments")
    team = relationship("Team", back_populates="assignments")
    team_lead = relationship("User", foreign_keys=[team_lead_id], back_populates="assigned_as_leader")
    assigned_employee = relationship("User", foreign_keys=[assigned_employee_id], back_populates="targeted_assignments")
    created_by = relationship("User", foreign_keys=[created_by_id])

class AuditLog(Base):
    """
    Tracks every administrative action, permission grant, employee transfer,
    and roster change.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    actor_name = Column(String(120), nullable=True)
    action = Column(String(80), nullable=False, index=True) # ASSIGNMENT_CREATE, ROSTER_UPDATE, EMPLOYEE_TRANSFER, etc.
    resource_type = Column(String(50), nullable=False) # UserAssignment, RosterEntry, User, Team, etc.
    resource_id = Column(String(50), nullable=True)
    details = Column(Text, nullable=True) # JSON or human-readable description
    ip_address = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    actor = relationship("User", back_populates="created_audit_logs")

class LeaveBalance(Base):
    """
    Monthly Leave Balance Report Record
    Direct mapping to company official Leave Balance Statement
    """
    __tablename__ = "leave_balances"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    unique_id = Column(String(50), index=True, nullable=False) # e.g. AIPLCC222
    ecn = Column(String(50), nullable=True, index=True) # e.g. MAH0297
    bm_id = Column(String(50), nullable=True) # e.g. 410055
    name = Column(String(120), nullable=True)
    location = Column(String(80), default="MUMBAI")
    doj = Column(Date, nullable=True) # Date of Joining
    eod = Column(Date, nullable=True) # Confirmation / End of probation date
    month_year = Column(String(30), default="Oct-26") # Statement period, e.g. Oct-26

    # Fractional Leave Quotas & Balances
    eligible_cl = Column(Float, default=0.0)
    eligible_sl = Column(Float, default=0.0)
    taken_cl = Column(Float, default=0.0)
    taken_sl = Column(Float, default=0.0)
    balance_cl = Column(Float, default=0.0)
    balance_sl = Column(Float, default=0.0)
    balance_co = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="leave_balances")

class Shift(Base):
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False) # Morning Shift, General Shift, Afternoon Shift, Night Shift
    code = Column(String(50), nullable=False) # e.g. 07:00 To 16:00
    start_time = Column(String(10), nullable=False) # 07:00
    end_time = Column(String(10), nullable=False) # 16:00
    is_overnight = Column(Boolean, default=False) # e.g. 22:00 to 06:00 next day
    break_duration_mins = Column(Integer, default=60) # Minutes
    color_code = Column(String(30), default="blue") # blue, green, orange, purple, teal, amber, red, grey
    applicable_locations = Column(String(255), default="All") # Comma-separated or 'All'
    effective_from = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True)

class ShiftChangeHistory(Base):
    """
    Audit log for roster shift modifications
    """
    __tablename__ = "shift_change_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    roster_date = Column(Date, nullable=False, index=True)
    previous_shift = Column(String(50), nullable=True)
    new_shift = Column(String(50), nullable=False)
    previous_timings = Column(String(50), nullable=True)
    new_timings = Column(String(50), nullable=True)
    previous_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    new_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    changed_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    changed_by_name = Column(String(120), nullable=False)
    change_reason = Column(Text, nullable=True)
    approval_status = Column(String(30), default="Approved")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    employee = relationship("User", foreign_keys=[user_id])
    modifier = relationship("User", foreign_keys=[changed_by_id])

class RosterViewLog(Base):
    """
    Privacy-conscious roster view tracking log for authorized audit purposes
    """
    __tablename__ = "roster_view_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user_name = Column(String(120), nullable=False)
    user_role = Column(String(50), nullable=True)
    view_type = Column(String(50), nullable=False) # 'Location Roster', 'Combined Roster', 'My Team Roster'
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    location_name = Column(String(80), nullable=True)
    team_context = Column(String(100), nullable=True)
    view_timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    viewer = relationship("User", foreign_keys=[user_id])

class RosterEntry(Base):
    __tablename__ = "roster_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True, index=True)
    date = Column(Date, nullable=False, index=True) # YYYY-MM-DD
    shift_code_or_time = Column(String(50), nullable=False) # "07:00 To 16:00", "09:00 To 18:00", "WO", "CO", "Leave"
    status = Column(String(20), default="Scheduled") # Scheduled, Present, Leave, WO, CO, Absent
    approval_status = Column(String(20), default="Approved") # Approved, Pending Approval, Rejected
    approved_by = Column(String(100), nullable=True)
    version = Column(Integer, default=1)
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="roster_entries", foreign_keys=[user_id])
    location = relationship("Location")

class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True, index=True)
    application_number = Column(String(50), unique=True, index=True, nullable=True) # e.g. LA-20261026-0001
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    leave_type = Column(String(20), nullable=False) # PL, CL, SL, Comp-Off, Unpaid, Half-Day
    day_part = Column(String(20), default="full") # "full" (1.0), "half_first" (0.5), "half_second" (0.5)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    duration_days = Column(Float, default=1.0)
    reason = Column(Text, nullable=False)
    status = Column(String(30), default="Pending Approval") # Draft, Pending Approval, Under Review, Approved, Rejected, Cancellation Requested, Cancelled, Withdrawn
    reviewer_comment = Column(Text, nullable=True)
    reviewed_by = Column(String(100), nullable=True)
    
    # Cancellation & Amendment Tracking
    cancellation_reason = Column(Text, nullable=True)
    cancellation_requested_at = Column(DateTime, nullable=True)
    cancelled_by = Column(String(100), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="leave_requests")
    attachments = relationship("LeaveAttachment", back_populates="leave_request", cascade="all, delete-orphan")
    history_records = relationship("LeaveHistory", back_populates="leave_request", cascade="all, delete-orphan")

class LeaveAttachment(Base):
    """
    Supporting evidence documents: medical bills, prescriptions, medical certificates, invitation cards, etc.
    """
    __tablename__ = "leave_attachments"

    id = Column(Integer, primary_key=True, index=True)
    leave_request_id = Column(Integer, ForeignKey("leave_requests.id"), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    stored_path = Column(String(500), nullable=False)
    file_type = Column(String(50), nullable=False) # pdf, jpg, jpeg, png
    file_size_bytes = Column(Integer, nullable=True)
    doc_category = Column(String(80), default="Medical / Supporting Evidence")
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True) # Soft delete/replacement flag
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    leave_request = relationship("LeaveRequest", back_populates="attachments")
    uploader = relationship("User")

class LeaveHistory(Base):
    """
    Immutable audit history of leave applications (edits, amendments, approvals, cancellation requests).
    """
    __tablename__ = "leave_history"

    id = Column(Integer, primary_key=True, index=True)
    leave_request_id = Column(Integer, ForeignKey("leave_requests.id"), nullable=False, index=True)
    action = Column(String(80), nullable=False) # APPLIED, EDITED, APPROVED, REJECTED, CANCEL_REQUESTED, CANCELLED, WITHDRAWN
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    actor_name = Column(String(120), nullable=True)
    previous_state = Column(Text, nullable=True) # JSON snapshot of previous dates/status
    new_state = Column(Text, nullable=True) # JSON snapshot of new dates/status
    remarks = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    leave_request = relationship("LeaveRequest", back_populates="history_records")
    actor = relationship("User")

class Holiday(Base):
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    date = Column(Date, nullable=False, unique=True)
    optional_flag = Column(Boolean, default=False)

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    category = Column(String(50), default="general") # shift_change, leave_status, announcement
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")

class UserPreference(Base):
    """
    Per-user preferences including custom pinned navigation shortcuts,
    theme settings, and sidebar configuration.
    """
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    sidebar_pinned = Column(Text, nullable=True) # JSON list of module IDs: ["dashboard", "roster", "attendance_swaps", "leaves"]
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")

class CompanySetting(Base):
    """
    Global 24/7 Enterprise rules, shift rotations, holiday compensatory policies,
    and leave quota limits.
    """
    __tablename__ = "company_settings"

    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String(80), unique=True, nullable=False, index=True)
    setting_value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
    category = Column(String(50), default="24x7_rules") # 24x7_rules, quotas, holidays, shifts
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserSessionLog(Base):
    """
    Automatic Login and Logout Tracking with Session Duration and IP/Browser device info.
    """
    __tablename__ = "user_session_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    login_time = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    logout_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, default=0) # Total active seconds between login and logout
    ip_address = Column(String(60), nullable=True)
    user_agent = Column(String(255), nullable=True)
    is_active_session = Column(Boolean, default=True) # True while user is still logged in
    
    user = relationship("User")

class WorkSession(Base):
    """
    Shift Work & Break Tracker for employees (Web Start Shift, Breaks, End Shift).
    """
    __tablename__ = "work_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True)
    session_date = Column(Date, nullable=False, index=True) # Operational date
    
    # Session Timestamps
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    
    # Calculated Minutes
    gross_duration_mins = Column(Integer, default=0)
    total_break_mins = Column(Integer, default=0)
    net_work_mins = Column(Integer, default=0)
    late_arrival_mins = Column(Integer, default=0)
    overtime_mins = Column(Integer, default=0)
    
    # Status: 'ACTIVE', 'ON_BREAK', 'COMPLETED'
    status = Column(String(30), default="ACTIVE", index=True)
    
    # Manager Sign-off
    is_verified = Column(Boolean, default=False)
    verified_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    manager_notes = Column(String(255), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    shift = relationship("Shift", foreign_keys=[shift_id])
    breaks = relationship("SessionBreak", back_populates="session", cascade="all, delete-orphan")

class SessionBreak(Base):
    """
    Individual break intervals within an active shift work session (Lunch, Tea, Auxiliary).
    """
    __tablename__ = "session_breaks"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("work_sessions.id"), nullable=False, index=True)
    break_type = Column(String(50), nullable=False) # 'Lunch', 'Tea', 'Auxiliary'
    start_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_mins = Column(Integer, default=0)
    is_excess = Column(Boolean, default=False)

    session = relationship("WorkSession", back_populates="breaks")




