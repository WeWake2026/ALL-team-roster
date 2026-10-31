from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.auth import (
    verify_password,
    get_password_hash,
    get_user_perms,
    get_current_user_from_cookie
)
from app.core.audit import log_audit_event
import models

router = APIRouter(tags=["Authentication"])
templates = Jinja2Templates(directory="templates")

def get_company_setting_val(key: str, default: str, db: Session) -> str:
    s = db.query(models.CompanySetting).filter(models.CompanySetting.setting_key == key).first()
    return s.setting_value if s else default

@router.get("/", response_class=HTMLResponse)
def index_redirect(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@router.get("/login", response_class=HTMLResponse)
def login_view(
    request: Request,
    error: Optional[str] = None,
    location_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    locations = db.query(models.Location).filter(models.Location.is_active == True).order_by(models.Location.name.asc()).all()
    loc_stats = {
        loc.id: db.query(models.User).filter(models.User.location_id == loc.id, models.User.is_active == True).count()
        for loc in locations
    }

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

@router.post("/login")
def login_submit(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    location_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    clean_id = identifier.strip()
    user = db.query(models.User).filter(
        (models.User.email == clean_id) | (models.User.unique_id == clean_id)
    ).first()

    locations = db.query(models.Location).filter(models.Location.is_active == True).order_by(models.Location.name.asc()).all()
    loc_stats = {
        loc.id: db.query(models.User).filter(models.User.location_id == loc.id, models.User.is_active == True).count()
        for loc in locations
    }

    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "user": None,
                "error": "Invalid email/ID or password. Please verify and try again.",
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
                "error": "Account is marked inactive or offboarded. Contact administrator.",
                "locations": locations,
                "loc_stats": loc_stats,
                "preselected_location_id": location_id
            }
        )

    # Scoping check
    perms = get_user_perms(user=user, db=db)
    target_loc_id = location_id or user.location_id

    # Record login session log
    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    u_agent = request.headers.get("user-agent", "")[:250]

    session_log = models.UserSessionLog(
        user_id=user.id,
        login_time=datetime.utcnow(),
        ip_address=client_ip,
        user_agent=u_agent,
        is_active_session=True
    )
    db.add(session_log)
    db.commit()

    is_mgmt = perms.is_admin or perms.is_hr or perms.is_manager or perms.is_team_leader or (user.access_level in ['Admin', 'Super Admin', 'Manager', 'Location Manager', 'HR', 'Team Leader'])
    redirect_url = f"/roster/location?location_id={target_loc_id}" if (target_loc_id and is_mgmt) else "/dashboard"

    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="user_id", value=str(user.id), httponly=True, max_age=86400 * 7, path="/", samesite="lax")
    response.set_cookie(key="session_log_id", value=str(session_log.id), httponly=True, max_age=86400 * 7, path="/", samesite="lax")
    if target_loc_id:
        response.set_cookie(key="active_location_id", value=str(target_loc_id), httponly=False, max_age=86400 * 7, path="/", samesite="lax")
    return response

@router.get("/logout")
def logout_action(request: Request, db: Session = Depends(get_db)):
    session_log_id_cookie = request.cookies.get("session_log_id")
    user_id_cookie = request.cookies.get("user_id")
    now = datetime.utcnow()

    if session_log_id_cookie:
        try:
            s_id = int(session_log_id_cookie)
            sess = db.query(models.UserSessionLog).filter(models.UserSessionLog.id == s_id).first()
            if sess and sess.is_active_session:
                sess.logout_time = now
                sess.duration_seconds = max(0, int((now - sess.login_time).total_seconds()))
                sess.is_active_session = False
                db.commit()
        except Exception:
            pass
    elif user_id_cookie:
        try:
            u_id = int(user_id_cookie)
            sess = db.query(models.UserSessionLog).filter(
                models.UserSessionLog.user_id == u_id,
                models.UserSessionLog.is_active_session == True
            ).order_by(models.UserSessionLog.id.desc()).first()
            if sess:
                sess.logout_time = now
                sess.duration_seconds = max(0, int((now - sess.login_time).total_seconds()))
                sess.is_active_session = False
                db.commit()
        except Exception:
            pass

    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="user_id")
    response.delete_cookie(key="session_log_id")
    return response

