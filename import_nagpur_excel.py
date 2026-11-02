import openpyxl
from datetime import datetime, date
from database import SessionLocal
import models
from auth import get_password_hash

EXCEL_PATH = "data/nagpur_roster_media.xlsx"

def run_nagpur_import():
    db = SessionLocal()
    try:
        # 1. Location
        nagpur_loc = db.query(models.Location).filter(models.Location.name.ilike("%nagpur%")).first()
        if not nagpur_loc:
            nagpur_loc = models.Location(name="Nagpur", code="NGP", is_active=True)
            db.add(nagpur_loc)
            db.commit()
            db.refresh(nagpur_loc)

        nagpur_loc_id = nagpur_loc.id
        print(f"Using Nagpur Location ID: {nagpur_loc_id}")

        default_hashed_pwd = get_password_hash("Welcome@123")
        wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)

        target_dates = [
            date(2026, 11, 1),
            date(2026, 11, 2),
            date(2026, 11, 3),
            date(2026, 11, 4),
            date(2026, 11, 5),
            date(2026, 11, 6),
            date(2026, 11, 7),
            date(2026, 11, 8),
        ]
        col_indices = [16, 22, 24, 26, 28, 30, 32, 34] # 1-based in openpyxl

        active_imported = 0
        roster_entries_count = 0

        # Import Active Roster
        ws_act = wb["November Week 2026"]
        for r in range(3, ws_act.max_row + 1):
            val_no = ws_act.cell(r, 1).value
            if not val_no or not str(val_no).strip().isdigit():
                continue

            emp_no = int(str(val_no).strip())
            doj_val = ws_act.cell(r, 2).value
            name = str(ws_act.cell(r, 4).value or "").strip()
            unique_id = str(ws_act.cell(r, 5).value or "").strip()
            bm_id = str(ws_act.cell(r, 6).value or "").strip()
            emp_id = str(ws_act.cell(r, 7).value or "").strip()
            mail_id = str(ws_act.cell(r, 8).value or "").strip().lower()
            designation = str(ws_act.cell(r, 9).value or "CCE").strip()
            gender = str(ws_act.cell(r, 10).value or "MALE").strip().upper()
            status_val = str(ws_act.cell(r, 11).value or "Active").strip()
            location = str(ws_act.cell(r, 14).value or "Nagpur").strip()
            default_shift = str(ws_act.cell(r, 15).value or "07:00 To 16:00").strip()

            if not name:
                continue

            if not unique_id or unique_id == "-":
                unique_id = f"NGP_{emp_no:03d}"
            if not mail_id or mail_id == "-":
                mail_id = f"ngp.{emp_no:03d}.{name.lower().replace(' ', '.')[:15]}@arceus.in"

            clean_doj = None
            if isinstance(doj_val, datetime):
                clean_doj = doj_val.date()
            elif isinstance(doj_val, date):
                clean_doj = doj_val
            elif doj_val and str(doj_val).strip() != "-":
                try:
                    clean_doj = datetime.strptime(str(doj_val).strip()[:10], "%Y-%m-%d").date()
                except Exception:
                    pass

            role_title = designation
            desig_up = designation.upper()
            if "ADMIN" in desig_up:
                access_level = "Admin"
            elif "SME" in desig_up:
                access_level = "SME"
            elif "QUALITY" in desig_up or "QA" in desig_up:
                access_level = "Quality"
            elif "TL" in desig_up or "LEAD" in desig_up:
                access_level = "Team Leader"
            else:
                access_level = "Employee"

            existing_user = db.query(models.User).filter(
                (models.User.unique_id == unique_id) | (models.User.email == mail_id)
            ).first()

            if not existing_user:
                target_user = models.User(
                    name=name,
                    unique_id=unique_id,
                    email=mail_id,
                    crm_id=emp_id if emp_id != "-" else None,
                    bm_id=bm_id if bm_id != "-" else None,
                    ecn=emp_id if emp_id != "-" else None,
                    role_title=role_title,
                    access_level=access_level,
                    department="Operations",
                    location="Nagpur",
                    location_id=nagpur_loc_id,
                    gender=gender if gender in ["MALE", "FEMALE"] else "MALE",
                    is_active=True,
                    doj=clean_doj,
                    hashed_password=default_hashed_pwd,
                    eligible_cl=12.0,
                    eligible_sl=8.0,
                    balance_cl=12.0,
                    balance_sl=8.0,
                    balance_co=0.0
                )
                db.add(target_user)
                db.flush()
                active_imported += 1
            else:
                target_user = existing_user
                target_user.name = name
                target_user.location = "Nagpur"
                target_user.location_id = nagpur_loc_id
                target_user.role_title = role_title
                target_user.access_level = access_level
                target_user.is_active = True
                if clean_doj:
                    target_user.doj = clean_doj

            # Roster entries
            for d_idx, c_idx in enumerate(col_indices):
                raw_cell = ws_act.cell(r, c_idx).value
                cell_val = str(raw_cell or "").strip()
                t_date = target_dates[d_idx]

                raw_val = cell_val if cell_val else default_shift
                u_val = raw_val.upper()

                if u_val in ["WO", "WEEK OFF"]:
                    shift_code = "WO"
                    entry_status = "WO"
                elif u_val in ["CO", "COMP-OFF", "COMP OFF"]:
                    shift_code = "CO"
                    entry_status = "CO"
                elif u_val in ["A", "ABSENT"]:
                    shift_code = "A"
                    entry_status = "Absent"
                elif u_val in ["P+HD", "HD", "HALF-DAY", "HALF DAY"]:
                    shift_code = "HD"
                    entry_status = "Half-Day"
                elif u_val in ["CL", "SL", "LEAVE"]:
                    shift_code = u_val
                    entry_status = "Leave"
                elif u_val in ["P", "PRESENT"]:
                    shift_code = default_shift
                    entry_status = "Present"
                elif any(ch in raw_val for ch in [":", "07:00", "09:00", "16:00", "18:00", "22:00"]):
                    shift_code = raw_val
                    entry_status = "Scheduled"
                else:
                    shift_code = default_shift
                    entry_status = "Scheduled"

                existing_re = db.query(models.RosterEntry).filter(
                    models.RosterEntry.user_id == target_user.id,
                    models.RosterEntry.date == t_date
                ).first()

                if existing_re:
                    existing_re.shift_code_or_time = shift_code
                    existing_re.status = entry_status
                    existing_re.location_id = nagpur_loc_id
                else:
                    new_re = models.RosterEntry(
                        user_id=target_user.id,
                        location_id=nagpur_loc_id,
                        date=t_date,
                        shift_code_or_time=shift_code,
                        status=entry_status,
                        approval_status="Approved",
                        updated_by="Nagpur Roster Import"
                    )
                    db.add(new_re)
                    roster_entries_count += 1

        db.commit()
        print(f"Active roster committed! Users: {active_imported}, Roster rows: {roster_entries_count}")

        # 3. Import Inactive Sheet
        inactive_imported = 0
        ws_inact = wb["Inactive"]
        for r in range(2, ws_inact.max_row + 1):
            name = str(ws_inact.cell(r, 4).value or "").strip()
            if not name or name.upper() in ["EMPLOYEE NAME", "NAME"]:
                continue

            doj_raw = ws_inact.cell(r, 2).value
            lwd_raw = ws_inact.cell(r, 3).value
            unique_id = str(ws_inact.cell(r, 5).value or "").strip()
            bm_id = str(ws_inact.cell(r, 6).value or "").strip()
            emp_id = str(ws_inact.cell(r, 7).value or "").strip()
            mail_id = str(ws_inact.cell(r, 8).value or "").strip().lower()
            designation = str(ws_inact.cell(r, 9).value or "CCE").strip()
            gender = str(ws_inact.cell(r, 10).value or "MALE").strip().upper()

            # Ensure unique id and unique email for inactive historical records
            if not unique_id or unique_id == "-":
                unique_id = f"OFF_{r:04d}"
            if not mail_id or mail_id == "-":
                mail_id = f"off.{r:04d}.{name.lower().replace(' ', '.')[:15]}@arceus.in"

            clean_doj = None
            if isinstance(doj_raw, datetime):
                clean_doj = doj_raw.date()
            elif isinstance(doj_raw, date):
                clean_doj = doj_raw

            clean_lwd = None
            if isinstance(lwd_raw, datetime):
                clean_lwd = lwd_raw.date()
            elif isinstance(lwd_raw, date):
                clean_lwd = lwd_raw

            existing_inact = db.query(models.User).filter(
                (models.User.unique_id == unique_id) | (models.User.email == mail_id)
            ).first()

            if not existing_inact:
                inact_user = models.User(
                    name=name,
                    unique_id=unique_id,
                    email=mail_id,
                    crm_id=emp_id if emp_id != "-" else None,
                    bm_id=bm_id if bm_id != "-" else None,
                    ecn=emp_id if emp_id != "-" else None,
                    role_title=designation,
                    access_level="Employee",
                    department="Operations",
                    location="Nagpur",
                    location_id=nagpur_loc_id,
                    gender=gender if gender in ["MALE", "FEMALE"] else "MALE",
                    is_active=False,
                    doj=clean_doj,
                    exit_date=clean_lwd,
                    exit_reason="Offboarded / Historical Record",
                    hashed_password=default_hashed_pwd
                )
                db.add(inact_user)
                try:
                    db.flush()
                    inactive_imported += 1
                except Exception as ex_flush:
                    db.rollback()
                    # Make email guaranteed unique with row index
                    mail_id = f"off.row{r}.{unique_id.lower()}@arceus.in"
                    inact_user.email = mail_id
                    db.add(inact_user)
                    db.flush()
                    inactive_imported += 1
            else:
                existing_inact.is_active = False
                existing_inact.exit_date = clean_lwd
                existing_inact.location = "Nagpur"
                existing_inact.location_id = nagpur_loc_id

        db.commit()
        print("=== Nagpur Excel Import Completed Successfully! ===")
        print(f"Active Employees: {active_imported}")
        print(f"Inactive / Offboarded Records: {inactive_imported}")
        print(f"Roster Entries Created: {roster_entries_count}")

    except Exception as e:
        db.rollback()
        print(f"Import Failed: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    run_nagpur_import()
