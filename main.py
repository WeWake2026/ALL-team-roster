import os
from datetime import datetime, date, timedelta
from typing import Optional, List
from io import BytesIO

from fastapi import FastAPI, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

import models
from database import engine, get_db, Base
from auth import (
    get_password_hash,
    verify_password,
    get_current_user_from_cookie,
    require_auth,
    require_admin,
    require_admin_or_hr,
    require_admin_or_manager,
    require_roster_editor,
    get_user_perms,
    resolve_user_permissions,
    log_audit_event
)
from excel_service import (
    import_roster_file,
    export_roster_excel,
    import_leave_statement_file,
    export_leave_master_excel,
    calculate_daily_capacity,
    offboard_employee
)

# Initialize Tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="ShiftFlow Pro - MSEDCL Workforce & Leave Portal")

# Static files & Jinja2 Templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        # Check if browser HTML navigation request
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(url="/login?error=Session+expired+or+login+required", status_code=status.HTTP_302_FOUND)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

# Helpers
def get_user_notifications(user_id: int, db: Session) -> List[models.Notification]:
    return db.query(models.Notification).filter(
        models.Notification.user_id == user_id
    ).order_by(desc(models.Notification.created_at)).all()

def get_pending_leave_count(db: Session) -> int:
    return db.query(models.LeaveRequest).filter(models.LeaveRequest.status == "Pending").count()

# ================= AUTH ROUTES ================= #

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    error: Optional[str] = None,
    location_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    locations = db.query(models.Location).filter(models.Location.is_active == True).order_by(models.Location.name.asc()).all()
    # Calculate active staff counts per location
    loc_stats = {}
    for loc in locations:
        staff_count = db.query(models.User).filter(
            models.User.location_id == loc.id,
            models.User.is_active == True
        ).count()
        loc_stats[loc.id] = staff_count

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "user": None,
            "error": error,
            "locations": locations,
            "loc_stats": loc_stats,
            "preselected_location_id": location_id
        }
    )

@app.post("/login")
def login_action(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    location_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    locations = db.query(models.Location).filter(models.Location.is_active == True).order_by(models.Location.name.asc()).all()
    loc_stats = {
        loc.id: db.query(models.User).filter(models.User.location_id == loc.id, models.User.is_active == True).count()
        for loc in locations
    }

    clean_id = identifier.strip()
    user = db.query(models.User).filter(
        (models.User.email == clean_id) | (models.User.unique_id == clean_id)
    ).first()

    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "user": None,
                "error": "Invalid email/unique ID or password.",
                "locations": locations,
                "loc_stats": loc_stats,
                "preselected_location_id": location_id
            }
        )

    if not user.is_active:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "user": None,
                "error": f"Account for {user.name} ({user.unique_id}) is deactivated/offboarded. Please contact your Administrator.",
                "locations": locations,
                "loc_stats": loc_stats,
                "preselected_location_id": location_id
            }
        )

    # Permission check for location selection
    perms = resolve_user_permissions(user, db)
    target_loc_id = location_id

    if location_id:
        target_loc = db.query(models.Location).filter(models.Location.id == location_id).first()
        if target_loc and not perms.can_access_location(target_loc.id):
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "user": None,
                    "error": f"Access Restricted: Your profile ({user.access_level}) is not authorized for {target_loc.name}. Please select your assigned location.",
                    "locations": locations,
                    "loc_stats": loc_stats,
                    "preselected_location_id": user.location_id
                }
            )

    # Determine post-login destination
    # If location is provided and authorized, send to Location Roster (or dashboard if employee without roster view rights)
    is_mgmt = perms.is_admin or perms.is_hr or perms.is_manager or perms.is_team_leader or (user.access_level in ['Admin', 'Super Admin', 'Manager', 'Location Manager', 'HR', 'Team Leader'])
    if target_loc_id and is_mgmt:
        redirect_url = f"/roster/location?location_id={target_loc_id}"
    else:
        redirect_url = "/dashboard"

    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    # Set session cookie
    response.set_cookie(
        key="user_id",
        value=str(user.id),
        httponly=True,
        max_age=86400 * 7,
        path="/",
        samesite="lax"
    )
    if target_loc_id:
        response.set_cookie(
            key="active_location_id",
            value=str(target_loc_id),
            httponly=False,
            max_age=86400 * 7,
            path="/",
            samesite="lax"
        )
    return response

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="user_id")
    return response

@app.get("/switch-persona")
def switch_persona(user_id: int, db: Session = Depends(get_db)):
    """Fast Persona switcher for rapid testing of Admin, Manager, and Agent roles"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="user_id",
            value=str(user.id),
            httponly=True,
            max_age=86400 * 7,
            path="/",
            samesite="lax"
        )
        return response
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

# ================= DASHBOARD ROUTE ================= #

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user: models.User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    today = date.today()
    notifications = get_user_notifications(user.id, db)
    pending_count = get_pending_leave_count(db)

    # Today's personal shift
    today_entry = db.query(models.RosterEntry).filter(
        models.RosterEntry.user_id == user.id,
        models.RosterEntry.date == today
    ).first()

    # Check if user has an approved leave today
    today_approved_leave = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.user_id == user.id,
        models.LeaveRequest.status == "Approved",
        models.LeaveRequest.start_date <= today,
        models.LeaveRequest.end_date >= today
    ).first()

    today_shift = today_entry.shift_code_or_time if today_entry else (today_approved_leave.leave_type if today_approved_leave else "09:00 To 18:00 (Default)")
    today_status = today_entry.status if today_entry else ("On Leave" if today_approved_leave else "Scheduled")

    # 7-day upcoming personal schedule
    weekly_schedule = []
    for offset in range(7):
        d = today + timedelta(days=offset)
        e = db.query(models.RosterEntry).filter(
            models.RosterEntry.user_id == user.id,
            models.RosterEntry.date == d
        ).first()

        # Check if there is an approved leave for this date
        d_leave = db.query(models.LeaveRequest).filter(
            models.LeaveRequest.user_id == user.id,
            models.LeaveRequest.status == "Approved",
            models.LeaveRequest.start_date <= d,
            models.LeaveRequest.end_date >= d
        ).first()

        shift_val = e.shift_code_or_time if e else (d_leave.leave_type if d_leave else "09:00 To 18:00")
        status_val = e.status if e else ("Leave" if d_leave else "Scheduled")

        weekly_schedule.append({
            "date": d,
            "shift": shift_val,
            "status": status_val,
            "is_today": (d == today)
        })

    # Upcoming future planned & approved leaves (strictly user's own)
    upcoming_leaves = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.user_id == user.id,
        models.LeaveRequest.end_date >= today
    ).order_by(models.LeaveRequest.start_date.asc()).all()

    # Recent personal leaves (Strict privacy: ONLY user's own)
    user_leaves = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.user_id == user.id
    ).order_by(desc(models.LeaveRequest.created_at)).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "active_page": "dashboard",
            "today": today,
            "today_shift": today_shift,
            "today_status": today_status,
            "weekly_schedule": weekly_schedule,
            "upcoming_leaves": upcoming_leaves,
            "user_leaves": user_leaves,
            "notifications": notifications,
            "pending_leave_count": pending_count
        }
    )

# ================= ROSTER MATRIX ROUTES ================= #

@app.get("/roster", response_class=HTMLResponse)
def roster_matrix(
    request: Request,
    start_date: Optional[str] = None,
    view_mode: Optional[str] = "7", # 7 or 14
    role: Optional[str] = "All",
    user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    today = date.today()

    # Determine start date (default to current week's Monday if not explicitly provided)
    if start_date:
        try:
            current_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        except Exception:
            current_start = today - timedelta(days=today.weekday())
    else:
        # Default to current week's Monday
        current_start = today - timedelta(days=today.weekday())

    num_days = 14 if view_mode == "14" else 7
    date_list = [current_start + timedelta(days=i) for i in range(num_days)]

    prev_date = current_start - timedelta(days=num_days)
    next_date = current_start + timedelta(days=num_days)

    # Holidays in this window
    holidays = db.query(models.Holiday).filter(
        models.Holiday.date >= date_list[0],
        models.Holiday.date <= date_list[-1]
    ).all()
    holiday_map = {h.date: h.name for h in holidays}

    # Available roles, locations, and shifts
    available_roles = [r[0] for r in db.query(models.User.role_title).distinct().all() if r[0]]
    available_locations = [l[0] for l in db.query(models.User.location).distinct().all() if l[0]]
    distinct_shifts = [s[0] for s in db.query(models.RosterEntry.shift_code_or_time).distinct().all() if s[0]]
    default_shifts = ["07:00 To 16:00", "09:00 To 18:00", "11:00 To 20:00", "13:00 To 22:00", "22:00 to 07:00", "WO", "CO", "SL", "CL", "P", "HD", "A"]
    available_shifts = sorted(list(set(default_shifts + distinct_shifts)))

    # Privacy-conscious view tracking
    try:
        view_log = models.RosterViewLog(
            user_id=user.id,
            user_name=user.name,
            user_role=user.role_title or user.access_level,
            view_type="Team Roster" if (perms.is_admin or perms.is_hr or perms.is_team_leader or perms.is_manager) else "My Team Roster",
            location_id=user.location_id,
            location_name=user.location,
            team_context=f"Team {user.team_id}" if user.team_id else "General"
        )
        db.add(view_log)
        db.commit()
    except Exception:
        db.rollback()

    # Query Users - active users, or users who offboarded after the roster start date
    u_query = db.query(models.User).filter(
        ((models.User.is_active == True) | (models.User.exit_date > date_list[0]))
    )

    # STRICT ROLE-BASED SCOPING:
    # If the user is an Agent / Advisor / standard Employee, strictly limit to their own assigned team!
    is_mgmt = perms.is_admin or perms.is_hr or perms.is_manager or perms.is_team_leader or (user.access_level in ['Admin', 'Super Admin', 'Manager', 'Location Manager', 'HR', 'Team Leader'])
    if not is_mgmt:
        if user.team_id:
            u_query = u_query.filter(models.User.team_id == user.team_id)
        else:
            u_query = u_query.filter(models.User.id == user.id)
    elif perms.is_team_leader and not (perms.is_admin or perms.is_hr):
        if perms.assigned_employee_ids:
            u_query = u_query.filter(models.User.id.in_(perms.assigned_employee_ids + [user.id]))
        elif user.team_id:
            u_query = u_query.filter(models.User.team_id == user.team_id)

    if role and role != "All":
        r_clean = role.strip().upper()
        if r_clean == "TL":
            u_query = u_query.filter(
                (models.User.role_title.ilike("%TL%")) |
                (models.User.role_title.ilike("%Team Lead%")) |
                (models.User.role_title.ilike("%Floor Sup%"))
            )
        elif r_clean == "ADMIN":
            u_query = u_query.filter(
                (models.User.access_level == "Admin") |
                (models.User.role_title.ilike("%Admin%")) |
                (models.User.role_title.ilike("%Operations Lead%"))
            )
        elif r_clean == "MANAGER":
            u_query = u_query.filter(
                (models.User.access_level.in_(["Manager", "Admin"])) |
                (models.User.role_title.ilike("%Manager%")) |
                (models.User.role_title.ilike("%Lead%"))
            )
        elif r_clean in ["ALL STAFF", "AGENTS", "ALL STAFF / AGENTS", "AGENT"]:
            u_query = u_query.filter(
                (models.User.access_level == "Employee") |
                (models.User.role_title.ilike("%Agent%")) |
                (models.User.role_title.ilike("%QA%")) |
                (models.User.role_title.ilike("%Auditor%")) |
                (models.User.role_title.ilike("%CSA%")) |
                (models.User.role_title.ilike("%MIS%"))
            )
        else:
            u_query = u_query.filter(models.User.role_title == role)
    else:
        # Default All view excludes non-operational System Administrator account
        if is_mgmt:
            u_query = u_query.filter(models.User.unique_id != "ADMIN001")
    users = u_query.order_by(models.User.name.asc()).all()

    # Build matrix
    matrix_data = []
    for u in users:
        entries = db.query(models.RosterEntry).filter(
            models.RosterEntry.user_id == u.id,
            models.RosterEntry.date >= date_list[0],
            models.RosterEntry.date <= date_list[-1]
        ).all()
        entry_map = {e.date: e.shift_code_or_time for e in entries}

        # Also pull any approved leave requests falling in this date range
        approved_leaves = db.query(models.LeaveRequest).filter(
            models.LeaveRequest.user_id == u.id,
            models.LeaveRequest.status == "Approved",
            models.LeaveRequest.start_date <= date_list[-1],
            models.LeaveRequest.end_date >= date_list[0]
        ).all()
        for al in approved_leaves:
            c_date = max(al.start_date, date_list[0])
            e_date = min(al.end_date, date_list[-1])
            tag = al.leave_type if al.leave_type in ["CL", "SL", "CO"] else ("CO" if al.leave_type == "Comp-Off" else "Leave")
            while c_date <= e_date:
                entry_map[c_date] = tag
                c_date += timedelta(days=1)

        # Summary counts
        wo_cnt = sum(1 for v in entry_map.values() if str(v).strip().upper() == "WO")
        co_cnt = sum(1 for v in entry_map.values() if str(v).strip().upper() == "CO")
        leave_cnt = sum(1 for v in entry_map.values() if str(v).strip().upper() in ["CL", "SL", "LEAVE", "PL"])
        p_cnt = sum(1 for v in entry_map.values() if str(v).strip().upper() in ["P", "S"] or any(t in str(v) for t in ["07:00", "09:00", "11:00", "13:00", "20:00", "22:00"]))

        matrix_data.append({
            "user": u,
            "dates": entry_map,
            "wo_count": wo_cnt,
            "co_count": co_cnt,
            "leave_count": leave_cnt,
            "present_count": p_cnt
        })

    # Role category views: All, TL, Admin, Manager, All Staff / Agents + individual roles
    role_categories = ["All", "TL", "Admin", "Manager", "All Staff / Agents"]
    for ar in available_roles:
        if ar not in role_categories:
            role_categories.append(ar)

    # Compute Feature 1: Daily Leave Quota & Mandays Capacity Tracker
    capacity_data = calculate_daily_capacity(date_list, role, db, eligible_leave_quota=5.0)

    pending_count = get_pending_leave_count(db)

    configured_shifts = db.query(models.Shift).filter(models.Shift.is_active == True).all()

    return templates.TemplateResponse(
        request=request,
        name="roster.html",
        context={
            "user": user,
            "perms": perms,
            "active_page": "roster",
            "today": today,
            "date_list": date_list,
            "roster_matrix": matrix_data,
            "holiday_map": holiday_map,
            "available_roles": available_roles,
            "role_categories": role_categories,
            "available_locations": available_locations,
            "available_shifts": available_shifts,
            "configured_shifts": configured_shifts,
            "current_role": role,
            "view_mode": str(num_days),
            "current_start_str": current_start.strftime("%Y-%m-%d"),
            "prev_date_str": prev_date.strftime("%Y-%m-%d"),
            "next_date_str": next_date.strftime("%Y-%m-%d"),
            "total_active_staff": len(users),
            "capacity_data": capacity_data,
            "pending_leave_count": pending_count
        }
    )

@app.get("/roster/export")
def export_roster(
    start_date: str,
    end_date: str,
    role: Optional[str] = "All",
    user: models.User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Export currently filtered roster view to high-finish Excel spreadsheet"""
    try:
        s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    except Exception:
        s_date = date.today()
        e_date = s_date + timedelta(days=6)

    excel_stream = export_roster_excel(s_date, e_date, role, db)
    filename = f"MSEDCL_ShiftFlow_Roster_{s_date.strftime('%Y%m%d')}_{e_date.strftime('%Y%m%d')}.xlsx"

    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ================= LEAVE PORTAL ROUTES ================= #

