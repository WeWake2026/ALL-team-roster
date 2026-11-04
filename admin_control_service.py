"""
Enterprise Admin Control Center Service
Handles multi-tier organizational hierarchy:
Organization -> Global Settings -> Location -> Branch -> Department -> Team -> Employee
"""

from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional
import json
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
import models

def get_effective_config(
    key: str,
    db: Session,
    location_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    team_id: Optional[int] = None,
    user_id: Optional[int] = None,
    default_val: str = ""
) -> Dict[str, Any]:
    """
    Inheritance resolution priority:
    1. Employee-specific override
    2. Team override
    3. Branch override
    4. Location override
    5. Global organization setting
    6. System fallback default
    """
    levels = []
    if user_id:
        levels.append(("EMPLOYEE", user_id))
    if team_id:
        levels.append(("TEAM", team_id))
    if branch_id:
        levels.append(("BRANCH", branch_id))
    if location_id:
        levels.append(("LOCATION", location_id))
    levels.append(("GLOBAL", 0))

    # Check database configuration_overrides
    for scope_level, scope_id in levels:
        override = db.query(models.ConfigurationOverride).filter(
            models.ConfigurationOverride.scope_level == scope_level,
            models.ConfigurationOverride.scope_id == scope_id,
            models.ConfigurationOverride.setting_key == key
        ).first()
        if override:
            return {
                "key": key,
                "value": override.setting_value,
                "scope_level": scope_level,
                "scope_id": scope_id,
                "is_customized": override.is_customized,
                "updated_at": override.updated_at
            }

    # Check company_settings table
    cs = db.query(models.CompanySetting).filter(models.CompanySetting.setting_key == key).first()
    if cs:
        return {
            "key": key,
            "value": cs.setting_value,
            "scope_level": "GLOBAL",
            "scope_id": 0,
            "is_customized": False,
            "updated_at": cs.updated_at
        }

    return {
        "key": key,
        "value": default_val,
        "scope_level": "SYSTEM_DEFAULT",
        "scope_id": 0,
        "is_customized": False,
        "updated_at": None
    }

def set_config_override(
    scope_level: str,
    scope_id: int,
    key: str,
    value: str,
    user_id: int,
    db: Session,
    category: str = "GENERAL"
):
    """Upsert a configuration override at a specific organizational scope"""
    rec = db.query(models.ConfigurationOverride).filter(
        models.ConfigurationOverride.scope_level == scope_level,
        models.ConfigurationOverride.scope_id == scope_id,
        models.ConfigurationOverride.setting_key == key
    ).first()

    if not rec:
        rec = models.ConfigurationOverride(
            scope_level=scope_level,
            scope_id=scope_id,
            setting_key=key,
            setting_value=value,
            setting_category=category,
            is_customized=True,
            last_modified_by=user_id
        )
        db.add(rec)
    else:
        rec.setting_value = value
        rec.is_customized = True
        rec.last_modified_by = user_id
        rec.updated_at = datetime.utcnow()
    db.commit()
    return rec