@router.get("/signup", response_class=HTMLResponse)
def signup_view(
    request: Request,
    error: Optional[str] = None,
    success: Optional[str] = None,
    db: Session = Depends(get_db)
):
    locations = db.query(models.Location).filter(models.Location.is_active == True).order_by(models.Location.name.asc()).all()
    departments = db.query(models.Department).order_by(models.Department.name.asc()).all()
    today = date.today()

    return templates.TemplateResponse(
        request=request,
        name="signup.html",
        context={
            "user": None,
            "locations": locations,
            "departments": departments,
            "today": today,
            "error": error,
            "success": success
        }
    )

@router.post("/signup", response_class=HTMLResponse)
def signup_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    unique_id: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    location_id: int = Form(...),
    department_id: Optional[int] = Form(None),
    role_title: Optional[str] = Form(None),
    phone_number: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    clean_name = name.strip()
    clean_email = email.strip().lower()
    clean_uid = unique_id.strip().upper()

    locations = db.query(models.Location).filter(models.Location.is_active == True).order_by(models.Location.name.asc()).all()
    departments = db.query(models.Department).order_by(models.Department.name.asc()).all()
    today = date.today()

    if password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="signup.html",
            context={"user": None, "locations": locations, "departments": departments, "today": today, "error": "Passwords do not match."}
        )

    if len(password) < 6:
        return templates.TemplateResponse(
            request=request,
            name="signup.html",
            context={"user": None, "locations": locations, "departments": departments, "today": today, "error": "Password must be at least 6 characters."}
        )

    existing = db.query(models.User).filter((models.User.email == clean_email) | (models.User.unique_id == clean_uid)).first()
    if existing:
        return templates.TemplateResponse(
            request=request,
            name="signup.html",
            context={"user": None, "locations": locations, "departments": departments, "today": today, "error": "An account with this Email or Employee ID already exists."}
        )

    new_user = models.User(
        name=clean_name,
        email=clean_email,
        unique_id=clean_uid,
        hashed_password=get_password_hash(password),
        location_id=location_id,
        department_id=department_id,
        role_title=role_title.strip() if role_title else "Operational Staff",
        access_level="Employee",
        is_active=True
    )
    db.add(new_user)
    db.flush()

    def_cl = float(get_company_setting_val("annual_cl_quota", "12.0", db))
    def_sl = float(get_company_setting_val("annual_sl_quota", "9.0", db))
    def_pl = float(get_company_setting_val("annual_pl_quota", "15.0", db))

    new_user.eligible_cl = def_cl
    new_user.eligible_sl = def_sl
    new_user.balance_cl = def_cl
    new_user.balance_sl = def_sl
    new_user.cl_balance = def_cl
    new_user.sl_balance = def_sl
    new_user.pl_balance = def_pl

    current_period = date.today().strftime("%b-%y")
    loc_obj = db.query(models.Location).filter(models.Location.id == location_id).first()
    leave_balance = models.LeaveBalance(
        user_id=new_user.id,
        unique_id=clean_uid,
        name=clean_name,
        location=loc_obj.name if loc_obj else "MUMBAI",
        month_year=current_period,
        eligible_cl=def_cl,
        eligible_sl=def_sl,
        balance_cl=def_cl,
        balance_sl=def_sl,
        balance_co=0.0
    )
    db.add(leave_balance)
    db.commit()

    return templates.TemplateResponse(
        request=request,
        name="signup.html",
        context={"user": None, "locations": locations, "departments": departments, "today": today, "success": f"Account for {clean_name} ({clean_uid}) created successfully! You can now log in."}
    )

@router.get("/switch-persona")
def switch_persona(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="user_id", value=str(user.id), httponly=True, max_age=86400 * 7, path="/", samesite="lax")
        return response
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
