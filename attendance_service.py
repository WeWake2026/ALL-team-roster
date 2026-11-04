import calendar
from datetime import date, datetime, timedelta
import io
import csv
from sqlalchemy.orm import Session
import models

def compute_user_monthly_attendance(user_id: int, year: int, month: int, db: Session):
    """
    Computes daily attendance matrix and monthly summary KPIs for a specific employee.
    Strictly scoped to user_id.
    """
    num_days = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, num_days)
    today = date.today()

    # Query user details
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return None

    # 1. Query Roster Entries for the month
    roster_entries = db.query(models.RosterEntry).filter(
        models.RosterEntry.user_id == user_id,
        models.RosterEntry.date >= start_date,
        models.RosterEntry.date <= end_date
    ).all()
    roster_map = {r.date: r for r in roster_entries}

    # 2. Query Approved Leaves for the month
    approved_leaves = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.user_id == user_id,
        models.LeaveRequest.status == "Approved",
        models.LeaveRequest.start_date <= end_date,
        models.LeaveRequest.end_date >= start_date
    ).all()

    leave_map = {}
    for al in approved_leaves:
        curr = max(al.start_date, start_date)
        last = min(al.end_date, end_date)
        while curr <= last:
            leave_map[curr] = al
            curr += timedelta(days=1)

    # 3. Query Holidays for the month
    holidays = db.query(models.Holiday).filter(
        models.Holiday.date >= start_date,
        models.Holiday.date <= end_date
    ).all()
    holiday_map = {h.date: h.name for h in holidays}

    # 4. Query WorkSessions for the month
    work_sessions = db.query(models.WorkSession).filter(
        models.WorkSession.user_id == user_id,
        models.WorkSession.session_date >= start_date,
        models.WorkSession.session_date <= end_date
    ).all()
    session_map = {ws.session_date: ws for ws in work_sessions}

    # 5. Query Biometric Punches
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())
    punches = db.query(models.BiometricPunchLog).filter(
        models.BiometricPunchLog.user_id == user_id,
        models.BiometricPunchLog.punch_time >= start_dt,
        models.BiometricPunchLog.punch_time <= end_dt
    ).all()
    punch_map = {}
    for p in punches:
        p_date = p.punch_time.date()
        if p_date not in punch_map:
            punch_map[p_date] = []
        punch_map[p_date].append(p)

    # Daily breakdown list
    daily_records = []
    
    # Summary Counters
    present_days = 0
    absent_days = 0
    weekly_offs = 0
    holiday_days = 0
    approved_leave_days = 0
    half_days = 0
    late_marks = 0
    scheduled_working_days = 0
    total_working_minutes = 0

    for day_num in range(1, num_days + 1):
        cur_date = date(year, month, day_num)
        is_future = cur_date > today
        weekday_name = cur_date.strftime("%a")

        r_entry = roster_map.get(cur_date)
        app_leave = leave_map.get(cur_date)
        holiday_name = holiday_map.get(cur_date)
        w_sess = session_map.get(cur_date)
        day_punches = punch_map.get(cur_date, [])

        shift_str = r_entry.shift_code_or_time if r_entry else ("Leave" if app_leave else "Not Scheduled")
        status_str = r_entry.status if r_entry else ("Leave" if app_leave else "Not Scheduled")

        # Determine shift timings
        shift_timing = shift_str
        if any(t in shift_str for t in [":", "07:00", "09:00", "11:00", "13:00", "16:00", "18:00", "20:00", "22:00"]):
            shift_timing = shift_str
        elif False:
            s_obj = db.query(models.Shift).filter(models.Shift.id == r_entry.shift_id).first()
            if s_obj:
                shift_timing = f"{s_obj.start_time} - {s_obj.end_time}"

        # Actual Punch in/out
        login_time_str = "--"
        logout_time_str = "--"
        work_hours_str = "--"
        net_mins = 0

        if w_sess:
            if w_sess.start_time:
                login_time_str = w_sess.start_time.strftime("%I:%M %p")
            if w_sess.end_time:
                logout_time_str = w_sess.end_time.strftime("%I:%M %p")
            net_mins = w_sess.net_work_mins or 0
        elif day_punches:
            sorted_punches = sorted(day_punches, key=lambda x: x.punch_time)
            login_time_str = sorted_punches[0].punch_time.strftime("%I:%M %p")
            if len(sorted_punches) > 1:
                logout_time_str = sorted_punches[-1].punch_time.strftime("%I:%M %p")
                net_mins = int((sorted_punches[-1].punch_time - sorted_punches[0].punch_time).total_seconds() / 60)
            else:
                logout_time_str = "--"

        if net_mins > 0:
            hrs = net_mins // 60
            mins = net_mins % 60
            work_hours_str = f"{hrs}h {mins:02d}m"
            total_working_minutes += net_mins

        u_shift = shift_str.strip().upper()
        u_status = status_str.strip().upper()

        code = "NOT_SCHEDULED"
        badge_label = "Not Scheduled"
        badge_color = "slate" # grey

        is_wo = (u_shift == "WO" or u_status == "WO")
        is_co = (u_shift in ["CO", "COMP-OFF"] or u_status == "CO")
        is_leave = bool(app_leave) or u_shift in ["CL", "SL", "PL", "LEAVE"] or u_status in ["LEAVE", "CL", "SL"]
        is_hd = (u_shift in ["HD", "HALF-DAY", "HALF DAY", "P+HD"] or u_status == "HD")
        is_absent = (u_shift in ["A", "ABSENT"] or u_status == "ABSENT")
        is_present_shift = (
            any(t in u_shift for t in [":", "07:00", "09:00", "11:00", "13:00", "16:00", "18:00", "20:00", "22:00"]) or
            u_shift in ["P", "S", "PRESENT"] or
            u_status in ["PRESENT", "SCHEDULED"]
        )

        # Check late mark: login > shift_start + 15m
        is_late = False
        if w_sess and w_sess.start_time and r_entry and ":" in shift_timing:
            try:
                shift_start_part = shift_timing.split("-")[0].strip().split(" ")[0].strip()
                if ":" in shift_start_part:
                    sh, sm = map(int, shift_start_part.split(":")[:2])
                    sess_local = w_sess.start_time + timedelta(hours=5, minutes=30)
                    if (sess_local.hour > sh) or (sess_local.hour == sh and sess_local.minute > sm + 15):
                        is_late = True
            except Exception:
                pass

        if holiday_name and not is_present_shift and not w_sess:
            code = "HOLIDAY"
            badge_label = f"Holiday: {holiday_name}"
            badge_color = "slate"
            holiday_days += 1
        elif is_wo:
            code = "WO"
            badge_label = "Weekly Off (WO)"
            badge_color = "blue"
            weekly_offs += 1
        elif is_co:
            code = "CO"
            badge_label = "Comp-Off (CO)"
            badge_color = "blue"
            weekly_offs += 1
        elif is_leave:
            leave_type = app_leave.leave_type if app_leave else (u_shift if u_shift in ["CL", "SL", "PL"] else "Leave")
            code = "LEAVE"
            badge_label = f"Leave ({leave_type})"
            badge_color = "purple"
            approved_leave_days += 1
        elif is_hd:
            code = "HALF_DAY"
            badge_label = "Half Day"
            badge_color = "amber"
            half_days += 1
            present_days += 1
            scheduled_working_days += 1
        elif is_late:
            code = "LATE"
            badge_label = "Late Mark"
            badge_color = "amber"
            late_marks += 1
            present_days += 1
            scheduled_working_days += 1
        elif is_absent:
            code = "ABSENT"
            badge_label = "Absent"
            badge_color = "red"
            absent_days += 1
            scheduled_working_days += 1
        elif is_present_shift:
            scheduled_working_days += 1
            if is_future:
                code = "SCHEDULED"
                badge_label = f"Scheduled ({shift_str})"
                badge_color = "slate"
            elif w_sess or day_punches or u_status == "PRESENT" or u_status == "SCHEDULED":
                code = "PRESENT"
                badge_label = "Present"
                badge_color = "emerald"
                present_days += 1
            else:
                code = "ABSENT"
                badge_label = "Absent / Unpunched"
                badge_color = "red"
                absent_days += 1
        else:
            if holiday_name:
                code = "HOLIDAY"
                badge_label = f"Holiday: {holiday_name}"
                badge_color = "slate"
                holiday_days += 1
            else:
                code = "NOT_SCHEDULED"
                badge_label = "Not Scheduled"
                badge_color = "slate"

        daily_records.append({
            "day": day_num,
            "date": cur_date,
            "date_str": cur_date.strftime("%Y-%m-%d"),
            "weekday": weekday_name,
            "is_today": (cur_date == today),
            "is_future": is_future,
            "code": code,
            "badge_label": badge_label,
            "badge_color": badge_color,
            "shift_name": shift_str,
            "shift_timing": shift_timing,
            "login_time": login_time_str,
            "logout_time": logout_time_str,
            "work_hours": work_hours_str,
            "status_text": status_str,
            "holiday_name": holiday_name,
            "notes": w_sess.notes if w_sess and w_sess.notes else ("" if not holiday_name else f"Holiday: {holiday_name}")
        })

    # Total work hours string
    tot_hrs = total_working_minutes // 60
    tot_mins = total_working_minutes % 60
    total_work_hours_str = f"{tot_hrs}h {tot_mins:02d}m"

    # Pending leave counts for employee
    pending_leaves = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.user_id == user_id,
        models.LeaveRequest.status == "Pending"
    ).all()
    pending_cl = sum(l.duration_days for l in pending_leaves if l.leave_type == "CL")
    pending_sl = sum(l.duration_days for l in pending_leaves if l.leave_type == "SL")
    pending_co = sum(l.duration_days for l in pending_leaves if l.leave_type in ["CO", "Comp-Off"])

    # Leave balances with total, used, pending, remaining
    cl_entitled = user.eligible_cl or 10.0
    cl_used = user.taken_cl or 0.0
    cl_remaining = user.balance_cl if user.balance_cl is not None else (user.cl_balance if user.cl_balance is not None else (cl_entitled - cl_used))

    sl_entitled = user.eligible_sl or 7.5
    sl_used = user.taken_sl or 0.0
    sl_remaining = user.balance_sl if user.balance_sl is not None else (user.sl_balance if user.sl_balance is not None else (sl_entitled - sl_used))

    co_entitled = (user.balance_co or 0.0) + (user.taken_co or 0.0) if hasattr(user, 'taken_co') and user.taken_co else (user.balance_co or 0.0)
    co_used = getattr(user, 'taken_co', 0.0) or 0.0
    co_remaining = user.balance_co if user.balance_co is not None else (user.co_balance or 0.0)

    leave_summary = {
        "CL": {
            "title": "Casual Leave (CL)",
            "entitled": round(cl_entitled, 2),
            "used": round(cl_used, 2),
            "pending": round(pending_cl, 2),
            "remaining": round(cl_remaining, 2)
        },
        "SL": {
            "title": "Sick Leave (SL)",
            "entitled": round(sl_entitled, 2),
            "used": round(sl_used, 2),
            "pending": round(pending_sl, 2),
            "remaining": round(sl_remaining, 2)
        },
        "CO": {
            "title": "Comp-Off (CO)",
            "entitled": round(co_entitled, 2),
            "used": round(co_used, 2),
            "pending": round(pending_co, 2),
            "remaining": round(co_remaining, 2)
        }
    }

    return {
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "month_label": f"{calendar.month_name[month]} {year}",
        "num_days": num_days,
        "first_weekday": calendar.monthrange(year, month)[0], # 0 is Monday
        "user_id": user_id,
        "user_name": user.name,
        "unique_id": user.unique_id,
        "employee_id": user.unique_id,
        "full_name": user.name,
        "summary": {
            "present_days": present_days,
            "absent_days": absent_days,
            "weekly_offs": weekly_offs,
            "holidays": holiday_days,
            "approved_leave_days": approved_leave_days,
            "half_days": half_days,
            "late_marks": late_marks,
            "scheduled_working_days": scheduled_working_days,
            "total_work_hours": total_work_hours_str
        },
        "metrics": {
            "present_days": present_days,
            "absent_days": absent_days,
            "weekly_offs": weekly_offs,
            "holidays": holiday_days,
            "approved_leave_days": approved_leave_days,
            "half_days": half_days,
            "late_marks": late_marks,
            "scheduled_working_days": scheduled_working_days,
            "total_work_hours": total_work_hours_str
        },
        "daily_records": daily_records,
        "leave_summary": leave_summary
    }