def get_workforce_kpis(db: Session, location_id: Optional[int] = None, branch_id: Optional[int] = None) -> Dict[str, Any]:
    """Computes comprehensive live workforce metrics across the enterprise"""
    today = date.today()

    query = db.query(models.User)
    if location_id:
        query = query.filter(models.User.location_id == location_id)
    if branch_id:
        query = query.filter(models.User.branch_id == branch_id)

    all_users = query.all()
    total_employees = len(all_users)
    active_employees = sum(1 for u in all_users if u.is_active and getattr(u, 'employment_status', 'ACTIVE') == 'ACTIVE')
    inactive_employees = sum(1 for u in all_users if not u.is_active or getattr(u, 'employment_status', 'ACTIVE') in ['INACTIVE', 'TERMINATED'])
    resigned_employees = sum(1 for u in all_users if getattr(u, 'employment_status', 'ACTIVE') == 'RESIGNED')
    notice_period = sum(1 for u in all_users if getattr(u, 'employment_status', 'ACTIVE') == 'NOTICE_PERIOD')
    
    # New joiners (joined within last 30 days)
    thirty_days_ago = today - timedelta(days=30)
    new_joiners = sum(1 for u in all_users if u.doj and u.doj >= thirty_days_ago)

    # Today's operational presence, shifts, leaves, and week offs
    user_ids = [u.id for u in all_users]
    today_roster = db.query(models.RosterEntry).filter(
        models.RosterEntry.date == today,
        models.RosterEntry.user_id.in_(user_ids)
    ).all() if user_ids else []

    today_leaves = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.status == "Approved",
        models.LeaveRequest.start_date <= today,
        models.LeaveRequest.end_date >= today,
        models.LeaveRequest.user_id.in_(user_ids)
    ).all() if user_ids else []

    pending_leaves = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.status == "Pending",
        models.LeaveRequest.user_id.in_(user_ids)
    ).count() if user_ids else 0

    on_leave_today = len(today_leaves) + sum(1 for r in today_roster if r.shift_code_or_time in ["CL", "SL", "Leave", "PL"])
    weekly_off_today = sum(1 for r in today_roster if r.shift_code_or_time in ["WO", "CO"])
    working_today = sum(1 for r in today_roster if r.shift_code_or_time not in ["WO", "CO", "CL", "SL", "Leave", "PL"])
    absent_today = max(0, total_employees - working_today - weekly_off_today - on_leave_today)

    # Shift distribution for today
    shift_counts = {}
    for r in today_roster:
        s = r.shift_code_or_time or "Unassigned"
        shift_counts[s] = shift_counts.get(s, 0) + 1

    return {
        "total_employees": total_employees,
        "active_employees": active_employees,
        "inactive_employees": inactive_employees,
        "resigned_employees": resigned_employees,
        "notice_period": notice_period,
        "new_joiners": new_joiners,
        "present_today": working_today,
        "on_leave_today": on_leave_today,
        "weekly_off_today": weekly_off_today,
        "absent_today": absent_today,
        "pending_leaves": pending_leaves,
        "shift_distribution": shift_counts
    }

def get_location_breakdowns(db: Session) -> List[Dict[str, Any]]:
    """Calculates location-wise workforce, branches, and staffing distribution"""
    locations = db.query(models.Location).filter(models.Location.is_active == True).all()
    results = []
    today = date.today()

    for loc in locations:
        loc_users = db.query(models.User).filter(models.User.location_id == loc.id, models.User.is_active == True).all()
        user_ids = [u.id for u in loc_users]
        
        branch_count = db.query(models.Branch).filter(models.Branch.location_id == loc.id, models.Branch.is_active == True).count()
        dept_count = db.query(models.Department).filter(models.Department.location_id == loc.id, models.Department.is_active == True).count()
        
        # Today's roster entries
        entries = db.query(models.RosterEntry).filter(
            models.RosterEntry.date == today,
            models.RosterEntry.user_id.in_(user_ids)
        ).all() if user_ids else []

        off_cnt = sum(1 for e in entries if e.shift_code_or_time in ["WO", "CO"])
        leave_cnt = sum(1 for e in entries if e.shift_code_or_time in ["CL", "SL", "Leave", "PL"])
        duty_cnt = sum(1 for e in entries if e.shift_code_or_time not in ["WO", "CO", "CL", "SL", "Leave", "PL"])

        # Upcoming holidays for this location
        loc_holidays = db.query(models.Holiday).filter(
            models.Holiday.date >= today,
            or_(models.Holiday.location_id == loc.id, models.Holiday.location_id == None)
        ).order_by(models.Holiday.date.asc()).limit(3).all()

        results.append({
            "id": loc.id,
            "name": loc.name,
            "code": loc.code,
            "state": loc.state or "Maharashtra",
            "city": loc.city or loc.name,
            "staff_count": len(loc_users),
            "branch_count": branch_count,
            "dept_count": dept_count,
            "working_today": duty_cnt,
            "off_today": off_cnt,
            "leave_today": leave_cnt,
            "upcoming_holidays": [{"name": h.name, "date": h.date.strftime('%d %b %Y')} for h in loc_holidays]
        })
    return results

