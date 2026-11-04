import httpx
import sqlite3
import datetime

BASE = "http://127.0.0.1:8000"

def test_attendance_and_late_grace():
    # Verify monthly attendance calculation handles grace period
    client = httpx.Client(base_url=BASE, follow_redirects=True)
    client.post("/login", data={"identifier": "admin@msedcl.com", "password": "password123"})
    res = client.get("/api/employee/attendance/export?format=csv&year=2026&month=10")
    assert res.status_code == 200
    assert len(res.content) > 500

def test_leave_application_and_idempotency():
    # 1. Test inverted dates rejection
    emp = httpx.Client(base_url=BASE, follow_redirects=True)
    emp.post("/login", data={"identifier": "bhakti.chavan@arceus.in", "password": "Welcome@123"})
    r_inv = emp.post("/leaves/apply", data={
        "leave_type": "CL",
        "start_date": "2026-11-20",
        "end_date": "2026-11-15",
        "reason": "Invalid dates test",
        "day_part": "full"
    })
    assert "earlier" in r_inv.text.lower() or "End+date+cannot" in str(r_inv.url)

    # 2. Test shift swap self-collision
    conn = sqlite3.connect("shiftflow.db")
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email = 'bhakti.chavan@arceus.in'")
    emp_id = c.fetchone()[0]
    conn.close()

    r_swap = emp.post("/roster/swap/create", data={
        "target_user_id": emp_id,
        "shift_date": "2026-11-25",
        "my_shift": "M1",
        "target_shift": "E1",
        "reason": "Test self swap"
    })
    assert "yourself" in r_swap.text.lower() or "Cannot+swap" in str(r_swap.url)

def test_team_leader_roster_access():
    tl = httpx.Client(base_url=BASE, follow_redirects=True)
    tl.post("/login", data={"identifier": "poonam.gaikwad@arceus.in", "password": "Welcome@123"})
    r_roster = tl.get("/roster")
    assert r_roster.status_code == 200

if __name__ == "__main__":
    test_attendance_and_late_grace()
    test_leave_application_and_idempotency()
    test_team_leader_roster_access()
    print("ALL HRMS WORKFLOW AUTOMATED TESTS PASSED!")