# ================= EXPORT GENERATORS (Excel, PDF, CSV) ================= #

def generate_employee_attendance_excel(data: dict) -> io.BytesIO:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Monthly Attendance"
    ws.views.sheetView[0].showGridLines = True

    font_title = Font(name="Calibri", size=15, bold=True, color="1E3A8A")
    font_sub = Font(name="Calibri", size=10, bold=False, color="475569")
    font_header = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    font_bold = Font(name="Calibri", size=10, bold=True, color="0F172A")
    font_regular = Font(name="Calibri", size=10, color="334155")
    
    fill_header = PatternFill("solid", fgColor="1E293B")
    fill_present = PatternFill("solid", fgColor="DCFCE7") # emerald-100
    fill_absent = PatternFill("solid", fgColor="FEE2E2")  # rose-100
    fill_wo = PatternFill("solid", fgColor="DBEAFE")      # blue-100
    fill_leave = PatternFill("solid", fgColor="F3E8FF")   # purple-100
    fill_hd = PatternFill("solid", fgColor="FEF3C7")      # amber-100

    thin_border = Border(
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0')
    )

    # Title Banner
    ws.merge_cells("A1:G1")
    ws["A1"] = f"MSEDCL ShiftFlow - Monthly Attendance & Workforce Report"
    ws["A1"].font = font_title
    ws["A1"].alignment = Alignment(vertical="center")

    ws.merge_cells("A2:G2")
    ws["A2"] = f"Employee: {data['user_name']} ({data['unique_id']})  |  Month: {data['month_label']}"
    ws["A2"].font = font_sub
    ws["A2"].alignment = Alignment(vertical="center")

    # Metrics Summary Row
    m = data["metrics"]
    ws["A4"] = "Summary Metric"
    ws["B4"] = "Days / Value"
    ws["D4"] = "Leave Category"
    ws["E4"] = "Entitled"
    ws["F4"] = "Used"
    ws["G4"] = "Remaining"

    for col in ["A", "B", "D", "E", "F", "G"]:
        cell = ws[f"{col}4"]
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center")

    kpi_rows = [
        ("Scheduled Working Days", m["scheduled_working_days"]),
        ("Present Days", m["present_days"]),
        ("Absent Days", m["absent_days"]),
        ("Weekly Offs (WO/CO)", m["weekly_offs"]),
        ("Holidays", m["holidays"]),
        ("Approved Leaves", m["approved_leave_days"]),
        ("Half Days", m["half_days"]),
        ("Late Marks", m["late_marks"]),
        ("Total Working Hours", m["total_work_hours"])
    ]

    for idx, (label, val) in enumerate(kpi_rows):
        r = 5 + idx
        ws[f"A{r}"] = label
        ws[f"A{r}"].font = font_regular
        ws[f"A{r}"].border = thin_border

        ws[f"B{r}"] = val
        ws[f"B{r}"].font = font_bold
        ws[f"B{r}"].alignment = Alignment(horizontal="center")
        ws[f"B{r}"].border = thin_border

    # Fill Leave Summary (cols D-G)
    ls = data["leave_summary"]
    leave_list = [ls["CL"], ls["SL"], ls["CO"]]
    for idx, item in enumerate(leave_list):
        r = 5 + idx
        ws[f"D{r}"] = item["title"]
        ws[f"D{r}"].font = font_regular
        ws[f"D{r}"].border = thin_border

        ws[f"E{r}"] = item["entitled"]
        ws[f"E{r}"].font = font_bold
        ws[f"E{r}"].alignment = Alignment(horizontal="center")
        ws[f"E{r}"].border = thin_border

        ws[f"F{r}"] = item["used"]
        ws[f"F{r}"].font = font_bold
        ws[f"F{r}"].alignment = Alignment(horizontal="center")
        ws[f"F{r}"].border = thin_border

        ws[f"G{r}"] = item["remaining"]
        ws[f"G{r}"].font = font_bold
        ws[f"G{r}"].alignment = Alignment(horizontal="center")
        ws[f"G{r}"].border = thin_border

    # Attendance Daily Table
    start_row = 16
    headers = ["Date", "Day", "Shift Schedule", "Login Time", "Logout Time", "Duration", "Attendance Status"]
    for col_idx, h in enumerate(headers, 1):
        col_letter = get_column_letter(col_idx)
        cell = ws[f"{col_letter}{start_row}"]
        cell.value = h
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    for i, rec in enumerate(data["daily_records"]):
        curr_r = start_row + 1 + i
        ws[f"A{curr_r}"] = rec["date_str"]
        ws[f"B{curr_r}"] = rec["weekday"]
        ws[f"C{curr_r}"] = rec["shift_timing"]
        ws[f"D{curr_r}"] = rec["login_time"]
        ws[f"E{curr_r}"] = rec["logout_time"]
        ws[f"F{curr_r}"] = rec["work_hours"]
        ws[f"G{curr_r}"] = rec["badge_label"]

        status_fill = None
        if rec["code"] in ["PRESENT", "SCHEDULED"]:
            status_fill = fill_present
        elif rec["code"] == "ABSENT":
            status_fill = fill_absent
        elif rec["code"] in ["WO", "CO"]:
            status_fill = fill_wo
        elif rec["code"] == "LEAVE":
            status_fill = fill_leave
        elif rec["code"] in ["HALF_DAY", "LATE"]:
            status_fill = fill_hd

        for col_idx in range(1, 8):
            col_letter = get_column_letter(col_idx)
            c = ws[f"{col_letter}{curr_r}"]
            c.font = font_regular
            c.border = thin_border
            if col_idx in [1, 2, 4, 5, 6]:
                c.alignment = Alignment(horizontal="center")
            if col_idx == 7 and status_fill:
                c.fill = status_fill
                c.font = font_bold

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

