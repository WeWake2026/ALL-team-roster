import re
from datetime import datetime, date, timedelta
from io import BytesIO
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session
import models

def normalize_header(header: str) -> str:
    if not isinstance(header, str):
        return ""
    return re.sub(r'[^a-zA-Z0-9]', '', header).upper()

def parse_date_str(val: Any) -> str:
    """
    Extract standard YYYY-MM-DD date string from header or date object.
    Strictly validates that year is realistic (e.g. 2020-2035) to avoid false matches
    like 'SUNDAY.1' parsing to '0001-01-01'.
    """
    if isinstance(val, (datetime, date)):
        if val.year >= 2020 and val.year <= 2035:
            return val.strftime("%Y-%m-%d")
        return ""
    
    s = str(val).strip()
    if not s or s.upper() in ["NAN", "NONE", "-", "=", "SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]:
        return ""

    m1 = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})', s)
    if m1:
        y, m, d = m1.groups()
        if int(y) >= 2020 and int(y) <= 2035:
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        return ""

    m2 = re.match(r'^(\d{1,2})[-/](\d{1,2})[-/](\d{4})', s)
    if m2:
        d, m, y = m2.groups()
        if int(y) >= 2020 and int(y) <= 2035:
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        return ""

    try:
        # Only parse if looks like a date containing digits
        if any(ch.isdigit() for ch in s):
            dt = pd.to_datetime(s, errors='coerce')
            if pd.notna(dt) and dt.year >= 2020 and dt.year <= 2035:
                return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return ""

def import_roster_file(file_bytes: bytes, filename: str, db: Session, updated_by: str = "Admin") -> Dict[str, Any]:
    """
    Parses an Excel (.xlsx, .xls) or CSV file matching MSEDCL operations format:
    Headers: NO / SR NO., EMPLOYEE NAME, GENDER, UNIQUE ID, CRM ID, BM ID, LOCATION, ECN, EMAIL-ID, ROLE,
    followed by date columns or week day headers (e.g. 2026-11-01, MONDAY, TUESDAY), and summary columns WO, CO, SHIFTS.
    Supports files with top title/metadata banner rows by auto-detecting the header row and inspecting banner rows for dates.
    """
    banner_dates_by_col = {}

    if filename.lower().endswith('.csv'):
        df_raw = pd.read_csv(BytesIO(file_bytes), header=None, nrows=10)
        skip = 0
        for idx, row in df_raw.iterrows():
            vals = [normalize_header(str(v)) for v in row.values if pd.notna(v)]
            if any(k in vals for k in ["UNIQUEID", "EMPLOYEENAME", "EMPNAME", "SRNO", "NO"]):
                skip = idx
                break
        
        # Check rows above the main header for embedded dates (e.g. row 0 having 2026-11-01)
        if skip > 0:
            for r_idx in range(skip):
                brow = df_raw.iloc[r_idx]
                for c_idx, val in enumerate(brow.values):
                    p_dt = parse_date_str(val)
                    if p_dt:
                        banner_dates_by_col[c_idx] = p_dt

        df = pd.read_csv(BytesIO(file_bytes), skiprows=skip)
    else:
        df_raw = pd.read_excel(BytesIO(file_bytes), sheet_name=0, header=None, nrows=10)
        skip = 0
        for idx, row in df_raw.iterrows():
            vals = [normalize_header(str(v)) for v in row.values if pd.notna(v)]
            if any(k in vals for k in ["UNIQUEID", "EMPLOYEENAME", "EMPNAME", "SRNO", "NO"]):
                skip = idx
                break

        # Check rows above the main header for embedded dates (e.g. row 0 having 2026-11-01)
        if skip > 0:
            for r_idx in range(skip):
                brow = df_raw.iloc[r_idx]
                for c_idx, val in enumerate(brow.values):
                    p_dt = parse_date_str(val)
                    if p_dt:
                        banner_dates_by_col[c_idx] = p_dt

        df = pd.read_excel(BytesIO(file_bytes), sheet_name=0, skiprows=skip)

    # Clean header mapping with priority for exact matches
    col_mapping = {}
    date_cols = []

    for col_idx, col in enumerate(df.columns):
        norm = normalize_header(str(col))
        # Exact matching with strict priority for UNIQUEID
        if norm == "UNIQUEID":
            col_mapping["unique_id"] = col
        elif norm in ["EMPLOYEEID", "EMPID"]:
            col_mapping["employee_id"] = col
            if "unique_id" not in col_mapping:
                col_mapping["unique_id"] = col
        elif norm in ["EMPLOYEENAME", "EMPNAME", "NAME"]:
            col_mapping["name"] = col
        elif norm in ["EMAILID", "EMAIL", "MAILID"]:
            col_mapping["email"] = col
        elif norm in ["CRMID", "CRM"]:
            col_mapping["crm_id"] = col
        elif norm in ["BMID", "BM"]:
            col_mapping["bm_id"] = col
        elif norm in ["LOCATION", "CITY"]:
            col_mapping["location"] = col
        elif norm in ["ROLE", "DESIGNATION"]:
            col_mapping["role_title"] = col
        elif norm in ["ECN"]:
            col_mapping["ecn"] = col
        elif norm in ["GENDER"]:
            col_mapping["gender"] = col
        elif norm in ["SRNO", "NO"]:
            col_mapping["sr_no"] = col
        elif norm in ["SHIFTS", "SHIFT", "SHIFTTEMP"]:
            col_mapping["default_shift"] = col
        elif norm in ["WO"]:
            col_mapping["wo_count"] = col
        elif norm in ["CO"]:
            col_mapping["co_count"] = col
        else:
            # First check if the header itself has a valid date
            dt_str = parse_date_str(col)
            # Second check if banner row above had a date for this column
            if not dt_str and col_idx in banner_dates_by_col:
                dt_str = banner_dates_by_col[col_idx]

            if dt_str:
                date_cols.append((col, dt_str))

    # Fallback if unique_id or name was not found by exact match
    if not col_mapping.get("unique_id"):
        for col in df.columns:
            norm = normalize_header(str(col))
            if "UNIQUEID" in norm or (norm.endswith("ID") and norm not in ["CRMID", "BMID", "EMAILID"]):
                col_mapping["unique_id"] = col
                break

    if not col_mapping.get("name"):
        for col in df.columns:
            norm = normalize_header(str(col))
            if "NAME" in norm:
                col_mapping["name"] = col
                break

    if not col_mapping.get("unique_id") and not col_mapping.get("name"):
        raise ValueError("Could not find 'UNIQUE ID' or 'EMPLOYEE NAME' column in the uploaded file.")

    if not date_cols:
        raise ValueError("No valid date columns (e.g. 2026-10-19) were detected in the file headers.")

    created_users = 0
    updated_users = 0
    roster_entries_count = 0

    from auth import get_password_hash
    default_hashed_pwd = get_password_hash("Welcome@123")

    for _, row in df.iterrows():
        name = str(row.get(col_mapping.get("name", ""), "")).strip()
        if not name or name in ["nan", "None", "-", ""] or name.upper() in ["EMPLOYEE NAME", "TOTAL", "PENDING", "ELIGIBLE LEAVE", "MANDAYS", "SHIFT"]:
            continue

        unique_id = str(row.get(col_mapping.get("unique_id", ""), "")).strip()
        # If unique_id is empty or '-', check employee_id or fallback to sr_no/name
        if not unique_id or unique_id in ["nan", "None", "-", ""]:
            emp_id_val = str(row.get(col_mapping.get("employee_id", ""), "")).strip()
            if emp_id_val and emp_id_val not in ["nan", "None", "-", ""]:
                unique_id = emp_id_val
            else:
                sr_val = str(row.get(col_mapping.get("sr_no", ""), "")).strip()
                if sr_val and sr_val.replace(".0", "").isdigit():
                    unique_id = f"EMP_{int(sr_val.replace('.0', '')):03d}"
                else:
                    clean_n = re.sub(r'[^a-zA-Z0-9]', '', name).upper()[:12]
                    unique_id = f"EMP_{clean_n}"
        if unique_id.upper() in ["UNIQUE ID", "ID", "TOTAL", "PENDING", "ELIGIBLE LEAVE", "MANDAYS"]:
            continue
        if name.upper() in ["EMPLOYEE NAME", "TOTAL", "PENDING", "ELIGIBLE LEAVE", "MANDAYS"]:
            continue

        email = str(row.get(col_mapping.get("email", ""), "")).strip()
        if not email or email in ["nan", "None", "-", ""]:
            clean_uid = re.sub(r'[^a-zA-Z0-9]', '', unique_id).lower()
            email = f"{clean_uid}@msedcl.com"

        crm_id = str(row.get(col_mapping.get("crm_id", ""), "")).strip()
        if crm_id in ["nan", "None", "-", ""]: crm_id = None

        bm_id = str(row.get(col_mapping.get("bm_id", ""), "")).strip()
        if bm_id in ["nan", "None", "-", ""]: bm_id = None

        ecn = str(row.get(col_mapping.get("ecn", ""), "")).strip()
        if ecn in ["nan", "None", "-", ""]: ecn = None

        role_title = str(row.get(col_mapping.get("role_title", ""), "Agent")).strip()
        if role_title in ["nan", "None", "-", ""]: role_title = "Agent"

        location = str(row.get(col_mapping.get("location", ""), "Mumbai")).strip()
        if location in ["nan", "None", "-", ""]: location = "Mumbai"

        gender = str(row.get(col_mapping.get("gender", ""), "Not Specified")).strip()
        if gender in ["nan", "None", "-", ""]: gender = "Not Specified"

        # Check existing user
        user = db.query(models.User).filter(
            (models.User.unique_id == unique_id) | (models.User.email == email)
        ).first()

        if user:
            user.name = name
            user.unique_id = unique_id
            if crm_id: user.crm_id = crm_id
            if bm_id: user.bm_id = bm_id
            if ecn: user.ecn = ecn
            user.role_title = role_title
            user.location = location
            user.gender = gender
            updated_users += 1
        else:
            user = models.User(
                unique_id=unique_id,
                name=name,
                email=email,
                crm_id=crm_id,
                bm_id=bm_id,
                ecn=ecn,
                role_title=role_title,
                access_level="Employee",
                location=location,
                gender=gender,
                hashed_password=default_hashed_pwd
            )
            db.add(user)
            db.flush()
            created_users += 1

        # Populate shift entries for each date column
        for orig_col, dt_str in date_cols:
            val = str(row.get(orig_col, "")).strip()
            if not val or val in ["nan", "None", ""]:
                continue

            entry_date = datetime.strptime(dt_str, "%Y-%m-%d").date()
            shift_code = val

            # Derive status from operation codes (P, WO, CO, SL, CL, HD, A, Left)
            upper_val = shift_code.upper()
            if upper_val == "WO":
                status = "WO"
            elif upper_val == "CO":
                status = "CO"
            elif upper_val in ["CL", "SL", "LEAVE", "PL"]:
                status = "Leave"
            elif upper_val == "A":
                status = "Absent"
            elif upper_val == "HD":
                status = "Half-Day"
            elif upper_val in ["P", "S"]:
                status = "Present"
            else:
                status = "Scheduled"

            # Check if entry already exists
            entry = db.query(models.RosterEntry).filter(
                models.RosterEntry.user_id == user.id,
                models.RosterEntry.date == entry_date
            ).first()

            if entry:
                entry.shift_code_or_time = shift_code
                entry.status = status
                entry.updated_by = updated_by
            else:
                entry = models.RosterEntry(
                    user_id=user.id,
                    date=entry_date,
                    shift_code_or_time=shift_code,
                    status=status,
                    updated_by=updated_by
                )
                db.add(entry)
            roster_entries_count += 1

    db.commit()
    return {
        "success": True,
        "created_users": created_users,
        "updated_users": updated_users,
        "roster_entries_count": roster_entries_count,
        "dates_processed": [d[1] for d in date_cols]
    }

