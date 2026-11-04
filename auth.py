import os
import hashlib
from datetime import date
from typing import Optional, List, Set, Tuple, Dict, Any
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from database import get_db
import models

# ----------------- PASSWORDS & HASHING (ARGON2 / BCRYPT WITH BACKWARD COMPATIBILITY) ----------------- #
import bcrypt

SALT_SHA256 = "msedcl_shiftflow_secure_salt_2026"

def get_password_hash(password: str) -> str:
    """Generate secure Bcrypt hash (work factor 12)"""
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def needs_rehash(hashed_password: str) -> bool:
    """Check if hash is legacy SHA-256 or plain text that requires upgrading to Bcrypt"""
    if not hashed_password:
        return True
    return not (hashed_password.startswith("$2b$") or hashed_password.startswith("$2a$") or hashed_password.startswith("$2y$"))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against Bcrypt hash, fallback to legacy SHA-256 salted hash or plain text"""
    if not hashed_password or not plain_password:
        return False
    # 1. Bcrypt check
    if hashed_password.startswith(("$2b$", "$2a$", "$2y$")):
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception:
            return False
    # 2. Legacy salted SHA-256 fallback
    legacy_sha = hashlib.sha256((plain_password + SALT_SHA256).encode('utf-8')).hexdigest()
    if legacy_sha == hashed_password:
        return True
    # 3. Plain text legacy fallback
    return plain_password == hashed_password

# ----------------- SESSION AUTH ----------------- #

def get_current_user_from_cookie(request: Request, db: Session = Depends(get_db)) -> Optional[models.User]:
    """Retrieve logged in user from cookie session"""
    user_id = request.cookies.get("user_id")
    if not user_id:
        return None
    try:
        uid = int(user_id)
        user = db.query(models.User).filter(models.User.id == uid, models.User.is_active == True).first()
        return user
    except Exception:
        return None

def require_auth(request: Request, db: Session = Depends(get_db)) -> models.User:
    """Dependency that ensures user is authenticated"""
    user = get_current_user_from_cookie(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"Location": "/login"}
        )
    return user

# ----------------- RBAC & ASSIGNMENT PERMISSION RESOLVER ----------------- #

class UserPermissions:
    """
    Resolved permissions and organizational scopes for a user
    """
    def __init__(
        self,
        user: models.User,
        is_super_admin: bool,
        is_admin: bool,
        is_hr: bool,
        is_manager: bool,
        is_team_leader: bool,
        is_employee: bool,
        location_ids: Set[int],
        department_ids: Set[int],
        team_ids: Set[int],
        assigned_employee_ids: Set[int],
        can_view_all: bool,
        can_create: bool,
        can_edit: bool,
        can_approve: bool,
        can_export: bool,
        active_assignments: List[models.UserAssignment],
        is_quality: bool = False,
        is_sme: bool = False
    ):
        self.user = user
        self.is_super_admin = is_super_admin
        self.is_admin = is_admin
        self.is_hr = is_hr
        self.is_manager = is_manager
        self.is_team_leader = is_team_leader
        self.is_employee = is_employee
        self.is_quality = is_quality
        self.is_sme = is_sme
        self.location_ids = location_ids
        self.department_ids = department_ids
        self.team_ids = team_ids
        self.assigned_employee_ids = assigned_employee_ids
        self.can_view_all = can_view_all
        self.can_create = can_create
        self.can_edit = can_edit
        self.can_approve = can_approve
        self.can_export = can_export
        self.active_assignments = active_assignments

    def can_access_location(self, location_id: Optional[int]) -> bool:
        if self.can_view_all or self.is_admin or self.is_super_admin:
            return True
        if not location_id:
            return False
        return location_id in self.location_ids

    def can_access_employee(self, target_employee_id: int) -> bool:
        if self.can_view_all or self.is_admin or self.is_super_admin:
            return True
        if self.user.id == target_employee_id:
            return True
        if target_employee_id in self.assigned_employee_ids:
            return True
        return False

def resolve_user_permissions(user: models.User, db: Session) -> UserPermissions:
    """
    Computes exact effective permissions based on Role and active UserAssignment records.
    Implements least-privilege access and denies access by default.
    """
    role = (user.access_level or "Employee").strip()
    role_title_clean = (user.role_title or "").strip().upper()

    is_super_admin = role in ["Super Admin"]
    is_admin = role in ["Super Admin", "Admin"]
    is_hr = role == "HR"
    is_manager = role in ["Location Manager", "Operations Manager", "Manager"]
    is_team_leader = role in ["Team Leader", "Team Lead", "TL"] or "LEAD" in role_title_clean or "TL" in role_title_clean
    is_quality = role in ["Quality", "QA", "Quality Lead"] or "QA" in role_title_clean or "QUALITY" in role_title_clean
    is_sme = role in ["SME", "Subject Matter Expert"] or "SME" in role_title_clean
    is_employee = not (is_admin or is_manager or is_hr or is_team_leader or is_quality or is_sme)

    # Admins and Super Admins have universal visibility by default
    if is_admin:
        all_locs = {loc.id for loc in db.query(models.Location.id).all()}
        all_depts = {d.id for d in db.query(models.Department.id).all()}
        all_teams = {t.id for t in db.query(models.Team.id).all()}
        all_emps = {u.id for u in db.query(models.User.id).all()}
        return UserPermissions(
            user=user,
            is_super_admin=is_super_admin,
            is_admin=True,
            is_hr=False,
            is_manager=True,
            is_team_leader=True,
            is_employee=False,
            location_ids=all_locs,
            department_ids=all_depts,
            team_ids=all_teams,
            assigned_employee_ids=all_emps,
            can_view_all=True,
            can_create=True,
            can_edit=True,
            can_approve=True,
            can_export=True,
            active_assignments=[]
        )

    # For HR, Location Manager, Team Leader, Coordinator, Employee:
    # Query explicit active UserAssignment rows
    today = date.today()
    assignments = db.query(models.UserAssignment).filter(
        models.UserAssignment.user_id == user.id,
        models.UserAssignment.status == "Active",
        models.UserAssignment.effective_from <= today,
        or_(models.UserAssignment.effective_to == None, models.UserAssignment.effective_to >= today)
    ).all()

    location_ids: Set[int] = set()
    department_ids: Set[int] = set()
    team_ids: Set[int] = set()
    assigned_employee_ids: Set[int] = {user.id} # Always own employee ID

    can_create = False
    can_edit = False
    can_approve = False
    can_export = False

    # Also include the user's home location/department
    if user.location_id:
        location_ids.add(user.location_id)
    if user.department_id:
        department_ids.add(user.department_id)
    if user.team_id:
        team_ids.add(user.team_id)

    # Process all active assignments
    for a in assignments:
        if a.location_id:
            location_ids.add(a.location_id)
        if a.department_id:
            department_ids.add(a.department_id)
        if a.team_id:
            team_ids.add(a.team_id)
        if a.assigned_employee_id:
            assigned_employee_ids.add(a.assigned_employee_id)
        
        can_create = can_create or bool(a.can_create)
        can_edit = can_edit or bool(a.can_edit)
        can_approve = can_approve or bool(a.can_approve)
        can_export = can_export or bool(a.can_export)

    # Role default baselines:
    if is_hr:
        # HR has create, edit, approve, and export within assigned scope
        can_create = True
        can_edit = True
        can_approve = True
        can_export = True
        # If no explicit assignment restricts HR, default to all authorized company locations
        if not assignments:
            location_ids = {loc.id for loc in db.query(models.Location.id).all()}
            department_ids = {d.id for d in db.query(models.Department.id).all()}

    elif is_manager:
        # Location Manager can edit, approve, export in assigned locations
        can_create = True
        can_edit = True
        can_approve = True
        can_export = True

    elif is_team_leader:
        # Team Leader can manage teams they lead directly or are assigned to
        led_teams = db.query(models.Team).filter(models.Team.team_lead_id == user.id).all()
        for lt in led_teams:
            team_ids.add(lt.id)
            if lt.department_id:
                department_ids.add(lt.department_id)

        # Team leader assigned direct reports
        subordinates = db.query(models.User.id).filter(
            or_(
                models.User.team_lead_id == user.id,
                models.User.team_id.in_(team_ids) if team_ids else False
            )
        ).all()
        for sub in subordinates:
            assigned_employee_ids.add(sub[0])

        # TL default permissions
        can_edit = can_edit or True

    elif is_quality:
        # QA / Quality Lead can audit rosters across operational teams and view reports
        can_view_all = False
        can_export = True
        can_create = False
        can_edit = False
        can_approve = False

    elif is_sme:
        # Subject Matter Expert has extended visibility for skill & roster support
        can_view_all = False
        can_export = True
        can_create = False
        can_edit = False
        can_approve = False

    # Build employee list from assigned teams/departments if no specific employee was specified
    if team_ids:
        team_members = db.query(models.User.id).filter(models.User.team_id.in_(team_ids)).all()
        for tm in team_members:
            assigned_employee_ids.add(tm[0])

    if is_hr and not assignments:
        assigned_employee_ids = {u.id for u in db.query(models.User.id).all()}
    elif is_manager:
        mgr_emps = db.query(models.User.id).filter(models.User.location_id.in_(location_ids)).all()
        for me in mgr_emps:
            assigned_employee_ids.add(me[0])

    return UserPermissions(
        user=user,
        is_super_admin=is_super_admin,
        is_admin=is_admin,
        is_hr=is_hr,
        is_manager=is_manager,
        is_team_leader=is_team_leader,
        is_employee=is_employee,
        is_quality=is_quality,
        is_sme=is_sme,
        location_ids=location_ids,
        department_ids=department_ids,
        team_ids=team_ids,
        assigned_employee_ids=assigned_employee_ids,
        can_view_all=False,
        can_create=can_create,
        can_edit=can_edit,
        can_approve=can_approve,
        can_export=can_export,
        active_assignments=assignments
    )

# ----------------- ROUTE DEPENDENCIES ----------------- #

def get_user_perms(
    request: Request,
    user: models.User = Depends(require_auth),
    db: Session = Depends(get_db)
) -> UserPermissions:
    """Dependency that returns the fully resolved UserPermissions object"""
    return resolve_user_permissions(user, db)

def require_admin(
    user: models.User = Depends(require_auth),
    perms: UserPermissions = Depends(get_user_perms)
) -> models.User:
    """Admin or Super Admin only"""
    if not perms.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to System Administrators only."
        )
    return user

def require_admin_or_hr(
    user: models.User = Depends(require_auth),
    perms: UserPermissions = Depends(get_user_perms)
) -> models.User:
    """Admin or HR only"""
    if not (perms.is_admin or perms.is_hr):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to HR and Administrators."
        )
    return user

def require_roster_editor(
    user: models.User = Depends(require_auth),
    perms: UserPermissions = Depends(get_user_perms)
) -> models.User:
    """Users with roster editing permissions (Admin, HR, Manager, authorized TL)"""
    if not (perms.is_admin or perms.can_edit):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit roster schedules."
        )
    return user

def require_admin_or_manager(
    user: models.User = Depends(require_auth),
    perms: UserPermissions = Depends(get_user_perms)
) -> models.User:
    """Admin, Manager, HR, Team Leader, Quality (QA), or SME routes"""
    if not (perms.is_admin or perms.is_manager or perms.is_hr or perms.is_team_leader or perms.is_quality or perms.is_sme):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to Authorized Operational Staff (Admin, Manager, Team Leader, Quality, SME)."
        )
    return user

# ----------------- AUDIT LOGGING HELPER ----------------- #

def log_audit_event(
    db: Session,
    actor: Optional[models.User],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None
):
    """
    Records an immutable audit entry in the audit_logs table
    """
    try:
        log_entry = models.AuditLog(
            actor_id=actor.id if actor else None,
            actor_name=actor.name if actor else "System",
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=details,
            ip_address=ip_address
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        print(f"Failed to record audit log: {e}")