def generate_employee_attendance_csv(data: dict) -> io.BytesIO:
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["MSEDCL ShiftFlow - Monthly Attendance Report"])
    writer.writerow(["Employee", f"{data['user_name']} ({data['unique_id']})"])
    writer.writerow(["Reporting Period", data['month_label']])
    writer.writerow([])

    writer.writerow(["Metric", "Count"])
    for k, v in data["metrics"].items():
        writer.writerow([k.replace("_", " ").title(), v])
    writer.writerow([])

    writer.writerow(["Leave Type", "Entitled", "Used", "Pending", "Remaining"])
    for item in data["leave_summary"].values():
        writer.writerow([item["title"], item["entitled"], item["used"], item["pending"], item["remaining"]])
    writer.writerow([])

    writer.writerow(["Date", "Day", "Shift Schedule", "Login Time", "Logout Time", "Duration", "Status", "Notes"])
    for rec in data["daily_records"]:
        writer.writerow([
            rec["date_str"],
            rec["weekday"],
            rec["shift_timing"],
            rec["login_time"],
            rec["logout_time"],
            rec["work_hours"],
            rec["badge_label"],
            rec["notes"]
        ])

    bytes_buf = io.BytesIO(buf.getvalue().encode('utf-8'))
    bytes_buf.seek(0)
    return bytes_buf