def export_roster_excel(start_date: date, end_date: date, role_filter: str, db: Session) -> BytesIO:
    """Generate a high-finish, styled Excel roster spreadsheet matching enterprise operations standards"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Weekly Operations Roster"
    ws.views.sheetView[0].showGridLines = True

    # Color Fills
    navy_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    date_header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    stripe_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    
    # Operations Codes Fills
    present_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid") # #DCFCE7 Emerald 100
    wo_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid") # #F1F5F9 Slate 100
    co_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid") # #FEF3C7 Amber 100
    sl_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid") # #FEE2E2 Rose 100
    cl_fill = PatternFill(start_color="E0E7FF", end_color="E0E7FF", fill_type="solid") # #E0E7FF Indigo 100
    hd_fill = PatternFill(start_color="FFEDD5", end_color="FFEDD5", fill_type="solid") # #FFEDD5 Orange 100
    absent_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

    # Fonts
    title_font = Font(name="Segoe UI", size=14, bold=True, color="FFFFFF")
    meta_font = Font(name="Segoe UI", size=10, italic=True, color="E2E8F0")
    header_font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    bold_cell_font = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
    cell_font = Font(name="Segoe UI", size=9, color="1E293B")
    wo_font = Font(name="Segoe UI", size=9, bold=True, color="64748B")
    present_font = Font(name="Segoe UI", size=9, bold=True, color="166534")
    leave_font = Font(name="Segoe UI", size=9, bold=True, color="991B1B")
    absent_font = Font(name="Segoe UI", size=9, bold=True, color="DC2626")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    curr = start_date
    date_list = []
    while curr <= end_date:
        date_list.append(curr)
        curr += timedelta(days=1)

    total_cols = 10 + len(date_list) + 3 # Metadata + Dates + WO, CO, Shifts
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    ws.row_dimensions[1].height = 36
    b_cell = ws.cell(row=1, column=1)
    b_cell.value = "MSEDCL OPERATIONS WORKFORCE ROSTER"
    b_cell.fill = navy_fill
    b_cell.font = title_font
    b_cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=total_cols)
    ws.row_dimensions[2].height = 20
    sub_cell = ws.cell(row=2, column=1)
    sub_cell.value = f"Schedule Period: {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')} | Exported on: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    sub_cell.fill = navy_fill
    sub_cell.font = meta_font
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")

    # Header Row 3
    headers = ["SR NO.", "EMPLOYEE NAME", "GENDER", "UNIQUE ID", "CRM ID", "BM ID", "LOCATION", "ECN", "EMAIL-ID", "ROLE"]
    for d in date_list:
        headers.append(d.strftime("%Y-%m-%d\n%A"))
    headers.extend(["WO", "CO", "SHIFTS"])

    ws.row_dimensions[3].height = 28
    for col_idx, h_text in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col_idx)
        cell.value = h_text
        is_date = (10 < col_idx <= 10 + len(date_list))
        cell.fill = date_header_fill if is_date else header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border

    # Fetch users and entries
    query = db.query(models.User).filter(models.User.is_active == True)
    if role_filter and role_filter != "All":
        query = query.filter(models.User.role_title == role_filter)
    users = query.order_by(models.User.name.asc()).all()

    current_row = 4
    for idx, user in enumerate(users, start=1):
        ws.row_dimensions[current_row].height = 22
        is_even = (idx % 2 == 0)
        row_fill = stripe_fill if is_even else None

        base_data = [
            idx,
            user.name,
            user.gender or "-",
            user.unique_id,
            user.crm_id or "-",
            user.bm_id or "-",
            user.location or "Mumbai",
            user.ecn or "-",
            user.email,
            user.role_title or "Agent"
        ]

        for col_idx, val in enumerate(base_data, start=1):
            cell = ws.cell(row=current_row, column=col_idx)
            cell.value = val
            cell.font = bold_cell_font if col_idx == 2 else cell_font
            cell.alignment = Alignment(horizontal="center" if col_idx in [1, 3, 4, 5, 6, 8] else "left", vertical="center")
            cell.border = thin_border
            if row_fill:
                cell.fill = row_fill

        entries = db.query(models.RosterEntry).filter(
            models.RosterEntry.user_id == user.id,
            models.RosterEntry.date >= start_date,
            models.RosterEntry.date <= end_date
        ).all()
        entry_map = {e.date: e.shift_code_or_time for e in entries}

        wo_total = 0
        co_total = 0

        for d_idx, d_obj in enumerate(date_list, start=11):
            cell = ws.cell(row=current_row, column=d_idx)
            val = entry_map.get(d_obj, "-")
            cell.value = val
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border

            u_val = str(val).strip().upper()
            if u_val == "WO":
                wo_total += 1
                cell.fill = wo_fill
                cell.font = wo_font
            elif u_val == "CO":
                co_total += 1
                cell.fill = co_fill
                cell.font = wo_font
            elif u_val in ["P", "S"]:
                cell.fill = present_fill
                cell.font = present_font
            elif u_val in ["SL", "LEAVE"]:
                cell.fill = sl_fill
                cell.font = leave_font
            elif u_val in ["CL", "PL"]:
                cell.fill = cl_fill
                cell.font = leave_font
            elif u_val == "HD":
                cell.fill = hd_fill
                cell.font = cell_font
            elif u_val in ["A", "ABSENT"]:
                cell.fill = absent_fill
                cell.font = absent_font
            else:
                if row_fill: cell.fill = row_fill
                cell.font = cell_font

        # WO Count Column
        col_wo = ws.cell(row=current_row, column=11 + len(date_list))
        col_wo.value = wo_total
        col_wo.alignment = Alignment(horizontal="center", vertical="center")
        col_wo.font = bold_cell_font
        col_wo.border = thin_border

        # CO Count Column
        col_co = ws.cell(row=current_row, column=12 + len(date_list))
        col_co.value = co_total
        col_co.alignment = Alignment(horizontal="center", vertical="center")
        col_co.font = bold_cell_font
        col_co.border = thin_border

        # Shifts Column
        col_sh = ws.cell(row=current_row, column=13 + len(date_list))
        col_sh.value = "09:00 To 18:00"
        col_sh.alignment = Alignment(horizontal="center", vertical="center")
        col_sh.font = cell_font
        col_sh.border = thin_border

        current_row += 1

    # Adjust column widths
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        if col[0].column == 1:
            ws.column_dimensions[col_letter].width = 8
        elif col[0].column == 2:
            ws.column_dimensions[col_letter].width = 28
        elif col[0].column in [3, 4, 5, 6, 7, 8]:
            ws.column_dimensions[col_letter].width = 16
        elif col[0].column in [9, 10]:
            ws.column_dimensions[col_letter].width = 26
        else:
            ws.column_dimensions[col_letter].width = 15

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output

def parse_date_safely(val: Any) -> Optional[date]:
    """Parse Date of Joining or EOD safely from string or datetime"""
    if not val or pd.isna(val) or str(val).strip() in ["", "-", "nan", "None"]:
        return None
    if isinstance(val, (datetime, date)):
        return val.date() if isinstance(val, datetime) else val
    s = str(val).strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%b-%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    try:
        dt = pd.to_datetime(s)
        return dt.date()
    except Exception:
        return None

def parse_float_safely(val: Any, default: float = 0.0) -> float:
    """Parse fractional balance values like 0.5, 0.75, 1.5, 2.75"""
    if val is None or pd.isna(val) or str(val).strip() in ["", "-", "nan", "None"]:
        return default
    try:
        return float(val)
    except Exception:
        # Check if comma is used as decimal separator or extra text
        s = re.sub(r'[^0-9.]', '', str(val).strip())
        try:
            return float(s)
        except Exception:
            return default

def parse_leave_statement_pdf(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parses Leave Balance Statement PDF (e.g. 'Leave Balance - IB Mumbai Oct-26.pdf')
    Format columns:
    Sr. No. | UNIQUE CODE | ECN | DATE OF JOINING | EMPLOYEE NAME | BIOMETRIC ID | LOCATION | EOD |
    Eligible CL | Eligible SL | Taken CL | Taken SL | Balance CL | Balance SL
    """
    import pypdf
    reader = pypdf.PdfReader(BytesIO(file_bytes))
    records = []

    # Regex for standard line with 14 tokens
    # e.g.: 1 AIPLCC899 MAH0779 11-04-2025 BHAKTI MAHESH CHAVAN 410407 MUMBAI 11-10-2025 10 7.75 5 7 5 0.75
    line_pattern = re.compile(
        r'^\s*(\d+)\s+([A-Z0-9]+)\s+([A-Z0-9]+)\s+(\d{2}[-/]\d{2}[-/]\d{4})\s+(.+?)\s+(\d+)\s+([A-Za-z]+)\s+(\d{2}[-/]\d{2}[-/]\d{4})\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s*$'
    )

    for page in reader.pages:
        text = page.extract_text()
        if not text:
            continue
        lines = text.split('\n')
        for line in lines:
            line_str = line.strip()
            m = line_pattern.match(line_str)
            if m:
                sr, ucode, ecn, doj_str, name, bmid, loc, eod_str, ecl, esl, tcl, tsl, bcl, bsl = m.groups()
                records.append({
                    "unique_id": ucode.strip(),
                    "ecn": ecn.strip(),
                    "doj": parse_date_safely(doj_str),
                    "name": name.strip(),
                    "bm_id": bmid.strip(),
                    "location": loc.strip(),
                    "eod": parse_date_safely(eod_str),
                    "eligible_cl": parse_float_safely(ecl),
                    "eligible_sl": parse_float_safely(esl),
                    "taken_cl": parse_float_safely(tcl),
                    "taken_sl": parse_float_safely(tsl),
                    "balance_cl": parse_float_safely(bcl),
                    "balance_sl": parse_float_safely(bsl),
                    "balance_co": 0.0
                })
            else:
                # Flexible whitespace split if regex didn't match directly
                tokens = re.split(r'\s+', line_str)
                # Minimum required tokens: sr, ucode, ecn, doj, ... name ..., bmid, loc, eod, 6 floats
                if len(tokens) >= 14 and tokens[0].isdigit() and re.match(r'^[A-Z0-9]+$', tokens[1]):
                    try:
                        ucode = tokens[1]
                        ecn = tokens[2]
                        doj_str = tokens[3]
                        # Last 6 are numbers: ecl, esl, tcl, tsl, bcl, bsl
                        ecl = float(tokens[-6])
                        esl = float(tokens[-5])
                        tcl = float(tokens[-4])
                        tsl = float(tokens[-3])
                        bcl = float(tokens[-2])
                        bsl = float(tokens[-1])
                        eod_str = tokens[-7]
                        loc = tokens[-8]
                        bmid = tokens[-9]
                        name = " ".join(tokens[4:-9])

                        records.append({
                            "unique_id": ucode.strip(),
                            "ecn": ecn.strip(),
                            "doj": parse_date_safely(doj_str),
                            "name": name.strip(),
                            "bm_id": bmid.strip(),
                            "location": loc.strip(),
                            "eod": parse_date_safely(eod_str),
                            "eligible_cl": ecl,
                            "eligible_sl": esl,
                            "taken_cl": tcl,
                            "taken_sl": tsl,
                            "balance_cl": bcl,
                            "balance_sl": bsl,
                            "balance_co": 0.0
                        })
                    except Exception:
                        continue

    return records

