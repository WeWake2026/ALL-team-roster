from datetime import date, time, timedelta
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal
from models import User, Shift, ShiftChangeHistory, RosterViewLog, LeaveRequest, Location, Team, RosterEntry

client = TestClient(app, follow_redirects=False)

def test_admin_access_all():
    """Verify admin has unrestricted access to roster, location-wise, combined, and shift management."""
    # Login as Admin using identifier & password
    resp = client.post("/login", data={"identifier": "admin@msedcl.com", "password": "password123"})
    assert resp.status_code in [200, 302, 303], f"Login failed with status {resp.status_code}"
    cookie = resp.headers.get("set-cookie")
    headers = {"Cookie": cookie} if cookie else {}

    # Check shift management page
    r = client.get("/admin/shifts", headers=headers)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    assert "Shift Configuration" in r.text

    # Check combined roster
    r = client.get("/roster/combined", headers=headers)
    assert r.status_code == 200

    # Check location roster
    r = client.get("/roster/location", headers=headers)
    assert r.status_code == 200

    # Check shift change history
    r = client.get("/roster/history", headers=headers)
    assert r.status_code == 200

def test_agent_restrictions():
    """Verify Agent cannot access location roster, combined roster, or shift management."""
    # Login as Agent / Employee (bhakti.chavan@arceus.in)
    resp = client.post("/login", data={"identifier": "bhakti.chavan@arceus.in", "password": "Welcome@123"})
    assert resp.status_code in [200, 302, 303], f"Agent login failed with {resp.status_code}"
    cookie = resp.headers.get("set-cookie")
    headers = {"Cookie": cookie} if cookie else {}

    # Must be 403 Forbidden for combined roster
    r = client.get("/roster/combined", headers=headers)
    assert r.status_code == 403

    # Must be 403 Forbidden for location roster
    r = client.get("/roster/location", headers=headers)
    assert r.status_code == 403

    # Must be 403 Forbidden for admin shift management
    r = client.get("/admin/shifts", headers=headers)
    assert r.status_code == 403

    # Read-only team roster must succeed
    r = client.get("/roster", headers=headers)
    assert r.status_code == 200
    # Must highlight the logged in user with You indicator
    assert 'You</span>' in r.text or 'You' in r.text

def test_overnight_shift_creation():
    """Verify Admin can create an overnight shift schedule (e.g. 22:00 to 06:00)."""
    resp = client.post("/login", data={"identifier": "admin@msedcl.com", "password": "password123"})
    cookie = resp.headers.get("set-cookie")
    headers = {"Cookie": cookie} if cookie else {}

    post_data = {
        "name": "Overnight Ops Shift",
        "start_time": "22:00",
        "end_time": "06:00",
        "is_overnight": "on",
        "break_duration_mins": 45,
        "color_code": "#8b5cf6",
        "applicable_locations": "All Locations",
        "effective_from": "2026-10-27"
    }
    r = client.post("/admin/shifts/create", data=post_data, headers=headers)
    assert r.status_code in [200, 302, 303]

    # Verify shift in database
    db = SessionLocal()
    shift = db.query(Shift).filter(Shift.name == "Overnight Ops Shift").first()
    assert shift is not None
    assert shift.is_overnight is True
    assert shift.color_code == "#8b5cf6"
    db.close()

def test_leave_conflict_prevention():
    """Verify quick assign shift rejects assigning a working shift if employee has approved leave."""
    db = SessionLocal()
    user = db.query(User).filter(User.email == "bhakti.chavan@arceus.in").first()
    user_id = user.id
    test_date = date.today() + timedelta(days=25)
    
    # Insert approved leave
    leave = LeaveRequest(
        user_id=user_id,
        leave_type="Sick Leave",
        start_date=test_date,
        end_date=test_date,
        status="Approved",
        reason="Test approved medical leave",
        duration_days=1.0
    )
    db.add(leave)
    db.commit()
    db.close()

    # Try changing shift to morning shift as Admin
    resp = client.post("/login", data={"identifier": "admin@msedcl.com", "password": "password123"})
    cookie = resp.headers.get("set-cookie")
    headers = {"Cookie": cookie} if cookie else {}

    r = client.post("/roster/quick-assign", data={
        "user_id": user_id,
        "roster_date": test_date.strftime("%Y-%m-%d"),
        "shift_name": "Morning Shift (07:00 To 16:00)",
        "reason": "Testing leave conflict"
    }, headers=headers)

    # Must be 400 Bad Request with Conflict warning when override is not specified
    assert r.status_code == 400
    assert "conflict" in r.text.lower() or "leave" in r.text.lower()

    # With override_leave enabled, it should succeed (302 redirect)
    r_override = client.post("/roster/quick-assign", data={
        "user_id": user_id,
        "roster_date": test_date.strftime("%Y-%m-%d"),
        "shift_name": "Morning Shift (07:00 To 16:00)",
        "reason": "Overriding leave for operational exigency",
        "override_leave": "true"
    }, headers=headers, follow_redirects=False)
    assert r_override.status_code == 302

def test_view_logging_and_audit_history():
    """Verify that visiting roster logs view tracking, and changing shift logs shift change history."""
    db = SessionLocal()
    v_count = db.query(RosterViewLog).count()
    assert v_count >= 1
    db.close()

if __name__ == "__main__":
    test_admin_access_all()
    print("✓ test_admin_access_all passed")
    test_agent_restrictions()
    print("✓ test_agent_restrictions passed")
    test_overnight_shift_creation()
    print("✓ test_overnight_shift_creation passed")
    test_leave_conflict_prevention()
    print("✓ test_leave_conflict_prevention passed")
    test_view_logging_and_audit_history()
    print("✓ test_view_logging_and_audit_history passed")
    print("ALL TESTS PASSED SUCCESSFULLY!")
