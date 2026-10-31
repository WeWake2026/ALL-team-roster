from datetime import date
from database import SessionLocal, engine, Base
import models
from auth import get_password_hash

def clear_and_init_clean_db():
    """Wipe mock data and initialize only necessary foundation models (Standard Shifts & initial Super Admin)."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("Clearing all demo data and initializing clean production state...")

        # 1. Standard Shift Templates
        shifts = [
            models.Shift(name="Morning Shift", code="07:00 To 16:00", start_time="07:00", end_time="16:00", color_code="teal"),
            models.Shift(name="General Shift", code="09:00 To 18:00", start_time="09:00", end_time="18:00", color_code="indigo"),
            models.Shift(name="Afternoon Shift", code="13:00 To 22:00", start_time="13:00", end_time="22:00", color_code="amber"),
            models.Shift(name="Night Shift", code="22:00 To 07:00", start_time="22:00", end_time="07:00", color_code="purple"),
        ]
        for s in shifts:
            db.add(s)

        # 2. Single Clean Super Admin
        admin_pw = get_password_hash("Admin@123")
        admin_user = models.User(
            unique_id="ADMIN001",
            crm_id=None,
            bm_id=None,
            ecn=None,
            name="System Administrator",
            email="admin@msedcl.com",
            role_title="Operations Lead",
            access_level="Admin",
            department="Operations",
            location="Headquarters",
            gender="Not Specified",
            hashed_password=admin_pw,
            pl_balance=24.0,
            cl_balance=12.0,
            sl_balance=10.0,
            co_balance=0.0,
            unpaid_taken=0.0
        )
        db.add(admin_user)
        db.commit()
        print("Clean state initialized successfully. All demo employees, rosters, leaves, and notifications removed.")
    except Exception as e:
        db.rollback()
        print(f"Error resetting database: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    clear_and_init_clean_db()