def parse_leave_statement_tabular(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """
    Parses Leave Balance Statement Excel (.xlsx, .xls) or CSV
    """
    if filename.lower().endswith('.csv'):
        df = pd.read_csv(BytesIO(file_bytes))
    else:
        df = pd.read_excel(BytesIO(file_bytes))

    # Detect header row if file has title rows like "Leave Balance Recd. - Oct'26"
    target_df = df
    header_found = False
    for i, col in enumerate(df.columns):
        norm = normalize_header(str(col))
        if "UNIQUE" in norm or "ECN" in norm:
            header_found = True
            break

    if not header_found:
        # Search first 10 rows to see if headers are on another row
        for row_idx in range(min(10, len(df))):
            row_vals = [normalize_header(str(v)) for v in df.iloc[row_idx].values]
            if any("UNIQUE" in v for v in row_vals) or any("ECN" in v for v in row_vals):
                new_headers = df.iloc[row_idx].values
                target_df = df.iloc[row_idx + 1:].copy()
                target_df.columns = new_headers
                break

    # Map column headers
    col_map = {}
    for col in target_df.columns:
        col_str = str(col).strip().upper()
        norm = normalize_header(col_str)

        if "UNIQUE" in norm or norm in ["UNIQUEID", "UNIQUECODE"]:
            col_map["unique_id"] = col
        elif norm in ["ECN", "ECNNO"]:
            col_map["ecn"] = col
        elif "JOIN" in norm or norm == "DOJ":
            col_map["doj"] = col
        elif "NAME" in norm:
            col_map["name"] = col
        elif "BIOMETRIC" in norm or norm in ["BMID", "BIOMETRICID"]:
            col_map["bm_id"] = col
        elif "LOCATION" in norm or "CITY" in norm:
            col_map["location"] = col
        elif norm in ["EOD", "ENDOFPROBATION", "CONFIRMATIONDATE"]:
            col_map["eod"] = col
        # Leave columns
        elif "ELIGIBLE" in norm and "CL" in norm:
            col_map["eligible_cl"] = col
        elif "ELIGIBLE" in norm and "SL" in norm:
            col_map["eligible_sl"] = col
        elif "TAKEN" in norm and "CL" in norm:
            col_map["taken_cl"] = col
        elif "TAKEN" in norm and "SL" in norm:
            col_map["taken_sl"] = col
        elif "BALANCE" in norm and "CL" in norm:
            col_map["balance_cl"] = col
        elif "BALANCE" in norm and "SL" in norm:
            col_map["balance_sl"] = col
        elif "COMPOFF" in norm or "BALANCECO" in norm or norm == "CO":
            col_map["balance_co"] = col

    # Positional fallback if multiple columns have similar headers
    # Standard format: CL, SL under Eligible; CL, SL under Taken; CL, SL under Balance
    remaining_cols = [c for c in target_df.columns if c not in col_map.values()]

    records = []
    for _, row in target_df.iterrows():
        unique_id = str(row.get(col_map.get("unique_id", ""), "")).strip()
        ecn = str(row.get(col_map.get("ecn", ""), "")).strip()

        if unique_id in ["nan", "None", "-", ""]:
            unique_id = ""
        if ecn in ["nan", "None", "-", ""]:
            ecn = ""

        # Ignore empty or header echo
        if not unique_id and not ecn:
            continue
        if unique_id.upper() in ["UNIQUE CODE", "UNIQUE ID", "TOTAL", "SR. NO."]:
            continue

        name = str(row.get(col_map.get("name", ""), "")).strip()
        if name in ["nan", "None", "-", ""]: name = ""

        bm_id = str(row.get(col_map.get("bm_id", ""), "")).strip()
        if bm_id in ["nan", "None", "-", ""]: bm_id = None

        location = str(row.get(col_map.get("location", ""), "MUMBAI")).strip()
        if location in ["nan", "None", "-", ""]: location = "MUMBAI"

        doj = parse_date_safely(row.get(col_map.get("doj", "")))
        eod = parse_date_safely(row.get(col_map.get("eod", "")))

        e_cl = parse_float_safely(row.get(col_map.get("eligible_cl", "")), 0.0)
        e_sl = parse_float_safely(row.get(col_map.get("eligible_sl", "")), 0.0)
        t_cl = parse_float_safely(row.get(col_map.get("taken_cl", "")), 0.0)
        t_sl = parse_float_safely(row.get(col_map.get("taken_sl", "")), 0.0)
        b_cl = parse_float_safely(row.get(col_map.get("balance_cl", "")), max(0.0, e_cl - t_cl))
        b_sl = parse_float_safely(row.get(col_map.get("balance_sl", "")), max(0.0, e_sl - t_sl))
        b_co = parse_float_safely(row.get(col_map.get("balance_co", "")), 0.0)

        records.append({
            "unique_id": unique_id,
            "ecn": ecn,
            "name": name,
            "bm_id": bm_id,
            "location": location,
            "doj": doj,
            "eod": eod,
            "eligible_cl": e_cl,
            "eligible_sl": e_sl,
            "taken_cl": t_cl,
            "taken_sl": t_sl,
            "balance_cl": b_cl,
            "balance_sl": b_sl,
            "balance_co": b_co
        })

    return records

def import_leave_statement_file(file_bytes: bytes, filename: str, db: Session, month_year: str = "Oct-26") -> Dict[str, Any]:
    """
    Imports and synchronizes Monthly Leave Statement (PDF, Excel, or CSV).
    Binds by UNIQUE CODE or ECN.
    Updates User balances and provisions missing employee profiles.
    Records history in leave_balances table.
    """
    fn_lower = filename.lower()
    if fn_lower.endswith('.pdf'):
        records = parse_leave_statement_pdf(file_bytes)
    elif fn_lower.endswith(('.xlsx', '.xls', '.csv')):
        records = parse_leave_statement_tabular(file_bytes, filename)
    else:
        raise ValueError(f"Unsupported file format: {filename}. Please upload .pdf, .xlsx, or .csv")

    if not records:
        raise ValueError("No valid employee leave ledger records could be extracted from the file.")

    from auth import get_password_hash
    default_hashed_pwd = get_password_hash("Welcome@123")

    updated_users = 0
    created_users = 0
    ledger_entries_created = 0

    for rec in records:
        unique_id = rec.get("unique_id", "").strip()
        ecn = rec.get("ecn", "").strip()
        name = rec.get("name", "").strip()
        bm_id = rec.get("bm_id")
        location = rec.get("location", "MUMBAI") or "MUMBAI"
        doj = rec.get("doj")
        eod = rec.get("eod")

        e_cl = rec.get("eligible_cl", 0.0)
        e_sl = rec.get("eligible_sl", 0.0)
        t_cl = rec.get("taken_cl", 0.0)
        t_sl = rec.get("taken_sl", 0.0)
        b_cl = rec.get("balance_cl", 0.0)
        b_sl = rec.get("balance_sl", 0.0)
        b_co = rec.get("balance_co", 0.0)

        # Match user by unique_id or ecn
        user = None
        if unique_id:
            user = db.query(models.User).filter(models.User.unique_id == unique_id).first()
        if not user and ecn:
            user = db.query(models.User).filter(models.User.ecn == ecn).first()

        if user:
            # Update user profile details
            if ecn and not user.ecn:
                user.ecn = ecn
            if bm_id and not user.bm_id:
                user.bm_id = bm_id
            if doj:
                user.doj = doj
            if eod:
                user.eod = eod
            if location and (not user.location or user.location == "Mumbai"):
                user.location = location

            # Sync active balances and quotas
            user.eligible_cl = e_cl
            user.eligible_sl = e_sl
            user.taken_cl = t_cl
            user.taken_sl = t_sl
            user.balance_cl = b_cl
            user.balance_sl = b_sl
            user.balance_co = b_co

            # Keep legacy balance fields in sync
            user.cl_balance = b_cl
            user.sl_balance = b_sl
            user.co_balance = b_co

            updated_users += 1
        else:
            # Provision missing employee profile
            gen_uid = unique_id if unique_id else (ecn if ecn else f"EMP{int(datetime.utcnow().timestamp())}")
            clean_email_tag = re.sub(r'[^a-zA-Z0-9]', '', gen_uid).lower()
            emp_email = f"{clean_email_tag}@msedcl.com"

            # Check if email is already taken
            existing_email = db.query(models.User).filter(models.User.email == emp_email).first()
            if existing_email:
                emp_email = f"{clean_email_tag}_{int(datetime.utcnow().timestamp()) % 10000}@msedcl.com"

            user = models.User(
                unique_id=gen_uid,
                ecn=ecn if ecn else None,
                bm_id=bm_id if bm_id else None,
                name=name if name else gen_uid,
                email=emp_email,
                role_title="QA Auditor",
                access_level="Employee",
                department="Operations",
                location=location,
                gender="Not Specified",
                hashed_password=default_hashed_pwd,
                is_active=True,
                doj=doj,
                eod=eod,
                eligible_cl=e_cl,
                eligible_sl=e_sl,
                taken_cl=t_cl,
                taken_sl=t_sl,
                balance_cl=b_cl,
                balance_sl=b_sl,
                balance_co=b_co,
                cl_balance=b_cl,
                sl_balance=b_sl,
                co_balance=b_co
            )
            db.add(user)
            db.flush() # Ensure user.id is generated
            created_users += 1

        # Save snapshot to LeaveBalance ledger
        ledger_entry = models.LeaveBalance(
            user_id=user.id,
            unique_id=user.unique_id,
            ecn=user.ecn,
            bm_id=user.bm_id,
            name=user.name,
            location=user.location,
            doj=user.doj,
            eod=user.eod,
            month_year=month_year,
            eligible_cl=e_cl,
            eligible_sl=e_sl,
            taken_cl=t_cl,
            taken_sl=t_sl,
            balance_cl=b_cl,
            balance_sl=b_sl,
            balance_co=b_co
        )
        db.add(ledger_entry)
        ledger_entries_created += 1

    db.commit()

    return {
        "total_records": len(records),
        "updated_users": updated_users,
        "created_users": created_users,
        "ledger_entries_created": ledger_entries_created
    }

def export_leave_master_excel(users: List[models.User], statement_title: str = "Official Leave Master Statement - Oct 2026") -> BytesIO:
    """
    Exports full Leave Master table to styled Excel (.xlsx) file matching company specifications
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leave Master"
    ws.views.sheetView[0].showGridLines = True

    # Styling definitions
    title_font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
    meta_font = Font(name="Calibri", size=10, italic=True, color="475569")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    cell_font = Font(name="Calibri", size=10, color="0F172A")
    bold_cell_font = Font(name="Calibri", size=10, bold=True, color="0F172A")
    balance_font = Font(name="Calibri", size=10, bold=True, color="1E40AF")

    header_dark = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_cl = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_sl = PatternFill(start_color="DC2626", end_color="DC2626", fill_type="solid")
    header_co = PatternFill(start_color="D97706", end_color="D97706", fill_type="solid")

    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    highlight_cl_fill = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
    highlight_sl_fill = PatternFill(start_color="FEF2F2", end_color="FEF2F2", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # Title Block
    ws.cell(row=1, column=1, value=statement_title).font = title_font
    ws.cell(row=2, column=1, value=f"Generated on: {datetime.utcnow().strftime('%d %b %Y %H:%M UTC')} | MSEDCL Quality Audit & Operations").font = meta_font

    headers = [
        ("Sr.", header_dark),
        ("UNIQUE CODE", header_dark),
        ("ECN", header_dark),
        ("DATE OF JOINING", header_dark),
        ("EMPLOYEE NAME", header_dark),
        ("BIOMETRIC ID", header_dark),
        ("LOCATION", header_dark),
        ("EOD", header_dark),
        ("Eligible Leaves (CL)", header_cl),
        ("Eligible Leaves (SL)", header_sl),
        ("Total Taken (CL)", header_cl),
        ("Total Taken (SL)", header_sl),
        ("Balance Leaves (CL)", header_cl),
        ("Balance Leaves (SL)", header_sl),
        ("Comp-Off Balance", header_co),
    ]

    header_row = 4
    for col_idx, (h_name, fill_style) in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=h_name)
        cell.font = header_font
        cell.fill = fill_style
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    ws.row_dimensions[header_row].height = 28

    current_row = 5
    for idx, u in enumerate(users, start=1):
        row_fill = zebra_fill if idx % 2 == 0 else None

        values = [
            idx,
            u.unique_id or "",
            u.ecn or "-",
            u.doj.strftime("%d-%m-%Y") if u.doj else "-",
            u.name or "",
            u.bm_id or "-",
            u.location or "MUMBAI",
            u.eod.strftime("%d-%m-%Y") if u.eod else "-",
            round(float(u.eligible_cl or 0.0), 2),
            round(float(u.eligible_sl or 0.0), 2),
            round(float(u.taken_cl or 0.0), 2),
            round(float(u.taken_sl or 0.0), 2),
            round(float(u.balance_cl if u.balance_cl is not None else u.cl_balance or 0.0), 2),
            round(float(u.balance_sl if u.balance_sl is not None else u.sl_balance or 0.0), 2),
            round(float(u.balance_co if u.balance_co is not None else u.co_balance or 0.0), 2),
        ]

        for col_idx, val in enumerate(values, start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = cell_font
            cell.border = thin_border

            if col_idx in [1, 2, 3, 6, 7, 8]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in [9, 10, 11, 12, 13, 14, 15]:
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

            # Highlighting balance columns
            if col_idx == 13:
                cell.fill = highlight_cl_fill
                cell.font = balance_font
            elif col_idx == 14:
                cell.fill = highlight_sl_fill
                cell.font = balance_font
            elif row_fill:
                cell.fill = row_fill

        ws.row_dimensions[current_row].height = 20
        current_row += 1

    # Set column widths
    col_widths = {
        1: 6,   # Sr.
        2: 15,  # UNIQUE CODE
        3: 14,  # ECN
        4: 16,  # DATE OF JOINING
        5: 28,  # EMPLOYEE NAME
        6: 15,  # BIOMETRIC ID
        7: 14,  # LOCATION
        8: 15,  # EOD
        9: 18,  # Eligible CL
        10: 18, # Eligible SL
        11: 18, # Taken CL
        12: 18, # Taken SL
        13: 20, # Balance CL
        14: 20, # Balance SL
        15: 18  # Comp-Off
    }
    for col_idx, width in col_widths.items():
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output

def calculate_daily_capacity(
    dates: List[date],
    role_filter: Optional[str],
    db: Session,
    eligible_leave_quota: Optional[float] = None,
    leave_cap_percentage: float = 15.0,
    location_filter: Optional[str] = "All"
) -> Dict[str, Any]:
    """
    Feature 1: Daily Leave Quota & Mandays Capacity Tracker (Enhanced Dynamic Engine)
    Accurately computes across each date:
      - Active Headcount (users active on that date, excluding offboarded users where exit_date <= target_date)
      - Week Off (WO) count
      - Present Scheduled (P, P+HD, Shift windows)
      - Absent (A) count
      - Total Leave (Approved Leaves + CL / SL / PL / Leave)
      - Live In Office (WorkSession status in ['ACTIVE', 'ON_BREAK'])
      - Net Available Working Mandays: Active Headcount - Total Leave - WO - Absent
      - Eligible Leave Quota: round(Active Headcount * (leave_cap_percentage / 100))
      - Pending Leave Slots: Eligible Leave Quota - Total Leave
      - Visual Status: 'available' (Green), 'full' (Amber), 'shortage' (Red alert)
    """
    # 1. Base query for users
    query = db.query(models.User)

    if location_filter and location_filter not in ["All", "ALL", ""]:
        query = query.filter(models.User.location.ilike(f"%{location_filter.strip()}%"))

    if role_filter and role_filter != "All":
        r_clean = role_filter.strip().upper()
        if r_clean == "TL":
            # Match Team Lead / ATL roles
            query = query.filter(
                (models.User.role_title.ilike("%TL%")) |
                (models.User.role_title.ilike("%Team Lead%")) |
                (models.User.role_title.ilike("%Floor Sup%"))
            )
        elif r_clean == "ADMIN":
            query = query.filter(
                (models.User.access_level == "Admin") |
                (models.User.role_title.ilike("%Admin%")) |
                (models.User.role_title.ilike("%Operations Lead%"))
            )
        elif r_clean == "MANAGER":
            query = query.filter(
                (models.User.access_level.in_(["Manager", "Admin"])) |
                (models.User.role_title.ilike("%Manager%")) |
                (models.User.role_title.ilike("%Lead%"))
            )
        elif r_clean in ["ALL STAFF", "AGENTS", "ALL STAFF / AGENTS", "AGENT"]:
            query = query.filter(
                (models.User.access_level == "Employee") |
                (models.User.role_title.ilike("%Agent%")) |
                (models.User.role_title.ilike("%QA%")) |
                (models.User.role_title.ilike("%Auditor%")) |
                (models.User.role_title.ilike("%CSA%")) |
                (models.User.role_title.ilike("%MIS%")) |
                (models.User.role_title.ilike("%CCE%")) |
                (models.User.role_title.ilike("%TR%"))
            )
        else:
            query = query.filter(models.User.role_title == role_filter)
    else:
        # Default All view excludes non-operational System Administrator
        query = query.filter(models.User.unique_id != "ADMIN001")

    all_filtered_users = query.all()
    user_ids = [u.id for u in all_filtered_users]

    if not dates:
        return {"days": [], "summary": {}}

    start_d = min(dates)
    end_d = max(dates)

    # Fetch all approved leaves for these users intersecting this date range
    approved_leaves = []
    if user_ids:
        approved_leaves = db.query(models.LeaveRequest).filter(
            models.LeaveRequest.user_id.in_(user_ids),
            models.LeaveRequest.status == "Approved",
            models.LeaveRequest.start_date <= end_d,
            models.LeaveRequest.end_date >= start_d
        ).all()

    # Pre-index approved leaves by date from LeaveRequest table
    leaves_by_date = {d: 0.0 for d in dates}
    user_leave_dates = set() # (user_id, date) to prevent double counting

    for lv in approved_leaves:
        emp = lv.user
        emp_exit = emp.exit_date if emp else None

        c_d = max(lv.start_date, start_d)
        e_d = min(lv.end_date, end_d)
        while c_d <= e_d:
            if c_d in leaves_by_date:
                if not (emp_exit and c_d >= emp_exit):
                    leave_weight = 0.5 if (getattr(lv, 'duration_days', 1.0) == 0.5 or getattr(lv, 'day_part', '') in ['half_first', 'half_second']) else 1.0
                    leaves_by_date[c_d] += leave_weight
                    user_leave_dates.add((lv.user_id, c_d))
            c_d += timedelta(days=1)

    # Fetch roster entries and work sessions in bulk
    roster_entries = []
    work_sessions = []
    if user_ids:
        roster_entries = db.query(models.RosterEntry).filter(
            models.RosterEntry.user_id.in_(user_ids),
            models.RosterEntry.date >= start_d,
            models.RosterEntry.date <= end_d
        ).all()

        work_sessions = db.query(models.WorkSession).filter(
            models.WorkSession.user_id.in_(user_ids),
            models.WorkSession.session_date >= start_d,
            models.WorkSession.session_date <= end_d
        ).all()

    # Organize entries by date: {date: {user_id: entry}}
    re_map_by_date = {d: {} for d in dates}
    for re in roster_entries:
        if re.date in re_map_by_date:
            re_map_by_date[re.date][re.user_id] = re

    # Organize sessions by date: {date: {user_id: session}}
    ws_map_by_date = {d: {} for d in dates}
    for ws in work_sessions:
        if ws.session_date in ws_map_by_date:
            ws_map_by_date[ws.session_date][ws.user_id] = ws

    daily_results = []
    today = date.today()

    for d in dates:
        active_users_today = [
            u for u in all_filtered_users
            if (u.is_active or (u.exit_date and d < u.exit_date)) and
               not (u.exit_date and d >= u.exit_date)
        ]
        headcount = len(active_users_today)

        # Count shifts, attendance statuses, WOs, Absents, live in-office counts, and shift slots
        wo_count = 0.0
        absent_count = 0.0
        scheduled_present_count = 0.0
        in_office_live_count = 0
        punched_completed_count = 0
        day_leave = leaves_by_date.get(d, 0.0)

        # Shift Slots Capacity Distribution Tracking
        slots_count = {
            "07:00-16:00": 0,
            "09:00-18:00": 0,
            "16:00-01:00": 0,
            "18:00-03:00": 0,
            "22:00-07:00": 0,
            "other": 0
        }

        for u in active_users_today:
            re = re_map_by_date[d].get(u.id)
            ws = ws_map_by_date[d].get(u.id)

            # Check live punch status
            if ws:
                if ws.status in ["ACTIVE", "ON_BREAK"]:
                    in_office_live_count += 1
                elif ws.status == "COMPLETED":
                    punched_completed_count += 1

            # Check roster shift code and status
            val = str(re.shift_code_or_time or "").strip().upper() if re else ""
            status_val = str(re.status or "").strip().upper() if re else ""

            # Check if user has approved leave first
            if (u.id, d) in user_leave_dates:
                pass # Already counted in day_leave
            elif val in ["CL", "SL", "PL", "LEAVE"] or status_val == "LEAVE":
                day_leave += 1.0
                user_leave_dates.add((u.id, d))
            elif val in ["HD", "HALF-DAY", "HALF DAY", "P+HD"] or status_val in ["HALF-DAY", "HD"]:
                day_leave += 0.5
                scheduled_present_count += 0.5
                user_leave_dates.add((u.id, d))
            elif val == "WO" or status_val == "WO":
                wo_count += 1.0
            elif val == "CO" or status_val == "CO":
                wo_count += 1.0
            elif val in ["A", "ABSENT"] or status_val == "ABSENT":
                absent_count += 1.0
            elif val in ["P", "PRESENT", "S"] or any(t in val for t in [":", "07:00", "09:00", "11:00", "13:00", "16:00", "18:00", "20:00", "22:00"]):
                scheduled_present_count += 1.0
            elif status_val == "PRESENT":
                scheduled_present_count += 1.0
            else:
                # Default if not scheduled: if day is in past/today and not punched/rostered, count as non-working
                scheduled_present_count += 1.0

            # Slot categorization
            if "07:00" in val:
                slots_count["07:00-16:00"] += 1
            elif "09:00" in val:
                slots_count["09:00-18:00"] += 1
            elif "16:00" in val:
                slots_count["16:00-01:00"] += 1
            elif "18:00" in val:
                slots_count["18:00-03:00"] += 1
            elif "22:00" in val:
                slots_count["22:00-07:00"] += 1
            elif val not in ["WO", "CO", "A", "ABSENT", "CL", "SL", "PL", "LEAVE", "HD", "-", ""]:
                slots_count["other"] += 1

        # Dynamic Mandays: Actual available operational capacity on that date
        mandays = max(0.0, float(headcount) - (day_leave + wo_count + absent_count))

        # Eligible Leave Quota: based on configured company leave cap %
        if eligible_leave_quota is not None and eligible_leave_quota > 0:
            day_quota = float(eligible_leave_quota)
        else:
            computed = round(headcount * (leave_cap_percentage / 100.0), 1)
            day_quota = max(1.0, computed) if headcount > 0 else 0.0

        # Pending Leave Slots = Quota - Total Leaves taken
        pending = float(day_quota) - day_leave

        if pending > 0:
            status = "available" # Green
            badge_class = "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 border-emerald-300"
            badge_label = f"+{pending:g} Available"
        elif pending == 0:
            status = "full" # Amber
            badge_class = "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 border-amber-300"
            badge_label = "Fully Booked (0)"
        else:
            status = "shortage" # Red alert
            badge_class = "bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300 border-rose-300 animate-pulse"
            badge_label = f"Shortage ({pending:g})"

        daily_results.append({
            "date": d,
            "date_str": d.strftime("%Y-%m-%d"),
            "day_name": d.strftime("%a"),
            "formatted_date": d.strftime("%d %b"),
            "active_headcount": headcount,
            "eligible_leave": day_quota,
            "total_leave": round(day_leave, 2),
            "week_off_count": int(wo_count),
            "absent_count": int(absent_count),
            "scheduled_present": int(scheduled_present_count),
            "in_office_live": in_office_live_count,
            "punched_completed": punched_completed_count,
            "mandays": round(mandays, 2),
            "pending": round(pending, 2),
            "status": status,
            "badge_class": badge_class,
            "badge_label": badge_label,
            "slots": slots_count
        })

    # Summary aggregations
    avg_headcount = round(sum(r["active_headcount"] for r in daily_results) / len(daily_results), 1) if daily_results else 0
    total_leaves_taken = round(sum(r["total_leave"] for r in daily_results), 2)
    total_wo_period = sum(r["week_off_count"] for r in daily_results)
    total_absent_period = sum(r["absent_count"] for r in daily_results)
    total_mandays = round(sum(r["mandays"] for r in daily_results), 2)
    shortage_days = sum(1 for r in daily_results if r["status"] == "shortage")

    return {
        "days": daily_results,
        "summary": {
            "avg_headcount": avg_headcount,
            "total_leaves_period": total_leaves_taken,
            "total_wo_period": total_wo_period,
            "total_absent_period": total_absent_period,
            "total_mandays": total_mandays,
            "shortage_days_count": shortage_days,
            "quota_per_day": eligible_leave_quota
        }
    }

def offboard_employee(
    user_id: int,
    exit_date_val: date,
    reason: str,
    db: Session,
    actor_name: str = "Admin"
) -> Dict[str, Any]:
    """
    Feature 2: Roster Employee Removal / Offboarding (Soft Delete)
      - Sets is_active = False with exit_date and exit_reason
      - Starting from exit_date onward, automatically cancels all pending or approved leaves
      - Updates roster slots from exit_date onward to 'Left'
      - Sends an audit notification
    """
    if isinstance(exit_date_val, str):
        try:
            exit_date_val = datetime.strptime(exit_date_val.strip(), "%Y-%m-%d").date()
        except Exception:
            exit_date_val = date.today()

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise ValueError("Employee not found.")

    user.is_active = False
    user.exit_date = exit_date_val
    user.exit_reason = (reason or "").strip()

    # Cancel pending or approved leaves starting on or after exit_date
    cancelled_leaves_count = 0
    leaves_to_cancel = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.user_id == user.id,
        models.LeaveRequest.status.in_(["Pending", "Approved"]),
        models.LeaveRequest.end_date >= exit_date_val
    ).all()

    for lv in leaves_to_cancel:
        lv.status = "Cancelled"
        lv.reviewer_comment = f"Automatically cancelled due to employee offboarding (Exit: {exit_date_val.strftime('%d-%m-%Y')})"
        lv.reviewed_by = actor_name
        lv.reviewed_at = datetime.utcnow()
        cancelled_leaves_count += 1

    # Update future roster entries on or after exit_date to status 'Left'
    updated_roster_count = 0
    future_roster = db.query(models.RosterEntry).filter(
        models.RosterEntry.user_id == user.id,
        models.RosterEntry.date >= exit_date_val
    ).all()

    for re_entry in future_roster:
        re_entry.shift_code_or_time = "Left"
        re_entry.status = "Left"
        re_entry.updated_by = f"Offboarding ({actor_name})"
        updated_roster_count += 1

    # Create administrative notification
    notif = models.Notification(
        user_id=user.id,
        title="Employee Offboarding Processed",
        message=f"Profile deactivated with exit date {exit_date_val.strftime('%d %b %Y')}. Reason: {reason}",
        category="general"
    )
    db.add(notif)
    db.commit()

    return {
        "user_id": user.id,
        "name": user.name,
        "unique_id": user.unique_id,
        "exit_date": exit_date_val.strftime("%Y-%m-%d"),
        "cancelled_leaves": cancelled_leaves_count,
        "updated_roster_entries": updated_roster_count
    }


def export_monthly_payroll_muster(month_date: date, location_filter: Optional[str], db: Session) -> BytesIO:
    """
    Feature 7: Enterprise Monthly Muster Roll & Payroll Statement Exporter (.xlsx)
    Calculates for each employee across the target month:
      - Total Calendar Days
      - Present Full Days (P)
      - Half-Days (HD * 0.5)
      - Approved Paid Leaves (CL + SL + PL + Leave)
      - Paid Week Offs (WO)
      - Paid Compensatory Offs (CO)
      - Unplanned Absences / LOP (A)
      - Overtime (OT) Hours
      - Net Total Payable Mandays (Present + Half-Days + Paid Leaves + WO + CO)
    """
    import calendar
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    year = month_date.year
    month = month_date.month
    num_days = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, num_days)
    month_dates = [date(year, month, d) for d in range(1, num_days + 1)]

    wb = openpyxl.Workbook()
    ws = wb.active
    month_name_str = month_start.strftime("%B %Y")
    ws.title = f"Payroll {month_start.strftime('%b %Y')}"
    ws.views.sheetView[0].showGridLines = True

    # Styling Palette
    navy_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    indigo_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    payable_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid") # Emerald 100
    lop_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid") # Rose 100
    stripe_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    title_font = Font(name="Segoe UI", size=14, bold=True, color="FFFFFF")
    sub_font = Font(name="Segoe UI", size=10, italic=True, color="94A3B8")
    header_font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    bold_font = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
    cell_font = Font(name="Segoe UI", size=9, color="334155")
    payable_font = Font(name="Segoe UI", size=10, bold=True, color="166534")
    lop_font = Font(name="Segoe UI", size=10, bold=True, color="991B1B")

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1")
    )

    # 1. Company Banner Header
    ws.merge_cells("A1:N1")
    t_cell = ws["A1"]
    t_cell.value = f"MSEDCL Workforce Operations — Monthly Muster Roll & Payroll Statement ({month_name_str})"
    t_cell.font = title_font
    t_cell.fill = navy_fill
    t_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 36

    ws.merge_cells("A2:N2")
    s_cell = ws["A2"]
    s_cell.value = f"Generated on {date.today().strftime('%d %B %Y')} | Location: {location_filter or 'All Operational Circles'} | Total Calendar Days: {num_days}"
    s_cell.font = sub_font
    s_cell.fill = navy_fill
    s_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[2].height = 20

    # 2. Table Headers
    headers = [
        "SR NO.", "EMPLOYEE NAME", "UNIQUE ID", "BM ID", "DESIGNATION", "LOCATION",
        "PRESENT (P)", "HALF-DAY (HD)", "WEEK OFF (WO)", "COMP-OFF (CO)",
        "PAID LEAVES", "ABSENT / LOP", "OT HOURS", "TOTAL PAYABLE MANDAYS"
    ]
    ws.row_dimensions[3].height = 26
    for col_idx, h_text in enumerate(headers, start=1):
        c = ws.cell(row=3, column=col_idx, value=h_text)
        c.font = header_font
        c.fill = header_fill if col_idx <= 6 else (indigo_fill if col_idx < 14 else payable_fill)
        if col_idx == 14:
            c.font = payable_font
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = thin_border

    # 3. Query Employees
    u_query = db.query(models.User).filter(
        ((models.User.is_active == True) | (models.User.exit_date >= month_start)),
        models.User.unique_id != "ADMIN001"
    )
    if location_filter and location_filter != "All":
        u_query = u_query.filter(models.User.location.ilike(f"%{location_filter}%"))

    users = u_query.order_by(models.User.name.asc()).all()
    user_ids = [u.id for u in users]

    # Pre-fetch Roster Entries & WorkSessions
    all_entries = db.query(models.RosterEntry).filter(
        models.RosterEntry.user_id.in_(user_ids),
        models.RosterEntry.date >= month_start,
        models.RosterEntry.date <= month_end
    ).all() if user_ids else []
    entry_map = {(e.user_id, e.date): e for e in all_entries}

    all_sessions = db.query(models.WorkSession).filter(
        models.WorkSession.user_id.in_(user_ids),
        models.WorkSession.session_date >= month_start,
        models.WorkSession.session_date <= month_end
    ).all() if user_ids else []
    session_map = {(s.user_id, s.session_date): s for s in all_sessions}

    all_leaves = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.user_id.in_(user_ids),
        models.LeaveRequest.status == "Approved",
        models.LeaveRequest.start_date <= month_end,
        models.LeaveRequest.end_date >= month_start
    ).all() if user_ids else []

    curr_row = 4
    for idx, u in enumerate(users, start=1):
        row_fill = stripe_fill if idx % 2 == 0 else None
        p_count = 0.0
        hd_count = 0.0
        wo_count = 0.0
        co_count = 0.0
        leave_count = 0.0
        absent_count = 0.0
        ot_minutes = 0

        # Leave dates set
        u_leaves = {d for lv in all_leaves if lv.user_id == u.id for d in month_dates if lv.start_date <= d <= lv.end_date}

        for d in month_dates:
            # Check exit date
            if u.exit_date and d >= u.exit_date:
                continue

            entry = entry_map.get((u.id, d))
            sess = session_map.get((u.id, d))

            if sess and sess.net_work_mins > 480: # Standard 8h = 480m
                ot_minutes += (sess.net_work_mins - 480)

            if d in u_leaves:
                leave_count += 1.0
                continue

            val = str(entry.shift_code_or_time or "").strip().upper() if entry else ""
            status_val = str(entry.status or "").strip().upper() if entry else ""

            if val in ["WO", "WEEK OFF"] or status_val == "WO":
                wo_count += 1.0
            elif val in ["CO", "COMP-OFF", "COMP OFF"] or status_val == "CO":
                co_count += 1.0
            elif val in ["CL", "SL", "PL", "LEAVE"] or status_val == "LEAVE":
                leave_count += 1.0
            elif val in ["HD", "HALF-DAY", "HALF DAY", "P+HD"] or status_val in ["HALF-DAY", "HD"]:
                hd_count += 1.0
            elif val in ["A", "ABSENT"] or status_val == "ABSENT":
                absent_count += 1.0
            elif val in ["P", "PRESENT", "S"] or any(ch in val for ch in [":", "07:00", "09:00", "16:00", "18:00", "22:00"]):
                p_count += 1.0
            elif sess and sess.status in ["ACTIVE", "COMPLETED"]:
                p_count += 1.0
            else:
                # Default present if rostered
                p_count += 1.0

        # Total Payable Mandays = Present + (HD * 0.5) + WO + CO + Paid Leaves
        total_payable = p_count + (hd_count * 0.5) + wo_count + co_count + leave_count
        ot_hours = round(ot_minutes / 60.0, 1)

        row_vals = [
            idx,
            u.name,
            u.unique_id,
            u.bm_id or "-",
            u.role_title or u.access_level,
            u.location or "Nagpur",
            int(p_count),
            int(hd_count),
            int(wo_count),
            int(co_count),
            int(leave_count),
            int(absent_count),
            ot_hours,
            round(total_payable, 1)
        ]

        ws.row_dimensions[curr_row].height = 20
        for col_idx, r_val in enumerate(row_vals, start=1):
            c = ws.cell(row=curr_row, column=col_idx, value=r_val)
            c.border = thin_border
            if row_fill and col_idx < 14:
                c.fill = row_fill

            if col_idx in [1, 3, 4, 7, 8, 9, 10, 11, 12, 13]:
                c.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx == 2:
                c.alignment = Alignment(horizontal="left", vertical="center")
            else:
                c.alignment = Alignment(horizontal="center", vertical="center")

            if col_idx == 12 and r_val > 0:
                c.fill = lop_fill
                c.font = lop_font
            elif col_idx == 14:
                c.fill = payable_fill
                c.font = payable_font
                c.alignment = Alignment(horizontal="center", vertical="center")
            else:
                c.font = cell_font

        curr_row += 1

    # Column dimensions auto-fit
    widths = [8, 28, 16, 12, 18, 15, 14, 14, 14, 14, 14, 14, 12, 22]
    for i, w in enumerate(widths, start=1):
        col_letter = get_column_letter(i)
        ws.column_dimensions[col_letter].width = w

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
