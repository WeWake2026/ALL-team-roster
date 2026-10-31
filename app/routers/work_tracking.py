from datetime import date, datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.auth import require_auth
from app.core.audit import log_audit_event
import models

router = APIRouter(prefix="/api/work", tags=["Work & Break Tracking"])

@router.post("/start-shift")
def start_work_shift(
    user: models.User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    today = date.today()
    now = datetime.utcnow()

    sess = db.query(models.WorkSession).filter(
        models.WorkSession.user_id == user.id,
        models.WorkSession.session_date == today
    ).order_by(models.WorkSession.id.desc()).first()

    if sess and sess.status in ["ACTIVE", "ON_BREAK"]:
        return JSONResponse({"status": "error", "message": "You already have an active shift session in progress."})

    new_sess = models.WorkSession(
        user_id=user.id,
        session_date=today,
        start_time=now,
        status="ACTIVE"
    )
    db.add(new_sess)
    db.commit()

    log_audit_event(
        db=db,
        actor=user,
        action="WORK_SHIFT_START",
        resource_type="WorkSession",
        resource_id=str(new_sess.id),
        details=f"Employee {user.name} started operational work session at {now.strftime('%H:%M:%S UTC')}."
    )

    return JSONResponse({"status": "success", "message": "Work shift started successfully!", "session_id": new_sess.id})

@router.post("/end-shift")
def end_work_shift(
    user: models.User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    today = date.today()
    now = datetime.utcnow()

    sess = db.query(models.WorkSession).filter(
        models.WorkSession.user_id == user.id,
        models.WorkSession.session_date == today,
        models.WorkSession.status.in_(["ACTIVE", "ON_BREAK"])
    ).order_by(models.WorkSession.id.desc()).first()

    if not sess:
        return JSONResponse({"status": "error", "message": "No active shift session found to complete."})

    if sess.status == "ON_BREAK":
        open_brk = db.query(models.SessionBreak).filter(
            models.SessionBreak.session_id == sess.id,
            models.SessionBreak.end_time == None
        ).first()
        if open_brk:
            open_brk.end_time = now
            open_brk.duration_mins = max(0, int((now - open_brk.start_time).total_seconds() / 60))

    sess.end_time = now
    sess.status = "COMPLETED"

    gross_mins = max(0, int((now - sess.start_time).total_seconds() / 60))
    breaks = db.query(models.SessionBreak).filter(models.SessionBreak.session_id == sess.id).all()
    total_brk_mins = sum(b.duration_mins for b in breaks)
    net_mins = max(0, gross_mins - total_brk_mins)

    sess.gross_duration_mins = gross_mins
    sess.total_break_mins = total_brk_mins
    sess.net_work_mins = net_mins
    db.commit()

    log_audit_event(
        db=db,
        actor=user,
        action="WORK_SHIFT_END",
        resource_type="WorkSession",
        resource_id=str(sess.id),
        details=f"Employee {user.name} completed shift. Gross: {gross_mins}m, Breaks: {total_brk_mins}m, Net Productive: {net_mins}m."
    )

    return JSONResponse({
        "status": "success",
        "message": f"Shift completed! Net working time: {net_mins // 60}h {net_mins % 60}m.",
        "gross_mins": gross_mins,
        "net_mins": net_mins
    })

@router.post("/start-break")
def start_work_break(
    request: Request,
    break_type: str = Form("Lunch"),
    user: models.User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    today = date.today()
    now = datetime.utcnow()

    sess = db.query(models.WorkSession).filter(
        models.WorkSession.user_id == user.id,
        models.WorkSession.session_date == today,
        models.WorkSession.status == "ACTIVE"
    ).order_by(models.WorkSession.id.desc()).first()

    if not sess:
        return JSONResponse({"status": "error", "message": "You must have an active working shift to take a break."})

    new_brk = models.SessionBreak(
        session_id=sess.id,
        break_type=break_type.strip(),
        start_time=now
    )
    sess.status = "ON_BREAK"
    db.add(new_brk)
    db.commit()

    return JSONResponse({"status": "success", "message": f"{break_type} break started.", "break_id": new_brk.id})

@router.post("/end-break")
def end_work_break(
    user: models.User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    today = date.today()
    now = datetime.utcnow()

    sess = db.query(models.WorkSession).filter(
        models.WorkSession.user_id == user.id,
        models.WorkSession.session_date == today,
        models.WorkSession.status == "ON_BREAK"
    ).order_by(models.WorkSession.id.desc()).first()

    if not sess:
        return JSONResponse({"status": "error", "message": "No active break found to end."})

    open_brk = db.query(models.SessionBreak).filter(
        models.SessionBreak.session_id == sess.id,
        models.SessionBreak.end_time == None
    ).order_by(models.SessionBreak.id.desc()).first()

    if open_brk:
        open_brk.end_time = now
        dur = max(0, int((now - open_brk.start_time).total_seconds() / 60))
        open_brk.duration_mins = dur

        all_breaks = db.query(models.SessionBreak).filter(models.SessionBreak.session_id == sess.id).all()
        cumulative_break_mins = sum(b.duration_mins for b in all_breaks)

        # Flag excess:
        # 1. Individual break limits: Lunch > 45 mins, Tea > 15 mins
        # 2. Cumulative shift break limit: Total Breaks > 60 mins (1 hour)
        is_individual_excess = (
            (open_brk.break_type.lower() == "lunch" and dur > 45) or
            (open_brk.break_type.lower() == "tea" and dur > 15) or
            (open_brk.break_type.lower() == "dinner" and dur > 45)
        )
        is_total_excess = cumulative_break_mins > 60

        if is_individual_excess or is_total_excess:
            open_brk.is_excess = True

        sess.total_break_mins = cumulative_break_mins

    sess.status = "ACTIVE"
    db.commit()

    return JSONResponse({
        "status": "success",
        "message": f"Break ended! Resumed active duty. (Today's total breaks: {cumulative_break_mins}m / 60m allowed)",
        "duration_mins": open_brk.duration_mins if open_brk else 0,
        "total_break_mins": cumulative_break_mins,
        "is_excess": open_brk.is_excess if open_brk else False
    })