# ================= UPGRADED LEAVE MANAGEMENT PORTAL ROUTES ================= #

import json
import uuid
from fastapi.responses import FileResponse

@app.get("/leaves", response_class=HTMLResponse)
def leaves_page(
    request: Request,
    alert_msg: Optional[str] = None,
    alert_type: Optional[str] = "success",
    user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    today = date.today()
    pending_count = get_pending_leave_count(db)

    # Privacy filter: Employee can query their own requests
    my_requests = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.user_id == user.id
    ).order_by(desc(models.LeaveRequest.created_at)).all()

    # Manager / Admin / Team Leader / HR review queue
    review_queue = []
    if perms.is_admin or perms.is_hr or perms.is_manager or perms.is_team_leader:
        rq_query = db.query(models.LeaveRequest).filter(
            models.LeaveRequest.status.in_(["Pending Approval", "Pending", "Cancellation Requested", "Under Review"])
        )
        # Prevent users from approving their own leave
        rq_query = rq_query.filter(models.LeaveRequest.user_id != user.id)

        # Team leader scoping
        if perms.is_team_leader and not (perms.is_admin or perms.is_hr):
            rq_query = rq_query.filter(models.LeaveRequest.user_id.in_(perms.assigned_employee_ids))
        elif not perms.can_view_all and not perms.is_admin:
            # Location manager scoping
            rq_query = rq_query.join(models.User).filter(models.User.location_id.in_(perms.location_ids))

        review_queue = rq_query.order_by(models.LeaveRequest.created_at.asc()).all()

    all_staff = []
    if perms.is_admin or perms.is_hr or perms.is_manager or perms.is_team_leader:
        s_query = db.query(models.User).filter(models.User.is_active == True)
        if not perms.can_view_all and not perms.is_admin:
            s_query = s_query.filter(models.User.location_id.in_(perms.location_ids))
        all_staff = s_query.order_by(models.User.name.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="leaves.html",
        context={
            "user": user,
            "perms": perms,
            "active_page": "leaves",
            "today": today,
            "my_requests": my_requests,
            "all_pending_requests": review_queue,
            "all_staff": all_staff,
            "pending_approval_count": len(review_queue),
            "pending_leave_count": pending_count,
            "alert_msg": alert_msg,
            "alert_type": alert_type
        }
    )