def generate_employee_attendance_pdf(data: dict) -> io.BytesIO:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#1E3A8A'),
        fontName='Helvetica-Bold'
    )
    sub_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#475569'),
        fontName='Helvetica'
    )
    th_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.white,
        fontName='Helvetica-Bold',
        alignment=1
    )
    td_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#0F172A'),
        fontName='Helvetica',
        alignment=1
    )

    elements = []

    # Title & Metadata
    elements.append(Paragraph("MSEDCL ShiftFlow - Monthly Employee Attendance Report", title_style))
    elements.append(Paragraph(f"<b>Employee:</b> {data['user_name']} ({data['unique_id']}) &nbsp;&nbsp;|&nbsp;&nbsp; <b>Month:</b> {data['month_label']} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Generated:</b> {datetime.now().strftime('%d-%b-%Y %I:%M %p')}", sub_style))
    elements.append(Spacer(1, 12))

    # Summary KPIs Table
    m = data["metrics"]
    kpi_data = [
        [
            Paragraph("<b>Scheduled Days</b>", td_style),
            Paragraph("<b>Present Days</b>", td_style),
            Paragraph("<b>Absent Days</b>", td_style),
            Paragraph("<b>Weekly Offs</b>", td_style),
            Paragraph("<b>Holidays</b>", td_style),
            Paragraph("<b>Approved Leaves</b>", td_style),
            Paragraph("<b>Half Days</b>", td_style),
            Paragraph("<b>Late Marks</b>", td_style),
            Paragraph("<b>Total Work Hours</b>", td_style)
        ],
        [
            str(m["scheduled_working_days"]),
            str(m["present_days"]),
            str(m["absent_days"]),
            str(m["weekly_offs"]),
            str(m["holidays"]),
            str(m["approved_leave_days"]),
            str(m["half_days"]),
            str(m["late_marks"]),
            str(m["total_work_hours"])
        ]
    ]

    t_kpi = Table(kpi_data, colWidths=[80]*9)
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
        ('BACKGROUND', (0,1), (-1,1), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,1), (-1,1), 10),
        ('TEXTCOLOR', (0,1), (-1,1), colors.HexColor('#1E293B')),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 5),
    ]))
    elements.append(t_kpi)
    elements.append(Spacer(1, 14))

    # Daily Table
    daily_rows = [
        [
            Paragraph("<b>Date</b>", th_style),
            Paragraph("<b>Day</b>", th_style),
            Paragraph("<b>Shift Timing</b>", th_style),
            Paragraph("<b>In Time</b>", th_style),
            Paragraph("<b>Out Time</b>", th_style),
            Paragraph("<b>Hours</b>", th_style),
            Paragraph("<b>Status</b>", th_style),
            Paragraph("<b>Notes / Remarks</b>", th_style)
        ]
    ]

    for rec in data["daily_records"]:
        daily_rows.append([
            Paragraph(rec["date_str"], td_style),
            Paragraph(rec["weekday"], td_style),
            Paragraph(rec["shift_timing"], td_style),
            Paragraph(rec["login_time"], td_style),
            Paragraph(rec["logout_time"], td_style),
            Paragraph(rec["work_hours"], td_style),
            Paragraph(rec["badge_label"], td_style),
            Paragraph(rec["notes"] or "--", td_style)
        ])

    col_widths = [65, 35, 120, 60, 60, 60, 140, 180]
    t_daily = Table(daily_rows, colWidths=col_widths, repeatRows=1)
    
    t_style = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E293B')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]

    for r_idx, rec in enumerate(data["daily_records"], 1):
        if rec["code"] in ["PRESENT", "SCHEDULED"]:
            t_style.append(('BACKGROUND', (6, r_idx), (6, r_idx), colors.HexColor('#DCFCE7')))
        elif rec["code"] == "ABSENT":
            t_style.append(('BACKGROUND', (6, r_idx), (6, r_idx), colors.HexColor('#FEE2E2')))
        elif rec["code"] in ["WO", "CO"]:
            t_style.append(('BACKGROUND', (6, r_idx), (6, r_idx), colors.HexColor('#DBEAFE')))
        elif rec["code"] == "LEAVE":
            t_style.append(('BACKGROUND', (6, r_idx), (6, r_idx), colors.HexColor('#F3E8FF')))
        elif rec["code"] in ["HALF_DAY", "LATE"]:
            t_style.append(('BACKGROUND', (6, r_idx), (6, r_idx), colors.HexColor('#FEF3C7')))
        elif r_idx % 2 == 0:
            t_style.append(('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor('#F8FAFC')))

    t_daily.setStyle(TableStyle(t_style))
    elements.append(t_daily)

    doc.build(elements)
    buf.seek(0)
    return buf
