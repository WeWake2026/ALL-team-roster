from datetime import date, datetime, timedelta
from database import SessionLocal, engine, Base
import models
from auth import get_password_hash

def init_db_and_seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Check if users already seeded
        if db.query(models.User).count() > 0:
            print("Database already contains data.")
            return

        print("Seeding initial database...")
        default_pw = get_password_hash("password123")

        # 1. Shifts
        shifts = [
            models.Shift(name="Morning Shift", code="07:00 To 16:00", start_time="07:00", end_time="16:00", color_code="teal"),
            models.Shift(name="General Shift", code="09:00 To 18:00", start_time="09:00", end_time="18:00", color_code="indigo"),
            models.Shift(name="Afternoon Shift", code="13:00 To 22:00", start_time="13:00", end_time="22:00", color_code="amber"),
            models.Shift(name="Night Shift", code="22:00 To 07:00", start_time="22:00", end_time="07:00", color_code="purple"),
        ]
        for s in shifts:
            db.add(s)

        # 2. Holidays
        today = date.today()
        holidays = [
            models.Holiday(name="Maharashtra Day", date=date(today.year, 5, 1)),
            models.Holiday(name="Independence Day", date=date(today.year, 8, 15)),
            models.Holiday(name="Ganesh Chaturthi", date=date(today.year, 9, 7)),
            models.Holiday(name="Diwali Laxmi Pujan", date=date(today.year, 11, 1)),
            models.Holiday(name="Republic Day", date=date(today.year, 1, 26)),
        ]
        for h in holidays:
            db.add(h)

        # 3. Users (Admins, Managers, Employees)
        users = [
            models.User(
                unique_id="ADMIN001",
                crm_id="CRM-9001",
                bm_id="BM-101",
                ecn="ECN-4401",
                name="Sanjay Sharma",
                email="admin@msedcl.com",
                role_title="Operations Lead",
                access_level="Admin",
                department="Operations & Quality",
                location="Bandra, Mumbai",
                gender="Male",
                hashed_password=default_pw,
                pl_balance=24.0, cl_balance=12.0, sl_balance=10.0, co_balance=4.0
            ),
            models.User(
                unique_id="MGR002",
                crm_id="CRM-9002",
                bm_id="BM-102",
                ecn="ECN-4402",
                name="Pooja Deshmukh",
                email="pooja.deshmukh@msedcl.com",
                role_title="Team Lead",
                access_level="Manager",
                department="Operations",
                location="Pune Central",
                gender="Female",
                hashed_password=default_pw,
                pl_balance=20.0, cl_balance=10.0, sl_balance=8.0, co_balance=3.0
            ),
            models.User(
                unique_id="AIPLCC221",
                crm_id="CRM-8021",
                bm_id="BM-221",
                ecn="ECN-5001",
                name="Rahul Kadam",
                email="rahul.kadam@msedcl.com",
                role_title="Senior QA Auditor",
                access_level="Employee",
                department="Quality Audit",
                location="Vashi, Navi Mumbai",
                gender="Male",
                hashed_password=default_pw,
                pl_balance=16.0, cl_balance=8.0, sl_balance=7.0, co_balance=2.0
            ),
            models.User(
                unique_id="AIPLCC222",
                crm_id="CRM-8022",
                bm_id="BM-222",
                ecn="ECN-5002",
                name="Priya Sawant",
                email="priya.sawant@msedcl.com",
                role_title="QA Auditor",
                access_level="Employee",
                department="Quality Audit",
                location="Thane",
                gender="Female",
                hashed_password=default_pw,
                pl_balance=18.0, cl_balance=9.0, sl_balance=8.0, co_balance=1.0
            ),
            models.User(
                unique_id="AIPLCC223",
                crm_id="CRM-8023",
                bm_id="BM-223",
                ecn="ECN-5003",
                name="Amit Shinde",
                email="amit.shinde@msedcl.com",
                role_title="Operations Agent",
                access_level="Employee",
                department="Consumer Support",
                location="Kalyan",
                gender="Male",
                hashed_password=default_pw,
                pl_balance=14.0, cl_balance=6.0, sl_balance=5.0, co_balance=0.0
            ),
            models.User(
                unique_id="AIPLCC224",
                crm_id="CRM-8024",
                bm_id="BM-224",
                ecn="ECN-5004",
                name="Sneha Patil",
                email="sneha.patil@msedcl.com",
                role_title="Operations Agent",
                access_level="Employee",
                department="Consumer Support",
                location="Bandra, Mumbai",
                gender="Female",
                hashed_password=default_pw,
                pl_balance=17.5, cl_balance=9.0, sl_balance=8.0, co_balance=2.0
            ),
            models.User(
                unique_id="AIPLCC225",
                crm_id="CRM-8025",
                bm_id="BM-225",
                ecn="ECN-5005",
                name="Vikram Jadhav",
                email="vikram.jadhav@msedcl.com",
                role_title="Technical Support Specialist",
                access_level="Employee",
                department="Technical Desk",
                location="Pune Central",
                gender="Male",
                hashed_password=default_pw,
                pl_balance=15.0, cl_balance=7.0, sl_balance=6.0, co_balance=1.0
            ),
            models.User(
                unique_id="AIPLCC226",
                crm_id="CRM-8026",
                bm_id="BM-226",
                ecn="ECN-5006",
                name="Anjali More",
                email="anjali.more@msedcl.com",
                role_title="QA Auditor",
                access_level="Employee",
                department="Quality Audit",
                location="Vashi, Navi Mumbai",
                gender="Female",
                hashed_password=default_pw,
                pl_balance=19.0, cl_balance=10.0, sl_balance=8.0, co_balance=2.0
            ),
        ]
        for u in users:
            db.add(u)
        db.flush()

        # 4. Generate Roster for 14 days around today
        # Week starts from Monday
        start_monday = today - timedelta(days=today.weekday())
        
        shift_patterns = [
            ["07:00 To 16:00", "07:00 To 16:00", "07:00 To 16:00", "07:00 To 16:00", "07:00 To 16:00", "WO", "WO"],
            ["09:00 To 18:00", "09:00 To 18:00", "09:00 To 18:00", "09:00 To 18:00", "09:00 To 18:00", "WO", "WO"],
            ["13:00 To 22:00", "13:00 To 22:00", "13:00 To 22:00", "13:00 To 22:00", "13:00 To 22:00", "WO", "WO"],
            ["22:00 To 07:00", "22:00 To 07:00", "22:00 To 07:00", "22:00 To 07:00", "WO", "WO", "CO"],
            ["09:00 To 18:00", "09:00 To 18:00", "Leave", "09:00 To 18:00", "09:00 To 18:00", "WO", "WO"],
            ["07:00 To 16:00", "07:00 To 16:00", "07:00 To 16:00", "07:00 To 16:00", "07:00 To 16:00", "WO", "CO"],
            ["13:00 To 22:00", "13:00 To 22:00", "13:00 To 22:00", "WO", "WO", "13:00 To 22:00", "13:00 To 22:00"],
            ["09:00 To 18:00", "09:00 To 18:00", "09:00 To 18:00", "09:00 To 18:00", "09:00 To 18:00", "WO", "WO"],
        ]

        for u_idx, u in enumerate(users):
            pattern = shift_patterns[u_idx % len(shift_patterns)]
            for day_offset in range(14): # 2 weeks
                entry_date = start_monday + timedelta(days=day_offset)
                shift_val = pattern[day_offset % 7]
                status = "Scheduled"
                if shift_val == "WO": status = "WO"
                elif shift_val == "CO": status = "CO"
                elif shift_val == "Leave": status = "Leave"

                roster_entry = models.RosterEntry(
                    user_id=u.id,
                    date=entry_date,
                    shift_code_or_time=shift_val,
                    status=status,
                    updated_by="System Initializer"
                )
                db.add(roster_entry)

        # 5. Leave Requests
        sample_leaves = [
            models.LeaveRequest(
                user_id=users[2].id, # Rahul
                leave_type="PL",
                start_date=start_monday + timedelta(days=2),
                end_date=start_monday + timedelta(days=2),
                duration_days=1.0,
                reason="Personal work regarding document verification at Sub-division office",
                status="Approved",
                reviewer_comment="Approved. Handover tasks to Priya Sawant.",
                reviewed_by="Sanjay Sharma",
                reviewed_at=datetime.utcnow()
            ),
            models.LeaveRequest(
                user_id=users[3].id, # Priya
                leave_type="CL",
                start_date=today + timedelta(days=3),
                end_date=today + timedelta(days=4),
                duration_days=2.0,
                reason="Family gathering and festival celebration in hometown",
                status="Pending"
            ),
            models.LeaveRequest(
                user_id=users[4].id, # Amit
                leave_type="SL",
                start_date=today + timedelta(days=1),
                end_date=today + timedelta(days=1),
                duration_days=1.0,
                reason="High fever and doctor-advised rest",
                status="Pending"
            ),
            models.LeaveRequest(
                user_id=users[5].id, # Sneha
                leave_type="Comp-Off",
                start_date=today + timedelta(days=5),
                end_date=today + timedelta(days=5),
                duration_days=1.0,
                reason="Availing compensatory off for working during Sunday sub-station audit",
                status="Pending"
            )
        ]
        for lr in sample_leaves:
            db.add(lr)

        # 6. Notifications
        notifications = [
            models.Notification(
                user_id=users[2].id,
                title="Leave Request Approved",
                message="Your Paid Leave for 1 day has been approved by Sanjay Sharma.",
                category="leave_status"
            ),
            models.Notification(
                user_id=users[3].id,
                title="Upcoming Shift Notification",
                message="You are scheduled for General Shift (09:00 To 18:00) today.",
                category="shift_change"
            ),
            models.Notification(
                user_id=users[0].id,
                title="New Leave Submissions",
                message="3 pending leave requests are awaiting your review in the Approval Queue.",
                category="leave_status"
            )
        ]
        for n in notifications:
            db.add(n)

        db.commit()
        print("Database initialized & seeded successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    init_db_and_seed()