@app.post("/leaves/apply")
async def apply_leave(
    request: Request,
    leave_type: str = Form(...), # CL, SL, Comp-Off, PL, Unpaid, Half-Day
    start_date: str = Form(...),
    end_date: str = Form(...),
    reason: str = Form(...),
    target_user_id: Optional[int] = Form(None), # When Admin/Manager assigns leave for another staff member
    admin_notes: Optional[str] = Form(None), # Remarks from senior/head
    day_part: Optional[str] = Form("full"), # "full" (1.0), "half_first" (0.5), "half_second" (0.5)
    doc_category: Optional[str] = Form("Medical / Supporting Evidence"),
    evidence_files: List[UploadFile] = File(default=[]),
    user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    try:
        # Determine applicant: self or target staff member if Admin/Manager
        applicant = user
        is_admin_assign = False
        if target_user_id and target_user_id != user.id:
            if not (perms.is_admin or perms.is_hr or perms.is_manager or perms.is_team_leader):
                raise HTTPException(status_code=403, detail="Unauthorized to apply leave on behalf of other staff.")
            target_user = db.query(models.User).filter(models.User.id == target_user_id).first()
            if not target_user:
                return RedirectResponse(url="/leaves?alert_msg=Target+employee+not+found&alert_type=error", status_code=302)
            applicant = target_user
            is_admin_assign = True

        s_dt = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
        e_dt = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
        if e_dt < s_dt:
            return RedirectResponse(
                url="/leaves?alert_msg=End+date+cannot+be+earlier+than+start+date&alert_type=error",
                status_code=status.HTTP_302_FOUND
            )

        # Check overlapping leave requests for this user
        overlapping = db.query(models.LeaveRequest).filter(
            models.LeaveRequest.user_id == applicant.id,
            models.LeaveRequest.status.in_(["Approved", "Pending Approval", "Pending", "Under Review"]),
            models.LeaveRequest.start_date <= e_dt,
            models.LeaveRequest.end_date >= s_dt
        ).first()
        if overlapping:
            return RedirectResponse(
                url=f"/leaves?alert_msg=Overlapping+leave+detected:+Application+{overlapping.application_number or overlapping.id}+already+covers+{overlapping.start_date}+to+{overlapping.end_date}&alert_type=error",
                status_code=status.HTTP_302_FOUND
            )

        if day_part in ["half", "half_first", "half_second"] or leave_type == "Half-Day":
            duration = 0.5
            if leave_type == "Half-Day":
                leave_type = "CL" if (applicant.balance_cl or applicant.cl_balance or 0) >= 0.5 else "SL"
        else:
            duration = float((e_dt - s_dt).days + 1)

        # Active balance references
        active_cl = applicant.balance_cl if applicant.balance_cl is not None else (applicant.cl_balance or 0.0)
        active_sl = applicant.balance_sl if applicant.balance_sl is not None else (applicant.sl_balance or 0.0)
        active_co = applicant.balance_co if applicant.balance_co is not None else (applicant.co_balance or 0.0)

        # Balance check
        if leave_type == "CL" and active_cl < duration:
            return RedirectResponse(
                url=f"/leaves?alert_msg=Insufficient+Casual+Leave+(CL)+balance.+Requested:+{duration}+Day(s),+Available:+{active_cl}+Day(s)&alert_type=error",
                status_code=status.HTTP_302_FOUND
            )
        elif leave_type == "SL" and active_sl < duration:
            return RedirectResponse(
                url=f"/leaves?alert_msg=Insufficient+Sick+Leave+(SL)+balance.+Requested:+{duration}+Day(s),+Available:+{active_sl}+Day(s)&alert_type=error",
                status_code=status.HTTP_302_FOUND
            )
        elif leave_type in ["Comp-Off", "CO"] and active_co < duration:
            return RedirectResponse(
                url=f"/leaves?alert_msg=Insufficient+Comp-Off+(CO)+balance.+Requested:+{duration}+Day(s),+Available:+{active_co}+Day(s)&alert_type=error",
                status_code=status.HTTP_302_FOUND
            )

        # Generate unique stable Application Number
        date_stamp = datetime.utcnow().strftime("%Y%m%d")
        seq = db.query(models.LeaveRequest).count() + 1
        app_num = f"LA-{date_stamp}-{seq:04d}"

        # Combine applicant reason with any senior admin handover note
        full_reason = reason.strip()
        if admin_notes and admin_notes.strip():
            full_reason += f" [Admin/Senior Note by {user.name}: {admin_notes.strip()}]"

        initial_status = "Approved" if (is_admin_assign and (perms.is_admin or perms.is_hr)) else "Pending Approval"

        leave_req = models.LeaveRequest(
            application_number=app_num,
            user_id=applicant.id,
            leave_type=leave_type,
            day_part=day_part,
            start_date=s_dt,
            end_date=e_dt,
            duration_days=duration,
            reason=full_reason,
            status=initial_status,
            reviewed_by=user.name if is_admin_assign else None,
            reviewed_at=datetime.utcnow() if is_admin_assign else None,
            reviewer_comment=admin_notes.strip() if admin_notes else None
        )
        db.add(leave_req)
        db.flush()

        # If auto-approved by admin/HR, deduct quota immediately and update roster
        if initial_status == "Approved":
            if leave_type == "CL":
                applicant.balance_cl = max(0.0, active_cl - duration)
                applicant.cl_balance = applicant.balance_cl
                applicant.taken_cl = (applicant.taken_cl or 0.0) + duration
            elif leave_type == "SL":
                applicant.balance_sl = max(0.0, active_sl - duration)
                applicant.sl_balance = applicant.balance_sl
                applicant.taken_sl = (applicant.taken_sl or 0.0) + duration
            elif leave_type in ["Comp-Off", "CO"]:
                applicant.balance_co = max(0.0, active_co - duration)
                applicant.co_balance = applicant.balance_co

            # Sync Roster
            curr = s_dt
            while curr <= e_dt:
                rentry = db.query(models.RosterEntry).filter(
                    models.RosterEntry.user_id == applicant.id,
                    models.RosterEntry.date == curr
                ).first()
                if not rentry:
                    rentry = models.RosterEntry(
                        user_id=applicant.id,
                        date=curr,
                        shift_code_or_time=leave_type,
                        status="Leave",
                        updated_by=user.name
                    )
                    db.add(rentry)
                else:
                    rentry.shift_code_or_time = leave_type
                    rentry.status = "Leave"
                    rentry.updated_by = user.name
                curr += timedelta(days=1)

        # Handle file uploads securely
        saved_count = 0
        allowed_exts = {".pdf", ".jpg", ".jpeg", ".png"}
        upload_dir = os.path.join(BASE_DIR, "uploads", "leave_evidence")
        os.makedirs(upload_dir, exist_ok=True)

        for file in evidence_files:
            if file and file.filename and file.filename.strip():
                ext = os.path.splitext(file.filename)[1].lower()
                if ext in allowed_exts:
                    content = await file.read()
                    if len(content) > 0:
                        safe_fname = f"{app_num}_{uuid.uuid4().hex[:8]}{ext}"
                        fpath = os.path.join(upload_dir, safe_fname)
                        with open(fpath, "wb") as f_out:
                            f_out.write(content)

                        attachment = models.LeaveAttachment(
                            leave_request_id=leave_req.id,
                            file_name=file.filename,
                            stored_path=safe_fname,
                            file_type=ext.replace(".", ""),
                            file_size_bytes=len(content),
                            doc_category=doc_category,
                            uploaded_by_id=user.id
                        )
                        db.add(attachment)
                        saved_count += 1

        # Record Audit History
        history = models.LeaveHistory(
            leave_request_id=leave_req.id,
            action="APPLIED",
            actor_id=user.id,
            actor_name=user.name,
            new_state=json.dumps({
                "application_number": app_num,
                "leave_type": leave_type,
                "start_date": str(s_dt),
                "end_date": str(e_dt),
                "duration": duration,
                "status": "Pending Approval",
                "attachments": saved_count
            }),
            remarks="Initial leave application submission with evidence."
        )
        db.add(history)

        # Notify Supervisors / Operations Leads
        admin_users = db.query(models.User).filter(models.User.access_level.in_(["Admin", "Manager", "HR"])).all()
        for adm in admin_users:
            if adm.id != user.id:
                notif = models.Notification(
                    user_id=adm.id,
                    title="New Leave Application Submitted",
                    message=f"{user.name} ({user.unique_id}) submitted {leave_type} request ({app_num}) for {duration} day(s).",
                    category="leave_status"
                )
                db.add(notif)

        db.commit()
        return RedirectResponse(
            url=f"/leaves?alert_msg=Leave+Application+{app_num}+submitted+successfully!&alert_type=success",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/leaves?alert_msg=Failed+to+submit+leave:+{str(e)}&alert_type=error",
            status_code=status.HTTP_302_FOUND
        )

@app.post("/leaves/edit")
async def edit_leave(
    request: Request,
    request_id: int = Form(...),
    leave_type: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    day_part: Optional[str] = Form("full"),
    reason: str = Form(...),
    additional_comments: Optional[str] = Form(None),
    doc_category: Optional[str] = Form("Updated Supporting Evidence"),
    evidence_files: List[UploadFile] = File(default=[]),
    user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    leave_req = db.query(models.LeaveRequest).filter(models.LeaveRequest.id == request_id).first()
    if not leave_req:
        return RedirectResponse(url="/leaves?alert_msg=Application+not+found&alert_type=error", status_code=status.HTTP_302_FOUND)

    # Permission check: Applicant or authorized Admin/HR
    if leave_req.user_id != user.id and not (perms.is_admin or perms.is_hr):
        raise HTTPException(status_code=403, detail="You are not authorized to edit another employee's application.")

    # Approved leave modification check
    if leave_req.status == "Approved" and not (perms.is_admin or perms.is_hr):
        return RedirectResponse(
            url="/leaves?alert_msg=Approved+leave+cannot+be+directly+modified.+Please+request+cancellation+or+contact+HR.&alert_type=error",
            status_code=status.HTTP_302_FOUND
        )

    try:
        s_dt = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
        e_dt = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
        if e_dt < s_dt:
            return RedirectResponse(url="/leaves?alert_msg=End+date+cannot+be+earlier+than+start+date&alert_type=error", status_code=302)

        prev_state = {
            "leave_type": leave_req.leave_type,
            "start_date": str(leave_req.start_date),
            "end_date": str(leave_req.end_date),
            "duration": leave_req.duration_days,
            "status": leave_req.status
        }

        duration = 0.5 if day_part in ["half", "half_first", "half_second"] else float((e_dt - s_dt).days + 1)

        leave_req.leave_type = leave_type
        leave_req.start_date = s_dt
        leave_req.end_date = e_dt
        leave_req.duration_days = duration
        leave_req.day_part = day_part
        leave_req.reason = reason.strip()
        leave_req.updated_at = datetime.utcnow()

        # If it was rejected or approved (by Admin amendment), reset to Pending Approval
        if leave_req.status in ["Rejected", "Draft"]:
            leave_req.status = "Pending Approval"

        # Handle newly uploaded evidence
        upload_dir = os.path.join(BASE_DIR, "uploads", "leave_evidence")
        os.makedirs(upload_dir, exist_ok=True)
        allowed_exts = {".pdf", ".jpg", ".jpeg", ".png"}

        for file in evidence_files:
            if file and file.filename and file.filename.strip():
                ext = os.path.splitext(file.filename)[1].lower()
                if ext in allowed_exts:
                    content = await file.read()
                    if len(content) > 0:
                        safe_fname = f"{leave_req.application_number or leave_req.id}_{uuid.uuid4().hex[:8]}{ext}"
                        with open(os.path.join(upload_dir, safe_fname), "wb") as f_out:
                            f_out.write(content)
                        att = models.LeaveAttachment(
                            leave_request_id=leave_req.id,
                            file_name=file.filename,
                            stored_path=safe_fname,
                            file_type=ext.replace(".", ""),
                            file_size_bytes=len(content),
                            doc_category=doc_category,
                            uploaded_by_id=user.id
                        )
                        db.add(att)

        # Audit History
        history = models.LeaveHistory(
            leave_request_id=leave_req.id,
            action="EDITED",
            actor_id=user.id,
            actor_name=user.name,
            previous_state=json.dumps(prev_state),
            new_state=json.dumps({
                "leave_type": leave_type,
                "start_date": str(s_dt),
                "end_date": str(e_dt),
                "duration": duration,
                "status": leave_req.status
            }),
            remarks=additional_comments or "Application amended by user."
        )
        db.add(history)

        db.commit()
        return RedirectResponse(
            url=f"/leaves?alert_msg=Application+{leave_req.application_number or leave_req.id}+updated+successfully!&alert_type=success",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/leaves?alert_msg=Failed+to+update+application:+{str(e)}&alert_type=error",
            status_code=status.HTTP_302_FOUND
        )

@app.post("/leaves/cancel")
def cancel_leave(
    request: Request,
    request_id: int = Form(...),
    cancellation_reason: str = Form(...),
    user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    leave_req = db.query(models.LeaveRequest).filter(models.LeaveRequest.id == request_id).first()
    if not leave_req:
        return RedirectResponse(url="/leaves?alert_msg=Application+not+found&alert_type=error", status_code=302)

    # Permission check: Applicant or Admin/HR
    if leave_req.user_id != user.id and not (perms.is_admin or perms.is_hr):
        raise HTTPException(status_code=403, detail="Unauthorized to cancel this application.")

    prev_status = leave_req.status
    leave_req.cancellation_reason = cancellation_reason.strip()
    leave_req.cancellation_requested_at = datetime.utcnow()

    # If pending or draft, applicant can withdraw directly
    if prev_status in ["Pending Approval", "Pending", "Draft", "Under Review"]:
        leave_req.status = "Withdrawn"
        leave_req.cancelled_by = user.name
        leave_req.cancelled_at = datetime.utcnow()
        action_name = "WITHDRAWN"
        msg = f"Application {leave_req.application_number or leave_req.id} withdrawn successfully."
    elif prev_status == "Approved":
        # If Admin or HR is cancelling directly, approve cancellation and re-credit quota
        if perms.is_admin or perms.is_hr or perms.is_manager:
            leave_req.status = "Cancelled"
            leave_req.cancelled_by = user.name
            leave_req.cancelled_at = datetime.utcnow()
            action_name = "CANCELLED"

            # Re-credit employee leave balance
            emp = leave_req.user
            dur = leave_req.duration_days
            if leave_req.leave_type == "CL":
                emp.balance_cl = (emp.balance_cl or 0.0) + dur
                emp.cl_balance = emp.balance_cl
                emp.taken_cl = max(0.0, (emp.taken_cl or 0.0) - dur)
            elif leave_req.leave_type == "SL":
                emp.balance_sl = (emp.balance_sl or 0.0) + dur
                emp.sl_balance = emp.balance_sl
                emp.taken_sl = max(0.0, (emp.taken_sl or 0.0) - dur)
            elif leave_req.leave_type in ["Comp-Off", "CO"]:
                emp.balance_co = (emp.balance_co or 0.0) + dur
                emp.co_balance = emp.balance_co

            # Remove leave status from roster entries (restore to General 09:00 or WO)
            curr = leave_req.start_date
            while curr <= leave_req.end_date:
                r_entry = db.query(models.RosterEntry).filter(
                    models.RosterEntry.user_id == emp.id,
                    models.RosterEntry.date == curr
                ).first()
                if r_entry and r_entry.status == "Leave":
                    r_entry.shift_code_or_time = "09:00 To 18:00"
                    r_entry.status = "Scheduled"
                    r_entry.updated_by = f"Leave Cancelled ({user.name})"
                curr += timedelta(days=1)

            msg = f"Approved leave {leave_req.application_number or leave_req.id} cancelled. Roster schedule and balances restored."
        else:
            # Employee requests cancellation of approved leave
            leave_req.status = "Cancellation Requested"
            action_name = "CANCEL_REQUESTED"
            msg = f"Cancellation request submitted for {leave_req.application_number or leave_req.id}. Awaiting Manager / HR review."
    else:
        leave_req.status = "Cancelled"
        action_name = "CANCELLED"
        msg = f"Application {leave_req.application_number or leave_req.id} closed."

    # Record history
    history = models.LeaveHistory(
        leave_request_id=leave_req.id,
        action=action_name,
        actor_id=user.id,
        actor_name=user.name,
        previous_state=json.dumps({"status": prev_status}),
        new_state=json.dumps({"status": leave_req.status, "cancellation_reason": cancellation_reason}),
        remarks=cancellation_reason
    )
    db.add(history)

    # In-app notification
    notif = models.Notification(
        user_id=leave_req.user_id,
        title=f"Leave {action_name.replace('_', ' ').title()}",
        message=f"Application {leave_req.application_number or leave_req.id}: {msg}",
        category="leave_status"
    )
    db.add(notif)

    db.commit()
    return RedirectResponse(url=f"/leaves?alert_msg={msg}&alert_type=success", status_code=status.HTTP_302_FOUND)

@app.post("/leaves/review")
def review_leave(
    request: Request,
    request_id: int = Form(...),
    action: str = Form(...), # Approve, Reject, Approve Cancellation, Reject Cancellation
    comment: Optional[str] = Form(None),
    user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    if not (perms.is_admin or perms.is_hr or perms.is_manager or perms.is_team_leader):
        raise HTTPException(status_code=403, detail="You do not have review permissions.")

    leave_req = db.query(models.LeaveRequest).filter(models.LeaveRequest.id == request_id).first()
    if not leave_req:
        return RedirectResponse(url="/leaves?alert_msg=Request+not+found&alert_type=error", status_code=status.HTTP_302_FOUND)

    # Prevent self-approval
    if leave_req.user_id == user.id:
        return RedirectResponse(
            url="/leaves?alert_msg=Security+Policy:+You+cannot+approve+or+review+your+own+leave+request.&alert_type=error",
            status_code=status.HTTP_302_FOUND
        )

    prev_status = leave_req.status

    if action == "Approve Cancellation":
        leave_req.status = "Cancelled"
        leave_req.cancelled_by = user.name
        leave_req.cancelled_at = datetime.utcnow()
        leave_req.reviewer_comment = comment or "Cancellation approved by supervisor"

        # Re-credit leave balance
        emp = leave_req.user
        dur = leave_req.duration_days
        if leave_req.leave_type == "CL":
            emp.balance_cl = (emp.balance_cl or 0.0) + dur
            emp.cl_balance = emp.balance_cl
            emp.taken_cl = max(0.0, (emp.taken_cl or 0.0) - dur)
        elif leave_req.leave_type == "SL":
            emp.balance_sl = (emp.balance_sl or 0.0) + dur
            emp.sl_balance = emp.balance_sl
            emp.taken_sl = max(0.0, (emp.taken_sl or 0.0) - dur)
        elif leave_req.leave_type in ["Comp-Off", "CO"]:
            emp.balance_co = (emp.balance_co or 0.0) + dur
            emp.co_balance = emp.balance_co

        # Restore roster
        curr = leave_req.start_date
        while curr <= leave_req.end_date:
            r_entry = db.query(models.RosterEntry).filter(
                models.RosterEntry.user_id == emp.id,
                models.RosterEntry.date == curr
            ).first()
            if r_entry and r_entry.status == "Leave":
                r_entry.shift_code_or_time = "09:00 To 18:00"
                r_entry.status = "Scheduled"
                r_entry.updated_by = f"Cancellation Approved ({user.name})"
            curr += timedelta(days=1)

    elif action == "Reject Cancellation":
        leave_req.status = "Approved" # Reverts back to Approved
        leave_req.reviewer_comment = comment or "Cancellation rejected. Leave remains in force."

    elif action == "Approve":
        leave_req.status = "Approved"
        leave_req.reviewer_comment = comment or "Approved by operations lead"
        leave_req.reviewed_by = user.name
        leave_req.reviewed_at = datetime.utcnow()

        emp = leave_req.user
        dur = leave_req.duration_days
        if leave_req.leave_type == "CL":
            emp.balance_cl = max(0.0, (emp.balance_cl or emp.cl_balance or 0.0) - dur)
            emp.cl_balance = emp.balance_cl
            emp.taken_cl = (emp.taken_cl or 0.0) + dur
        elif leave_req.leave_type == "SL":
            emp.balance_sl = max(0.0, (emp.balance_sl or emp.sl_balance or 0.0) - dur)
            emp.sl_balance = emp.balance_sl
            emp.taken_sl = (emp.taken_sl or 0.0) + dur
        elif leave_req.leave_type in ["Comp-Off", "CO"]:
            emp.balance_co = max(0.0, (emp.balance_co or emp.co_balance or 0.0) - dur)
            emp.co_balance = emp.balance_co

        # Update roster slots
        curr = leave_req.start_date
        slot_label = leave_req.leave_type if leave_req.leave_type in ["CL", "SL", "CO"] else ("CO" if leave_req.leave_type == "Comp-Off" else "Leave")
        while curr <= leave_req.end_date:
            entry = db.query(models.RosterEntry).filter(
                models.RosterEntry.user_id == emp.id,
                models.RosterEntry.date == curr
            ).first()
            if entry:
                entry.shift_code_or_time = slot_label
                entry.status = "Leave"
                entry.updated_by = f"Leave Approval ({user.name})"
            else:
                entry = models.RosterEntry(
                    user_id=emp.id,
                    date=curr,
                    shift_code_or_time=slot_label,
                    status="Leave",
                    updated_by=f"Leave Approval ({user.name})"
                )
                db.add(entry)
            curr += timedelta(days=1)

    else: # Reject
        leave_req.status = "Rejected"
        leave_req.reviewer_comment = comment or "Rejected by operations lead"
        leave_req.reviewed_by = user.name
        leave_req.reviewed_at = datetime.utcnow()

    # Record Audit History
    history = models.LeaveHistory(
        leave_request_id=leave_req.id,
        action=action.upper(),
        actor_id=user.id,
        actor_name=user.name,
        previous_state=json.dumps({"status": prev_status}),
        new_state=json.dumps({"status": leave_req.status}),
        remarks=comment
    )
    db.add(history)

    # In-app notification
    notif = models.Notification(
        user_id=leave_req.user_id,
        title=f"Leave Request {leave_req.status}",
        message=f"Application {leave_req.application_number or leave_req.id} status updated to {leave_req.status} by {user.name}.",
        category="leave_status"
    )
    db.add(notif)

    db.commit()
    return RedirectResponse(
        url=f"/leaves?alert_msg=Decision+applied:+Application+{leave_req.application_number or leave_req.id}+{leave_req.status}!&alert_type=success",
        status_code=status.HTTP_302_FOUND
    )

# Secure Supporting Evidence Download (Authenticated & Scoped Only)
@app.get("/leaves/evidence/{attachment_id}")
def download_leave_evidence(
    attachment_id: int,
    user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    attachment = db.query(models.LeaveAttachment).filter(models.LeaveAttachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Supporting evidence file not found.")

    leave_req = attachment.leave_request
    # Security: File is only accessible by applicant or authorized reviewers (Admin, HR, Manager, TL)
    if leave_req.user_id != user.id and not (perms.is_admin or perms.is_hr or perms.is_manager or perms.is_team_leader):
        raise HTTPException(status_code=403, detail="Access denied: You are not authorized to view this medical/supporting document.")

    upload_dir = os.path.join(BASE_DIR, "uploads", "leave_evidence")
    full_path = os.path.join(upload_dir, attachment.stored_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Physical evidence file not found on server.")

    return FileResponse(
        path=full_path,
        filename=attachment.file_name,
        media_type="application/octet-stream"
    )

@app.get("/leaves/{request_id}/details")
def get_leave_details(
    request_id: int,
    user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    leave_req = db.query(models.LeaveRequest).filter(models.LeaveRequest.id == request_id).first()
    if not leave_req:
        raise HTTPException(status_code=404, detail="Leave application not found.")

    # Permissions: Applicant or authorized reviewer
    if leave_req.user_id != user.id and not (perms.is_admin or perms.is_hr or perms.is_manager or perms.is_team_leader):
        raise HTTPException(status_code=403, detail="Unauthorized.")

    attachments = [{
        "id": att.id,
        "file_name": att.file_name,
        "file_type": att.file_type,
        "file_size_bytes": att.file_size_bytes or 0,
        "doc_category": att.doc_category,
        "uploaded_at": att.uploaded_at.strftime("%d %b %Y, %H:%M") if att.uploaded_at else ""
    } for att in leave_req.attachments if att.is_active]

    history = [{
        "id": h.id,
        "action": h.action,
        "actor_name": h.actor_name,
        "remarks": h.remarks or "",
        "timestamp": h.timestamp.strftime("%d %b %Y, %H:%M") if h.timestamp else "",
        "previous_state": h.previous_state or "",
        "new_state": h.new_state or ""
    } for h in sorted(leave_req.history_records, key=lambda x: x.timestamp, reverse=True)]

    return JSONResponse(content={
        "id": leave_req.id,
        "application_number": leave_req.application_number or f"LA-{leave_req.id}",
        "employee_name": leave_req.user.name,
        "employee_id": leave_req.user.unique_id,
        "leave_type": leave_req.leave_type,
        "day_part": leave_req.day_part or "full",
        "start_date": str(leave_req.start_date),
        "end_date": str(leave_req.end_date),
        "duration_days": leave_req.duration_days,
        "reason": leave_req.reason,
        "status": leave_req.status,
        "reviewer_comment": leave_req.reviewer_comment or "",
        "reviewed_by": leave_req.reviewed_by or "",
        "cancellation_reason": leave_req.cancellation_reason or "",
        "created_at": leave_req.created_at.strftime("%d %b %Y, %H:%M") if leave_req.created_at else "",
        "updated_at": leave_req.updated_at.strftime("%d %b %Y, %H:%M") if leave_req.updated_at else "",
        "attachments": attachments,
        "history": history
    })

# ================= ADMIN OPERATIONS & QUICK ASSIGN ================= #

@app.get("/roster/manage", response_class=HTMLResponse)
def manage_roster(
    request: Request,
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    today = date.today()
    users = db.query(models.User).filter(models.User.is_active == True).order_by(models.User.name.asc()).all()
    shifts = db.query(models.Shift).all()
    holidays = db.query(models.Holiday).order_by(models.Holiday.date.asc()).all()
    pending_count = get_pending_leave_count(db)

    return templates.TemplateResponse(
        request=request,
        name="manage_roster.html",
        context={
            "user": user,
            "active_page": "manage_roster",
            "today": today,
            "users": users,
            "shifts": shifts,
            "holidays": holidays,
            "pending_leave_count": pending_count
        }
    )

@app.post("/roster/quick-assign")
def quick_assign_shift(
    user_id: int = Form(...),
    date: Optional[str] = Form(None),
    roster_date: Optional[str] = Form(None),
    shift_code: Optional[str] = Form(None),
    shift_name: Optional[str] = Form(None),
    reason: Optional[str] = Form(None),
    return_url: Optional[str] = Form(None),
    override_leave: Optional[str] = Form(None),
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    raw_target_date = roster_date if roster_date is not None else date
    if raw_target_date is not None and not str(type(raw_target_date)).startswith("<class 'fastapi.params"):
        target_date_str = str(raw_target_date).strip()
    elif date is not None and not str(type(date)).startswith("<class 'fastapi.params"):
        target_date_str = str(date).strip()
    else:
        target_date_str = ""

    if not target_date_str:
        raise HTTPException(status_code=400, detail="Date is required")
    t_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

    raw_shift = shift_name if shift_name is not None else shift_code
    if raw_shift is not None and not str(type(raw_shift)).startswith("<class 'fastapi.params"):
        assigned_shift = str(raw_shift).strip()
    elif shift_code is not None and not str(type(shift_code)).startswith("<class 'fastapi.params"):
        assigned_shift = str(shift_code).strip()
    else:
        assigned_shift = ""

    if not assigned_shift:
        raise HTTPException(status_code=400, detail="Shift is required")

    entry_status = "Scheduled"
    if "WO" in assigned_shift: entry_status = "WO"
    elif "CO" in assigned_shift: entry_status = "CO"
    elif "Leave" in assigned_shift or "SL" in assigned_shift or "CL" in assigned_shift: entry_status = "Leave"

    entry = db.query(models.RosterEntry).filter(
        models.RosterEntry.user_id == user_id,
        models.RosterEntry.date == t_date
    ).first()

    # Check if target employee is offboarded and reject assignments after exit date
    target_emp = db.query(models.User).filter(models.User.id == user_id).first()
    if target_emp:
        if not target_emp.is_active or (target_emp.exit_date and t_date >= target_emp.exit_date):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot assign shifts to offboarded employee {target_emp.name}. Employee was offboarded effectively from {target_emp.exit_date}."
            )

    is_override = str(override_leave).lower() in ["true", "1", "yes", "on"]

    # Leave Conflict Verification (Section J & G):
    approved_leave = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.user_id == user_id,
        models.LeaveRequest.status == "Approved",
        models.LeaveRequest.start_date <= t_date,
        models.LeaveRequest.end_date >= t_date
    ).first()
    if approved_leave:
        if not is_override:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot change shift: Employee {target_emp.name if target_emp else ''} has Approved {approved_leave.leave_type} Leave ({approved_leave.application_number or approved_leave.id}) covering {t_date}. Cancel or amend the leave first, or check 'Override Leave'."
            )
        else:
            # Override enabled: Cancel conflicting leave and record in audit
            approved_leave.status = "Cancelled"
            approved_leave.cancellation_reason = f"Overridden by shift change to '{assigned_shift}' by {user.name} on {t_date}"
            approved_leave.cancelled_by = user.name
            approved_leave.cancelled_at = datetime.utcnow()

    # Pending Leave Warning Check
    pending_leave = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.user_id == user_id,
        models.LeaveRequest.status.in_(["Pending Approval", "Pending", "Under Review"]),
        models.LeaveRequest.start_date <= t_date,
        models.LeaveRequest.end_date >= t_date
    ).first()
    warning_note = ""
    if pending_leave:
        warning_note = f" (Note: Overwrote schedule with pending {pending_leave.leave_type} leave request {pending_leave.application_number or pending_leave.id})"

    prev_shift = entry.shift_code_or_time if entry else "None"
    if entry:
        entry.shift_code_or_time = assigned_shift
        entry.status = entry_status
        entry.updated_by = user.name
    else:
        entry = models.RosterEntry(
            user_id=user_id,
            date=t_date,
            shift_code_or_time=assigned_shift,
            status=entry_status,
            updated_by=user.name
        )
        db.add(entry)

    # Record Shift Change History Audit Trail (Section H):
    safe_reason = str(reason).strip() if (reason is not None and not str(type(reason)).startswith("<class 'fastapi.params")) else None
    final_reason = safe_reason if safe_reason else f"Shift updated from Roster desk by {user.name}{warning_note}"
    history_record = models.ShiftChangeHistory(
        user_id=user_id,
        roster_date=t_date,
        previous_shift=prev_shift,
        new_shift=assigned_shift,
        previous_timings=prev_shift,
        new_timings=assigned_shift,
        changed_by_id=user.id,
        changed_by_name=user.name,
        change_reason=final_reason,
        approval_status="Approved"
    )
    db.add(history_record)

    # In-app notify affected staff
    notif = models.Notification(
        user_id=user_id,
        title="Shift Schedule Updated",
        message=f"Your shift on {t_date.strftime('%d %b %Y')} has been updated from {prev_shift} to {assigned_shift} by {user.name}.",
        category="shift_change"
    )
    db.add(notif)
    db.commit()

    safe_return_url = str(return_url).strip() if (return_url is not None and not str(type(return_url)).startswith("<class 'fastapi.params")) else None
    redirect_target = safe_return_url if safe_return_url else "/roster"
    delimiter = "&" if "?" in redirect_target else "?"
    return RedirectResponse(url=f"{redirect_target}{delimiter}alert_msg=Shift+updated+successfully+and+logged+to+history!&alert_type=success", status_code=302)

# ================= ADMIN SHIFT MANAGEMENT & AUDIT ROUTES ================= #

@app.get("/admin/shifts", response_class=HTMLResponse)
def admin_shifts_page(
    request: Request,
    user: models.User = Depends(require_admin_or_manager),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    shifts = db.query(models.Shift).order_by(models.Shift.id.asc()).all()
    locations = db.query(models.Location).filter(models.Location.is_active == True).all()

    # Calculate employee assignment counts and coverage
    coverage_map = {}
    for s in shifts:
        count = db.query(models.RosterEntry).filter(
            models.RosterEntry.shift_code_or_time == s.code,
            models.RosterEntry.date == date.today()
        ).count()
        coverage_map[s.id] = count

    return templates.TemplateResponse(
        request=request,
        name="shift_management.html",
        context={
            "user": user,
            "perms": perms,
            "active_page": "shifts",
            "shifts": shifts,
            "locations": locations,
            "coverage_map": coverage_map,
            "pending_leave_count": get_pending_leave_count(db)
        }
    )

@app.post("/admin/shifts/create")
def admin_create_shift(
    name: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    color_code: str = Form("blue"),
    is_overnight: Optional[bool] = Form(False),
    break_duration_mins: Optional[int] = Form(60),
    applicable_locations: Optional[str] = Form("All"),
    effective_from: Optional[str] = Form(None),
    user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    code = f"{start_time} To {end_time}"
    eff_dt = datetime.strptime(effective_from.strip(), "%Y-%m-%d").date() if effective_from and effective_from.strip() else None

    # Auto-detect overnight if start > end
    if start_time > end_time:
        is_overnight = True

    new_shift = models.Shift(
        name=name.strip(),
        code=code,
        start_time=start_time.strip(),
        end_time=end_time.strip(),
        is_overnight=is_overnight,
        break_duration_mins=break_duration_mins or 60,
        color_code=color_code.strip().lower(),
        applicable_locations=applicable_locations or "All",
        effective_from=eff_dt,
        is_active=True
    )
    db.add(new_shift)
    db.commit()

    return RedirectResponse(
        url="/admin/shifts?alert_msg=Shift+created+successfully!&alert_type=success",
        status_code=302
    )

@app.post("/admin/shifts/edit")
def admin_edit_shift(
    shift_id: int = Form(...),
    name: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    color_code: str = Form(...),
    is_overnight: Optional[bool] = Form(False),
    break_duration_mins: Optional[int] = Form(60),
    applicable_locations: Optional[str] = Form("All"),
    effective_from: Optional[str] = Form(None),
    user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift configuration not found.")

    eff_dt = datetime.strptime(effective_from.strip(), "%Y-%m-%d").date() if effective_from and effective_from.strip() else None

    if start_time > end_time:
        is_overnight = True

    shift.name = name.strip()
    shift.code = f"{start_time} To {end_time}"
    shift.start_time = start_time.strip()
    shift.end_time = end_time.strip()
    shift.color_code = color_code.strip().lower()
    shift.is_overnight = is_overnight
    shift.break_duration_mins = break_duration_mins or 60
    shift.applicable_locations = applicable_locations or "All"
    shift.effective_from = eff_dt

    db.commit()
    return RedirectResponse(
        url="/admin/shifts?alert_msg=Shift+updated+successfully!&alert_type=success",
        status_code=302
    )

@app.post("/admin/shifts/toggle")
def admin_toggle_shift(
    shift_id: int = Form(...),
    user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found.")

    shift.is_active = not shift.is_active
    db.commit()
    state_str = "activated" if shift.is_active else "deactivated"
    return RedirectResponse(
        url=f"/admin/shifts?alert_msg=Shift+{state_str}+successfully!&alert_type=success",
        status_code=302
    )

@app.get("/roster/history", response_class=HTMLResponse)
def roster_change_history_page(
    request: Request,
    employee_search: Optional[str] = None,
    user: models.User = Depends(require_admin_or_manager),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    query = db.query(models.ShiftChangeHistory)
    if employee_search and employee_search.strip():
        term = f"%{employee_search.strip()}%"
        query = query.join(models.User, models.ShiftChangeHistory.user_id == models.User.id).filter(
            (models.User.name.ilike(term)) | (models.User.unique_id.ilike(term))
        )

    history_records = query.order_by(desc(models.ShiftChangeHistory.created_at)).limit(100).all()

    return templates.TemplateResponse(
        request=request,
        name="shift_history.html",
        context={
            "user": user,
            "perms": perms,
            "active_page": "shift_history",
            "history_records": history_records,
            "employee_search": employee_search or "",
            "pending_leave_count": get_pending_leave_count(db)
        }
    )

@app.get("/admin/sync", response_class=HTMLResponse)
def sync_page(
    request: Request,
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    pending_count = get_pending_leave_count(db)
    return templates.TemplateResponse(
        request=request,
        name="sync.html",
        context={
            "user": user,
            "active_page": "sync",
            "pending_leave_count": pending_count
        }
    )

@app.post("/admin/upload-roster")
async def upload_roster(
    file: UploadFile = File(...),
    clear_existing: Optional[str] = Form(None),
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    try:
        if str(clear_existing).lower() in ["true", "1", "yes", "on"]:
            db.query(models.RosterEntry).delete()
            db.commit()

        contents = await file.read()
        res = import_roster_file(contents, file.filename, db, updated_by=user.name)
        msg = f"Successfully synced roster! Created {res['created_users']} new staff, updated {res['updated_users']}, ingested {res['roster_entries_count']} shift entries."
        first_date = res['dates_processed'][0] if res.get('dates_processed') else ""
        date_param = f"&start_date={first_date}" if first_date else ""
        return RedirectResponse(
            url=f"/roster?alert_msg={msg}&alert_type=success{date_param}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/sync?alert_msg=Sync+failed:+{str(e)}&alert_type=error",
            status_code=status.HTTP_302_FOUND
        )

@app.post("/admin/roster/clear")
def clear_all_roster_data(
    return_url: Optional[str] = Form(None),
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    """Purges all existing shift roster entries so a fresh roster schedule can be uploaded."""
    deleted_count = db.query(models.RosterEntry).delete()
    db.commit()
    redirect_target = return_url if return_url else "/roster"
    delimiter = "&" if "?" in redirect_target else "?"
    return RedirectResponse(
        url=f"{redirect_target}{delimiter}alert_msg=Successfully+cleared+{deleted_count}+roster+shift+records!&alert_type=success",
        status_code=status.HTTP_302_FOUND
    )

@app.post("/admin/upload-leave-statement")
async def upload_leave_statement(
    file: UploadFile = File(...),
    month_year: Optional[str] = Form("Oct-26"),
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    """
    Ingests official monthly leave balance statement (PDF, Excel, or CSV).
    Binds by UNIQUE CODE or ECN, creates missing employee profiles, and logs ledger snapshot.
    """
    try:
        contents = await file.read()
        res = import_leave_statement_file(contents, file.filename, db, month_year=month_year or "Oct-26")
        msg = f"Successfully synced leave statement! Matched & updated {res['updated_users']} profiles, provisioned {res['created_users']} new staff, logged {res['ledger_entries_created']} ledger entries."
        return RedirectResponse(
            url=f"/admin/leave-master?alert_msg={msg}&alert_type=success",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/leave-master?alert_msg=Upload+failed:+{str(e)}&alert_type=error",
            status_code=status.HTTP_302_FOUND
        )

@app.get("/admin/leave-master", response_class=HTMLResponse)
def leave_master_page(
    request: Request,
    search: Optional[str] = None,
    role: Optional[str] = "All",
    location: Optional[str] = "All",
    alert_msg: Optional[str] = None,
    alert_type: Optional[str] = "success",
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    """
    Dedicated Leave Audit Master Table with search, role filters, and export capabilities.
    """
    today = date.today()
    pending_count = get_pending_leave_count(db)

    # Distinct filters
    available_roles = [r[0] for r in db.query(models.User.role_title).distinct().all() if r[0]]
    available_locations = [l[0] for l in db.query(models.User.location).distinct().all() if l[0]]

    # Query users
    query = db.query(models.User).filter(models.User.is_active == True)
    if role and role != "All":
        query = query.filter(models.User.role_title == role)
    if location and location != "All":
        query = query.filter(models.User.location == location)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            (models.User.name.ilike(term)) |
            (models.User.unique_id.ilike(term)) |
            (models.User.ecn.ilike(term)) |
            (models.User.bm_id.ilike(term))
        )

    users_list = query.order_by(models.User.name.asc()).all()

    # Aggregate metrics
    total_cl_avail = sum((u.balance_cl if u.balance_cl is not None else u.cl_balance or 0.0) for u in users_list)
    total_sl_avail = sum((u.balance_sl if u.balance_sl is not None else u.sl_balance or 0.0) for u in users_list)
    total_cl_taken = sum((u.taken_cl or 0.0) for u in users_list)
    total_sl_taken = sum((u.taken_sl or 0.0) for u in users_list)

    return templates.TemplateResponse(
        request=request,
        name="leave_master.html",
        context={
            "user": user,
            "active_page": "leave_master",
            "today": today,
            "pending_leave_count": pending_count,
            "users": users_list,
            "available_roles": available_roles,
            "available_locations": available_locations,
            "selected_role": role,
            "selected_location": location,
            "search_term": search or "",
            "total_cl_avail": round(total_cl_avail, 2),
            "total_sl_avail": round(total_sl_avail, 2),
            "total_cl_taken": round(total_cl_taken, 2),
            "total_sl_taken": round(total_sl_taken, 2),
            "alert_msg": alert_msg,
            "alert_type": alert_type
        }
    )

@app.get("/admin/leave-master/export")
def export_leave_master(
    search: Optional[str] = None,
    role: Optional[str] = "All",
    location: Optional[str] = "All",
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    """
    Exports leave master audit table to styled Excel (.xlsx) spreadsheet
    """
    query = db.query(models.User).filter(models.User.is_active == True)
    if role and role != "All":
        query = query.filter(models.User.role_title == role)
    if location and location != "All":
        query = query.filter(models.User.location == location)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            (models.User.name.ilike(term)) |
            (models.User.unique_id.ilike(term)) |
            (models.User.ecn.ilike(term)) |
            (models.User.bm_id.ilike(term))
        )
    users_list = query.order_by(models.User.name.asc()).all()

    excel_stream = export_leave_master_excel(users_list)
    filename = f"MSEDCL_Leave_Master_Audit_{date.today().strftime('%Y%m%d')}.xlsx"

    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/admin/sample-roster")
def download_sample_roster(
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    """Download a ready-to-use sample spreadsheet matching operations format"""
    today = date.today()
    s_date = today - timedelta(days=today.weekday())
    e_date = s_date + timedelta(days=6)
    excel_stream = export_roster_excel(s_date, e_date, "All", db)
    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ShiftFlow_Operations_Sample_Template.xlsx"}
    )

@app.get("/admin/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    today = date.today()
    pending_count = get_pending_leave_count(db)
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "user": user,
            "active_page": "settings",
            "today": today,
            "pending_leave_count": pending_count
        }
    )

@app.post("/admin/add-holiday")
def add_holiday(
    name: str = Form(...),
    date: str = Form(...),
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    h_date = datetime.strptime(date, "%Y-%m-%d").date()
    existing = db.query(models.Holiday).filter(models.Holiday.date == h_date).first()
    if existing:
        existing.name = name
    else:
        h = models.Holiday(name=name, date=h_date)
        db.add(h)
    db.commit()
    return RedirectResponse(url="/roster/manage", status_code=status.HTTP_302_FOUND)

@app.post("/admin/add-shift")
def add_shift(
    name: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    code = f"{start_time} To {end_time}"
    shift = models.Shift(
        name=name,
        code=code,
        start_time=start_time,
        end_time=end_time,
        color_code="indigo"
    )
    db.add(shift)
    db.commit()
    return RedirectResponse(url="/roster/manage", status_code=status.HTTP_302_FOUND)

# ================= USER CREDENTIALS & ACCOUNT MANAGEMENT ================= #

@app.get("/admin/users", response_class=HTMLResponse)
def user_accounts_page(
    request: Request,
    status_filter: Optional[str] = "all",
    location_id: Optional[int] = None,
    department_id: Optional[int] = None,
    team_lead_id: Optional[int] = None,
    user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    # Authorization: Admin, HR, Manager can access employee console
    if not (perms.is_admin or perms.is_hr or perms.is_manager):
        raise HTTPException(status_code=403, detail="Access denied. Authorized Admin, HR, or Management personnel only.")

    u_query = db.query(models.User)

    # Scoping for non-admins
    if not perms.can_view_all and not perms.is_admin:
        u_query = u_query.filter(models.User.location_id.in_(perms.location_ids))

    if status_filter == "active":
        u_query = u_query.filter(models.User.is_active == True)
    elif status_filter == "offboarded":
        u_query = u_query.filter(models.User.is_active == False)

    if location_id:
        u_query = u_query.filter(models.User.location_id == location_id)
    if department_id:
        u_query = u_query.filter(models.User.department_id == department_id)
    if team_lead_id:
        u_query = u_query.filter(models.User.team_lead_id == team_lead_id)

    users = u_query.order_by(models.User.name.asc()).all()

    total_count = db.query(models.User).count()
    active_count = db.query(models.User).filter(models.User.is_active == True).count()
    offboarded_count = db.query(models.User).filter(models.User.is_active == False).count()

    locations = db.query(models.Location).filter(models.Location.is_active == True).all()
    departments = db.query(models.Department).filter(models.Department.is_active == True).all()
    team_leaders = db.query(models.User).filter(
        (models.User.access_level.in_(["Team Leader", "Manager", "Admin"])) |
        (models.User.role_title.ilike("%Lead%")) |
        (models.User.role_title.ilike("%TL%"))
    ).all()

    pending_count = get_pending_leave_count(db)

    # Check if logged-in user can change employee status
    can_manage_status = perms.is_admin or (perms.is_hr and perms.can_edit) or perms.is_manager

    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={
            "user": user,
            "perms": perms,
            "active_page": "users",
            "users": users,
            "total_count": total_count,
            "active_count": active_count,
            "offboarded_count": offboarded_count,
            "current_status_filter": status_filter,
            "locations": locations,
            "departments": departments,
            "team_leaders": team_leaders,
            "can_manage_status": can_manage_status,
            "pending_leave_count": pending_count
        }
    )

# ================= REST API UPGRADE PACKAGE ENDPOINTS ================= #

@app.get("/api/dashboard/metrics")
def get_dashboard_metrics(
    date_str: Optional[str] = None,
    shifts: Optional[str] = None,
    roles: Optional[str] = None,
    user: models.User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """
    Computes Headcount & Attendance metrics for a given date, with optional multi-shift and multi-role filters.
    """
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            target_date = date.today()
    else:
        # Check if database has any roster entry dates
        first_entry = db.query(models.RosterEntry).order_by(models.RosterEntry.date.asc()).first()
        target_date = first_entry.date if first_entry else date.today()

    shift_filter_list = [s.strip().upper() for s in shifts.split(",") if s.strip()] if shifts else []
    role_filter_list = [r.strip() for r in roles.split(",") if r.strip()] if roles else []

    # Query active employees
    u_query = db.query(models.User).filter(models.User.is_active == True)
    if role_filter_list:
        u_query = u_query.filter(models.User.role_title.in_(role_filter_list))
    all_users = u_query.all()
    user_ids = [u.id for u in all_users]

    entries = db.query(models.RosterEntry).filter(
        models.RosterEntry.date == target_date,
        models.RosterEntry.user_id.in_(user_ids)
    ).all()
    entry_by_user = {e.user_id: e for e in entries}

    total_planned = len(all_users)
    present_count = 0
    wo_count = 0
    cl_count = 0
    sl_count = 0
    co_count = 0
    absent_count = 0

    # Also fetch all approved leaves for target_date
    approved_leaves_today = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.status == "Approved",
        models.LeaveRequest.start_date <= target_date,
        models.LeaveRequest.end_date >= target_date,
        models.LeaveRequest.user_id.in_(user_ids)
    ).all()
    leave_by_user = {al.user_id: al for al in approved_leaves_today}

    for u in all_users:
        e = entry_by_user.get(u.id)
        al = leave_by_user.get(u.id)
        
        # If approved leave exists, it takes precedence
        if al:
            code = al.leave_type.upper()
        else:
            code = str(e.shift_code_or_time).strip().upper() if e else ""

        # If shift filters are active
        if shift_filter_list and not any(sf in code for sf in shift_filter_list):
            continue

        if code == "WO":
            wo_count += 1
        elif code in ["CO", "COMP-OFF"]:
            co_count += 1
        elif code in ["CL"]:
            cl_count += 1
        elif code in ["SL"]:
            sl_count += 1
        elif code in ["PL", "LEAVE", "UNPAID"]:
            # Counted as leave (can classify under CL or absent)
            cl_count += 1
        elif code in ["P", "S"] or any(t in code for t in ["07:00", "09:00", "11:00", "13:00", "20:00", "22:00"]):
            present_count += 1
        elif code in ["A", "ABSENT", "LEFT"]:
            absent_count += 1
        else:
            if e and e.status == "Present":
                present_count += 1
            else:
                absent_count += 1

    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "total_planned": total_planned,
        "present": present_count,
        "wo": wo_count,
        "cl": cl_count,
        "sl": sl_count,
        "co": co_count,
        "absent": absent_count
    }

class ResetPasswordPayload(models.Base.__class__):
    pass

@app.get("/api/admin/users/details/{user_id}")
def api_get_user_details(
    user_id: int,
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    return {
        "id": target.id,
        "name": target.name,
        "email": target.email,
        "unique_id": target.unique_id,
        "crm_id": target.crm_id or "",
        "bm_id": target.bm_id or "",
        "ecn": target.ecn or "",
        "role_title": target.role_title or "",
        "access_level": target.access_level or "Employee",
        "location_id": target.location_id,
        "location": target.location or "",
        "department_id": target.department_id,
        "department": target.department or "",
        "is_active": target.is_active,
        "cl_balance": float(target.cl_balance or 0.0),
        "sl_balance": float(target.sl_balance or 0.0),
        "pl_balance": float(target.pl_balance or 0.0),
        "co_balance": float(target.co_balance or 0.0),
        "taken_cl": float(target.taken_cl or 0.0),
        "taken_sl": float(target.taken_sl or 0.0),
        "doj": str(target.doj) if target.doj else "",
        "exit_date": str(target.exit_date) if target.exit_date else "",
        "exit_reason": target.exit_reason or ""
    }

@app.post("/api/admin/users/update-all")
async def api_admin_update_all_user_details(
    request: Request,
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    try:
        data = await request.json()
        target_uid = int(data.get("user_id"))
        target = db.query(models.User).filter(models.User.id == target_uid).first()
        if not target:
            raise HTTPException(status_code=404, detail="User not found.")

        # Update Personal & Identifiers
        if "name" in data and data["name"]:
            target.name = str(data["name"]).strip()
        if "email" in data and data["email"]:
            target.email = str(data["email"]).strip()
        if "unique_id" in data and data["unique_id"]:
            target.unique_id = str(data["unique_id"]).strip()
        if "bm_id" in data:
            target.bm_id = str(data["bm_id"]).strip() if data["bm_id"] else None
        if "crm_id" in data:
            target.crm_id = str(data["crm_id"]).strip() if data["crm_id"] else None
        if "ecn" in data:
            target.ecn = str(data["ecn"]).strip() if data["ecn"] else None

        # Update Role & Permissions
        if "role_title" in data and data["role_title"]:
            target.role_title = str(data["role_title"]).strip()
        if "access_level" in data and data["access_level"]:
            target.access_level = str(data["access_level"]).strip()

        # Update Location & Department
        if "location_id" in data and data["location_id"]:
            loc_id = int(data["location_id"])
            loc_obj = db.query(models.Location).filter(models.Location.id == loc_id).first()
            if loc_obj:
                target.location_id = loc_obj.id
                target.location = loc_obj.name

        if "department_id" in data and data["department_id"]:
            dept_id = int(data["department_id"])
            dept_obj = db.query(models.Department).filter(models.Department.id == dept_id).first()
            if dept_obj:
                target.department_id = dept_obj.id
                target.department = dept_obj.name

        # Update Active Status
        if "is_active" in data:
            target.is_active = bool(data["is_active"])

        # Update Leave Quotas
        if "cl_balance" in data:
            target.cl_balance = float(data["cl_balance"] or 0.0)
            target.balance_cl = target.cl_balance
        if "sl_balance" in data:
            target.sl_balance = float(data["sl_balance"] or 0.0)
            target.balance_sl = target.sl_balance
        if "pl_balance" in data:
            target.pl_balance = float(data["pl_balance"] or 0.0)
        if "co_balance" in data:
            target.co_balance = float(data["co_balance"] or 0.0)

        # Optional password update if provided
        if "new_password" in data and data["new_password"]:
            raw_pw = str(data["new_password"]).strip()
            if len(raw_pw) >= 4:
                from auth import get_password_hash
                target.hashed_password = get_password_hash(raw_pw)

        db.commit()
        return {
            "status": "success",
            "message": f"Successfully updated all details and quotas for {target.name} ({target.unique_id}).",
            "user": {
                "id": target.id,
                "name": target.name,
                "location": target.location,
                "location_id": target.location_id,
                "access_level": target.access_level,
                "is_active": target.is_active
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/admin/users/edit")
async def api_admin_edit_user(
    request: Request,
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    try:
        data = await request.json()
        target_uid = int(data.get("user_id"))
        target_user = db.query(models.User).filter(models.User.id == target_uid).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found.")

        # Fields allowed to edit
        if "location_id" in data and data["location_id"]:
            loc_id = int(data["location_id"])
            loc_obj = db.query(models.Location).filter(models.Location.id == loc_id).first()
            if loc_obj:
                target_user.location_id = loc_obj.id
                target_user.location = loc_obj.name

        if "access_level" in data and data["access_level"]:
            target_user.access_level = str(data["access_level"]).strip()

        if "role_title" in data and data["role_title"]:
            target_user.role_title = str(data["role_title"]).strip()

        if "is_active" in data:
            target_user.is_active = bool(data["is_active"])

        if "department_id" in data and data["department_id"]:
            dept_id = int(data["department_id"])
            dept_obj = db.query(models.Department).filter(models.Department.id == dept_id).first()
            if dept_obj:
                target_user.department_id = dept_obj.id
                target_user.department = dept_obj.name

        db.commit()
        return {
            "status": "success",
            "message": f"Updated profile for {target_user.name}.",
            "user": {
                "id": target_user.id,
                "name": target_user.name,
                "location_id": target_user.location_id,
                "location_name": target_user.location,
                "is_active": target_user.is_active,
                "access_level": target_user.access_level
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/admin/users/create")
async def api_admin_create_user(
    request: Request,
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    try:
        data = await request.json()
        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip()
        unique_id = str(data.get("unique_id", "")).strip()
        location_id = int(data.get("location_id"))
        role_title = str(data.get("role_title", "Operational Staff")).strip()
        access_level = str(data.get("access_level", "Employee")).strip()
        raw_pw = str(data.get("password", "Welcome@123")).strip()

        if not name or not email or not unique_id:
            raise HTTPException(status_code=400, detail="Name, email, and Unique ID are required.")

        # Check existing
        existing = db.query(models.User).filter(
            (models.User.email == email) | (models.User.unique_id == unique_id)
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="User with this email or ID already exists.")

        loc_obj = db.query(models.Location).filter(models.Location.id == location_id).first()
        loc_name = loc_obj.name if loc_obj else "Mumbai"

        from auth import get_password_hash
        new_u = models.User(
            name=name,
            email=email,
            unique_id=unique_id,
            location_id=location_id,
            location=loc_name,
            role_title=role_title,
            access_level=access_level,
            hashed_password=get_password_hash(raw_pw),
            is_active=True,
            cl_balance=10.0,
            sl_balance=8.0,
            pl_balance=15.0,
            co_balance=2.0
        )
        db.add(new_u)
        db.commit()
        db.refresh(new_u)

        return {
            "status": "success",
            "message": f"Successfully registered {new_u.name} in {loc_name}.",
            "user_id": new_u.id
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/admin/users/reset-password")
async def api_reset_password(
    request: Request,
    user: models.User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db)
):
    try:
        data = await request.json()
        target_uid = int(data.get("user_id"))
        new_password = str(data.get("new_password", "")).strip()

        if not new_password or len(new_password) < 4:
            raise HTTPException(status_code=400, detail="Password must be at least 4 characters long.")

        target_user = db.query(models.User).filter(models.User.id == target_uid).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="User account not found.")

        target_user.hashed_password = get_password_hash(new_password)
        db.commit()

        return {
            "success": True,
            "message": f"Password reset successfully for {target_user.name}.",
            "user_id": target_user.id,
            "name": target_user.name,
            "email": target_user.email,
            "unique_id": target_user.unique_id
        }
    except Exception as e:
        db.rollback()
        return {"success": False, "detail": str(e)}

@app.get("/api/leaves/my-balance")
def api_get_my_balance(
    user: models.User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """
    Privacy-guarded leave balance query: only returns authenticated employee's own ledger balances.
    """
    return {
        "user_id": user.id,
        "name": user.name,
        "unique_id": user.unique_id,
        "annual_total_quota": 21.0,
        "cl_balance": user.cl_balance,
        "sl_balance": user.sl_balance,
        "co_balance": user.co_balance,
        "pl_balance": user.pl_balance,
        "unpaid_taken": user.unpaid_taken
    }

@app.post("/admin/employees/offboard")
def handle_offboard_employee(
    request: Request,
    user_id: int = Form(...),
    exit_date: str = Form(...),
    exit_reason: Optional[str] = Form(None),
    reason: Optional[str] = Form(None),
    remarks: Optional[str] = Form(None),
    return_url: Optional[str] = Form(None),
    current_user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    """
    Roster Employee Offboarding / Deactivation
    Strictly restricted to Admin, HR (with edit rights), or Managers with authorization.
    """
    if not (perms.is_admin or (perms.is_hr and perms.can_edit) or perms.is_manager):
        raise HTTPException(status_code=403, detail="You do not have permission to offboard employees.")

    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Employee not found.")

    # Scope check for location
    if not perms.can_view_all and not perms.is_admin:
        if target_user.location_id and not perms.can_access_location(target_user.location_id):
            raise HTTPException(status_code=403, detail="You are not authorized to offboard employees outside your assigned location.")

    redirect_target = return_url or "/admin/users"
    sep = "&" if "?" in redirect_target else "?"

    try:
        e_date = datetime.strptime(exit_date.strip(), "%Y-%m-%d").date()
        final_reason = (exit_reason or reason or "Separation").strip()
        if remarks and remarks.strip():
            final_reason = f"{final_reason} - {remarks.strip()}"

        res = offboard_employee(
            user_id=user_id,
            exit_date_val=e_date,
            reason=final_reason,
            db=db,
            actor_name=current_user.name
        )

        log_audit_event(
            db=db,
            actor=current_user,
            action="EMPLOYEE_OFFBOARD",
            resource_type="User",
            resource_id=str(user_id),
            details=f"Offboarded {target_user.name} ({target_user.unique_id}) effective {e_date}. Reason: {final_reason}"
        )

        msg = f"Employee {res['name']} ({res['unique_id']}) offboarded successfully effective {res['exit_date']}."
        return RedirectResponse(
            url=f"{redirect_target}{sep}alert_msg={msg}&alert_type=success",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        return RedirectResponse(
            url=f"{redirect_target}{sep}alert_msg=Offboarding+failed:+{str(e)}&alert_type=error",
            status_code=status.HTTP_302_FOUND
        )

@app.post("/admin/employees/activate")
def handle_activate_employee(
    request: Request,
    user_id: int = Form(...),
    return_url: Optional[str] = Form(None),
    current_user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    """
    Roster Employee Activation / Reactivation
    Restores an employee to Active status, clears exit date, and re-enables roster scheduling.
    """
    if not (perms.is_admin or (perms.is_hr and perms.can_edit) or perms.is_manager):
        raise HTTPException(status_code=403, detail="You do not have permission to change employee active status.")

    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Employee not found.")

    if not perms.can_view_all and not perms.is_admin:
        if target_user.location_id and not perms.can_access_location(target_user.location_id):
            raise HTTPException(status_code=403, detail="You are not authorized to manage employees outside your assigned location.")

    prev_exit_date = target_user.exit_date
    target_user.is_active = True
    target_user.exit_date = None
    target_user.exit_reason = None
    db.commit()

    log_audit_event(
        db=db,
        actor=current_user,
        action="EMPLOYEE_ACTIVATE",
        resource_type="User",
        resource_id=str(user_id),
        details=f"Reactivated {target_user.name} ({target_user.unique_id}). Previous exit date was {prev_exit_date}."
    )

    redirect_target = return_url or "/admin/users"
    sep = "&" if "?" in redirect_target else "?"
    msg = f"Employee {target_user.name} ({target_user.unique_id}) is now ACTIVE and eligible for shift scheduling."
    return RedirectResponse(
        url=f"{redirect_target}{sep}alert_msg={msg}&alert_type=success",
        status_code=status.HTTP_302_FOUND
    )

@app.post("/api/admin/employees/offboard")
async def api_offboard_employee(
    request: Request,
    current_user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    """
    Feature REST API: Employee Deactivation / Offboarding
    """
    if not (perms.is_admin or (perms.is_hr and perms.can_edit) or perms.is_manager):
        raise HTTPException(status_code=403, detail="You do not have permission to offboard employees.")

    try:
        data = await request.json()
        target_uid = int(data.get("user_id"))
        exit_date_str = str(data.get("exit_date", "")).strip()
        reason = str(data.get("exit_reason", "")).strip() or "Separation"

        if not exit_date_str:
            raise HTTPException(status_code=400, detail="Exit date is required.")

        target_user = db.query(models.User).filter(models.User.id == target_uid).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found.")

        if not perms.can_view_all and not perms.is_admin:
            if target_user.location_id and not perms.can_access_location(target_user.location_id):
                raise HTTPException(status_code=403, detail="Unauthorized location access.")

        e_date = datetime.strptime(exit_date_str, "%Y-%m-%d").date()
        res = offboard_employee(
            user_id=target_uid,
            exit_date_val=e_date,
            reason=reason,
            db=db,
            actor_name=current_user.name
        )

        log_audit_event(
            db=db,
            actor=current_user,
            action="EMPLOYEE_OFFBOARD",
            resource_type="User",
            resource_id=str(target_uid),
            details=f"Offboarded {target_user.name} via API effective {e_date}"
        )

        return {
            "success": True,
            "message": f"Employee {res['name']} offboarded successfully.",
            "data": res
        }
    except Exception as e:
        db.rollback()
        return {"success": False, "detail": str(e)}

@app.post("/api/admin/employees/activate")
async def api_activate_employee(
    request: Request,
    current_user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    """
    Feature REST API: Employee Reactivation
    """
    if not (perms.is_admin or (perms.is_hr and perms.can_edit) or perms.is_manager):
        raise HTTPException(status_code=403, detail="You do not have permission to reactivate employees.")

    try:
        data = await request.json()
        target_uid = int(data.get("user_id"))
        target_user = db.query(models.User).filter(models.User.id == target_uid).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found.")

        if not perms.can_view_all and not perms.is_admin:
            if target_user.location_id and not perms.can_access_location(target_user.location_id):
                raise HTTPException(status_code=403, detail="Unauthorized location access.")

        prev_exit_date = target_user.exit_date
        target_user.is_active = True
        target_user.exit_date = None
        target_user.exit_reason = None
        db.commit()

        log_audit_event(
            db=db,
            actor=current_user,
            action="EMPLOYEE_ACTIVATE",
            resource_type="User",
            resource_id=str(target_uid),
            details=f"Reactivated {target_user.name} ({target_user.unique_id}) via API."
        )

        return {
            "success": True,
            "message": f"Employee {target_user.name} reactivated successfully.",
            "user_id": target_uid,
            "is_active": True
        }
    except Exception as e:
        db.rollback()
        return {"success": False, "detail": str(e)}

@app.get("/api/roster/capacity")
def api_get_roster_capacity(
    start_date: Optional[str] = None,
    num_days: Optional[int] = 7,
    role: Optional[str] = "All",
    quota: Optional[float] = 5.0,
    user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    """
    Feature 1 REST API: Daily Leave Quota & Mandays Capacity Tracker
    Restricted to Admin, HR, Location Manager, and Team Leader.
    """
    is_authorized = (
        perms.is_admin or 
        perms.is_hr or 
        perms.is_manager or 
        perms.is_team_leader or 
        (user.access_level in ['Admin', 'Super Admin', 'Manager', 'HR', 'Team Leader']) or 
        ("team lead" in (user.role_title or "").lower()) or
        ("lead" in (user.role_title or "").lower())
    )
    if not is_authorized:
        raise HTTPException(status_code=403, detail="Access denied: Daily Leave Quota & Mandays Capacity Tracker is visible only to Admin and Team Leaders.")

    if start_date:
        try:
            s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        except Exception:
            s_date = date.today()
    else:
        s_date = date.today()

    count = min(31, max(1, num_days or 7))
    dates = [s_date + timedelta(days=i) for i in range(count)]
    res = calculate_daily_capacity(dates, role, db, eligible_leave_quota=quota or 5.0)
    return res

# ================= LOCATION-WISE ROSTER MODULE ================= #

@app.get("/roster/location", response_class=HTMLResponse)
def location_roster_view(
    request: Request,
    location_id: Optional[int] = None,
    start_date: Optional[str] = None,
    view_mode: Optional[str] = "7",
    department_id: Optional[int] = None,
    team_id: Optional[int] = None,
    user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    # Strict Server-Side Role Enforcement:
    # Agents, Advisors, and Employees cannot access Location Roster
    is_mgmt = perms.is_admin or perms.is_hr or perms.is_manager or perms.is_team_leader or (user.access_level in ['Admin', 'Super Admin', 'Manager', 'Location Manager', 'HR', 'Team Leader'])
    if not is_mgmt:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Location-Wise Roster is restricted to Admin, HR, Managers, and Team Leaders."
        )

    # Privacy-conscious view tracking
    try:
        view_log = models.RosterViewLog(
            user_id=user.id,
            user_name=user.name,
            user_role=user.role_title or user.access_level,
            view_type="Location Roster",
            location_id=location_id,
            location_name=f"Location {location_id}" if location_id else "Default Location",
            team_context=f"Dept {department_id}" if department_id else "All"
        )
        db.add(view_log)
        db.commit()
    except Exception:
        db.rollback()

    # Determine authorized locations for this user
    today = date.today()

    all_locations = db.query(models.Location).filter(models.Location.is_active == True).all()
    if perms.can_view_all or perms.is_admin:
        authorized_locations = all_locations
    else:
        authorized_locations = [loc for loc in all_locations if loc.id in perms.location_ids]

    if not authorized_locations:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You have no authorized work locations assigned to your account."
        )

    # Resolve target location with strict IDOR verification
    if location_id:
        target_loc = db.query(models.Location).filter(models.Location.id == location_id).first()
        if not target_loc or not perms.can_access_location(target_loc.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not authorized to view the requested location roster."
            )
    else:
        # Check if user has an active_location_id cookie set from login or selection
        cookie_loc_id = request.cookies.get("active_location_id")
        matched_loc = None
        if cookie_loc_id:
            try:
                c_id = int(cookie_loc_id)
                matched_loc = next((loc for loc in authorized_locations if loc.id == c_id), None)
            except Exception:
                pass
        target_loc = matched_loc if matched_loc else authorized_locations[0]

    # Date range calculation
    if start_date:
        try:
            current_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        except Exception:
            current_start = today - timedelta(days=today.weekday())
    else:
        first_entry = db.query(models.RosterEntry).filter(
            models.RosterEntry.location_id == target_loc.id
        ).order_by(models.RosterEntry.date.asc()).first()
        if first_entry:
            current_start = first_entry.date
        else:
            current_start = today - timedelta(days=today.weekday())

    num_days = 14 if view_mode == "14" else 7
    date_list = [current_start + timedelta(days=i) for i in range(num_days)]
    prev_date = current_start - timedelta(days=num_days)
    next_date = current_start + timedelta(days=num_days)

    # Holidays in window
    holidays = db.query(models.Holiday).filter(
        models.Holiday.date >= date_list[0],
        models.Holiday.date <= date_list[-1]
    ).all()
    holiday_map = {h.date: h.name for h in holidays}

    # Query employees belonging to target location with strict scope filtering
    u_query = db.query(models.User).filter(
        models.User.location_id == target_loc.id,
        models.User.is_active == True
    )

    # If user is Team Leader, strictly restrict to their assigned subordinates
    if perms.is_team_leader and not (perms.is_admin or perms.is_hr):
        u_query = u_query.filter(models.User.id.in_(perms.assigned_employee_ids))

    if department_id:
        u_query = u_query.filter(models.User.department_id == department_id)
    if team_id:
        u_query = u_query.filter(models.User.team_id == team_id)

    users = u_query.order_by(models.User.name.asc()).all()

    # Build matrix & calculate shortages
    matrix_data = []
    daily_present_count = {d: 0 for d in date_list}

    for u in users:
        entries = db.query(models.RosterEntry).filter(
            models.RosterEntry.user_id == u.id,
            models.RosterEntry.date >= date_list[0],
            models.RosterEntry.date <= date_list[-1]
        ).all()
        entry_map = {e.date: e.shift_code_or_time for e in entries}

        # Check leaves
        approved_leaves = db.query(models.LeaveRequest).filter(
            models.LeaveRequest.user_id == u.id,
            models.LeaveRequest.status == "Approved",
            models.LeaveRequest.start_date <= date_list[-1],
            models.LeaveRequest.end_date >= date_list[0]
        ).all()
        for al in approved_leaves:
            c_date = max(al.start_date, date_list[0])
            e_date = min(al.end_date, date_list[-1])
            tag = al.leave_type if al.leave_type in ["CL", "SL", "CO"] else "Leave"
            while c_date <= e_date:
                entry_map[c_date] = tag
                c_date += timedelta(days=1)

        wo_cnt = sum(1 for v in entry_map.values() if str(v).strip().upper() == "WO")
        co_cnt = sum(1 for v in entry_map.values() if str(v).strip().upper() == "CO")
        leave_cnt = sum(1 for v in entry_map.values() if str(v).strip().upper() in ["CL", "SL", "LEAVE", "PL"])

        for d in date_list:
            s_val = str(entry_map.get(d, "09:00 To 18:00")).strip().upper()
            if s_val not in ["WO", "CO", "CL", "SL", "LEAVE", "PL", "A"]:
                daily_present_count[d] += 1

        matrix_data.append({
            "user": u,
            "dates": entry_map,
            "wo_count": wo_cnt,
            "co_count": co_cnt,
            "leave_count": leave_cnt
        })

    # Detect staffing shortages (< 5 active staff per operational day)
    staffing_shortages = [d for d, cnt in daily_present_count.items() if cnt < 5]

    departments = db.query(models.Department).filter(
        (models.Department.location_id == target_loc.id) | (models.Department.location_id == None)
    ).all()
    teams = db.query(models.Team).all()

    return templates.TemplateResponse(
        request=request,
        name="location_roster.html",
        context={
            "user": user,
            "perms": perms,
            "active_page": "location_roster",
            "today": today,
            "authorized_locations": authorized_locations,
            "current_location": target_loc,
            "date_list": date_list,
            "roster_matrix": matrix_data,
            "holiday_map": holiday_map,
            "view_mode": str(num_days),
            "current_start_str": current_start.strftime("%Y-%m-%d"),
            "prev_date_str": prev_date.strftime("%Y-%m-%d"),
            "next_date_str": next_date.strftime("%Y-%m-%d"),
            "total_active_staff": len(users),
            "departments": departments,
            "teams": teams,
            "selected_dept_id": department_id or "",
            "selected_team_id": team_id or "",
            "staffing_shortages": staffing_shortages,
            "pending_leave_count": get_pending_leave_count(db)
        }
    )

# ================= COMBINED MULTI-LOCATION ROSTER MODULE ================= #

@app.get("/roster/combined", response_class=HTMLResponse)
def combined_roster_view(
    request: Request,
    start_date: Optional[str] = None,
    view_mode: Optional[str] = "7",
    user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    # Strict Server-Side Role Enforcement:
    # Only authorized Admin and HR can access Combined Roster!
    can_access_combined = perms.is_admin or perms.is_hr or (user.access_level in ['Admin', 'Super Admin', 'HR'])
    if not can_access_combined:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Consolidated Combined Roster is restricted exclusively to Admin and HR."
        )

    today = date.today()

    # Privacy-conscious view tracking
    try:
        view_log = models.RosterViewLog(
            user_id=user.id,
            user_name=user.name,
            user_role=user.role_title or user.access_level,
            view_type="Combined Roster",
            location_id=None,
            location_name="All Authorized Locations",
            team_context="Cross-Enterprise"
        )
        db.add(view_log)
        db.commit()
    except Exception:
        db.rollback()

    all_locations = db.query(models.Location).filter(models.Location.is_active == True).all()
    if perms.can_view_all or perms.is_admin:
        authorized_locations = all_locations
    else:
        authorized_locations = [loc for loc in all_locations if loc.id in perms.location_ids]

    # Date handling
    if start_date:
        try:
            current_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        except Exception:
            current_start = today - timedelta(days=today.weekday())
    else:
        first_entry = db.query(models.RosterEntry).order_by(models.RosterEntry.date.asc()).first()
        current_start = first_entry.date if first_entry else (today - timedelta(days=today.weekday()))

    num_days = 14 if view_mode == "14" else 7
    date_list = [current_start + timedelta(days=i) for i in range(num_days)]
    prev_date = current_start - timedelta(days=num_days)
    next_date = current_start + timedelta(days=num_days)

    # Query employees across all authorized locations
    auth_loc_ids = [loc.id for loc in authorized_locations]
    u_query = db.query(models.User).filter(
        models.User.is_active == True,
        models.User.location_id.in_(auth_loc_ids)
    )

    if perms.is_team_leader and not (perms.is_admin or perms.is_hr):
        u_query = u_query.filter(models.User.id.in_(perms.assigned_employee_ids))

    users = u_query.order_by(models.User.location.asc(), models.User.name.asc()).all()

    matrix_data = []
    for u in users:
        entries = db.query(models.RosterEntry).filter(
            models.RosterEntry.user_id == u.id,
            models.RosterEntry.date >= date_list[0],
            models.RosterEntry.date <= date_list[-1]
        ).all()
        entry_map = {e.date: e.shift_code_or_time for e in entries}

        wo_cnt = sum(1 for v in entry_map.values() if str(v).strip().upper() == "WO")
        co_cnt = sum(1 for v in entry_map.values() if str(v).strip().upper() == "CO")
        leave_cnt = sum(1 for v in entry_map.values() if str(v).strip().upper() in ["CL", "SL", "LEAVE", "PL"])

        matrix_data.append({
            "user": u,
            "dates": entry_map,
            "wo_count": wo_cnt,
            "co_count": co_cnt,
            "leave_count": leave_cnt
        })

    departments = db.query(models.Department).all()

    return templates.TemplateResponse(
        request=request,
        name="combined_roster.html",
        context={
            "user": user,
            "perms": perms,
            "active_page": "combined_roster",
            "today": today,
            "authorized_locations": authorized_locations,
            "date_list": date_list,
            "roster_matrix": matrix_data,
            "view_mode": str(num_days),
            "current_start_str": current_start.strftime("%Y-%m-%d"),
            "prev_date_str": prev_date.strftime("%Y-%m-%d"),
            "next_date_str": next_date.strftime("%Y-%m-%d"),
            "total_active_staff": len(users),
            "departments": departments,
            "pending_leave_count": get_pending_leave_count(db)
        }
    )

# ================= ADMIN USER & DATA ASSIGNMENT MODULE ================= #

@app.get("/admin/assignments", response_class=HTMLResponse)
def admin_assignments_page(
    request: Request,
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    assignments = db.query(models.UserAssignment).order_by(desc(models.UserAssignment.created_at)).all()
    users = db.query(models.User).filter(models.User.is_active == True).order_by(models.User.name.asc()).all()
    locations = db.query(models.Location).filter(models.Location.is_active == True).all()
    departments = db.query(models.Department).filter(models.Department.is_active == True).all()
    teams = db.query(models.Team).filter(models.Team.is_active == True).all()
    team_leaders = db.query(models.User).filter(
        models.User.is_active == True,
        (models.User.access_level.in_(["Team Leader", "Manager", "Admin"])) |
        (models.User.role_title.ilike("%Lead%")) |
        (models.User.role_title.ilike("%TL%"))
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="assignments.html",
        context={
            "user": current_admin,
            "active_page": "assignments",
            "today": date.today(),
            "assignments": assignments,
            "users": users,
            "locations": locations,
            "departments": departments,
            "teams": teams,
            "team_leaders": team_leaders,
            "pending_leave_count": get_pending_leave_count(db)
        }
    )

@app.post("/admin/assignments")
def create_user_assignment(
    request: Request,
    user_id: int = Form(...),
    location_id: Optional[str] = Form(None),
    department_id: Optional[str] = Form(None),
    team_id: Optional[str] = Form(None),
    team_lead_id: Optional[str] = Form(None),
    assigned_employee_id: Optional[str] = Form(None),
    effective_from: str = Form(...),
    effective_to: Optional[str] = Form(None),
    can_view: Optional[str] = Form(None),
    can_create: Optional[str] = Form(None),
    can_edit: Optional[str] = Form(None),
    can_approve: Optional[str] = Form(None),
    can_export: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    try:
        eff_from = datetime.strptime(effective_from.strip(), "%Y-%m-%d").date()
        eff_to = datetime.strptime(effective_to.strip(), "%Y-%m-%d").date() if effective_to and effective_to.strip() else None

        loc_id = int(location_id) if location_id and location_id.strip() else None
        dept_id = int(department_id) if department_id and department_id.strip() else None
        t_id = int(team_id) if team_id and team_id.strip() else None
        tl_id = int(team_lead_id) if team_lead_id and team_lead_id.strip() else None
        emp_id = int(assigned_employee_id) if assigned_employee_id and assigned_employee_id.strip() else None

        new_assignment = models.UserAssignment(
            user_id=user_id,
            location_id=loc_id,
            department_id=dept_id,
            team_id=t_id,
            team_lead_id=tl_id,
            assigned_employee_id=emp_id,
            can_view=bool(can_view),
            can_create=bool(can_create),
            can_edit=bool(can_edit),
            can_approve=bool(can_approve),
            can_export=bool(can_export),
            effective_from=eff_from,
            effective_to=eff_to,
            status="Active",
            notes=notes.strip() if notes else None,
            created_by_id=current_admin.id
        )
        db.add(new_assignment)
        db.commit()

        # Record Immutable Audit Log
        log_audit_event(
            db=db,
            actor=current_admin,
            action="ASSIGNMENT_CREATE",
            resource_type="UserAssignment",
            resource_id=str(new_assignment.id),
            details=f"Granted scope to user_id={user_id} (Location={loc_id}, Team={t_id}, TL={tl_id})"
        )

        return RedirectResponse(
            url="/admin/assignments?alert_msg=Scope+assignment+granted+successfully!&alert_type=success",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/admin/assignments?alert_msg=Assignment+failed:+{str(e)}&alert_type=error",
            status_code=status.HTTP_302_FOUND
        )

@app.post("/admin/assignments/{assignment_id}/status")
def update_assignment_status(
    assignment_id: int,
    status: str = Form(...),
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    assignment = db.query(models.UserAssignment).filter(models.UserAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment record not found.")

    assignment.status = status
    db.commit()

    log_audit_event(
        db=db,
        actor=current_admin,
        action=f"ASSIGNMENT_{status.upper()}",
        resource_type="UserAssignment",
        resource_id=str(assignment.id),
        details=f"Updated assignment {assignment_id} status to {status}"
    )

    return RedirectResponse(
        url=f"/admin/assignments?alert_msg=Assignment+status+updated+to+{status}&alert_type=success",
        status_code=302
    )

# ================= AUDIT LOGS MODULE ================= #

@app.get("/audit-logs", response_class=HTMLResponse)
def audit_logs_page(
    request: Request,
    current_admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    logs = db.query(models.AuditLog).order_by(desc(models.AuditLog.timestamp)).limit(200).all()
    return templates.TemplateResponse(
        request=request,
        name="audit_logs.html",
        context={
            "user": current_admin,
            "active_page": "audit_logs",
            "logs": logs,
            "pending_leave_count": get_pending_leave_count(db)
        }
    )

# ================= REPORTS & ANALYTICS MODULE ================= #

@app.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request,
    user: models.User = Depends(require_auth),
    perms: get_user_perms = Depends(get_user_perms),
    db: Session = Depends(get_db)
):
    today = date.today()
    total_staff = len(perms.assigned_employee_ids) if not perms.can_view_all else db.query(models.User).filter(models.User.is_active == True).count()

    # Query today's shifts for authorized staff
    today_entries = db.query(models.RosterEntry).filter(
        models.RosterEntry.date == today
    ).all()
    today_leaves = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.status == "Approved",
        models.LeaveRequest.start_date <= today,
        models.LeaveRequest.end_date >= today
    ).all()

    off_today = sum(1 for e in today_entries if e.shift_code_or_time in ["WO", "CO"])
    on_leave_today = len(today_leaves) + sum(1 for e in today_entries if e.shift_code_or_time in ["CL", "SL", "Leave", "PL"])
    present_today = max(0, total_staff - off_today - on_leave_today)

    # Location distribution
    locations = db.query(models.Location).filter(models.Location.is_active == True).all()
    loc_headcount = []
    for loc in locations:
        cnt = db.query(models.User).filter(models.User.location_id == loc.id, models.User.is_active == True).count()
        pct = round((cnt / max(1, total_staff)) * 100, 1)
        loc_headcount.append({"name": loc.name, "count": cnt, "percent": pct})

    # Shift distribution
    shift_slots = ["07:00 To 16:00", "09:00 To 18:00", "13:00 To 22:00", "22:00 To 07:00", "WO", "CO"]
    shift_breakdown = []
    for s in shift_slots:
        cnt = sum(1 for e in today_entries if s.lower() in e.shift_code_or_time.lower())
        pct = round((cnt / max(1, len(today_entries))) * 100, 1)
        shift_breakdown.append({"shift": s, "count": cnt, "percent": pct})

    return templates.TemplateResponse(
        request=request,
        name="reports.html",
        context={
            "user": user,
            "perms": perms,
            "active_page": "reports",
            "today": today,
            "total_staff": total_staff,
            "present_today": present_today,
            "on_leave_today": on_leave_today,
            "off_today": off_today,
            "location_headcount": loc_headcount,
            "shift_breakdown": shift_breakdown,
            "pending_leave_count": get_pending_leave_count(db)
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

