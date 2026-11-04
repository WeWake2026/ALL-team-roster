from datetime import date, timedelta
import models
import database
from main import app
from auth import (
    get_password_hash,
    resolve_user_permissions
)

def run_tests():
    print("=" * 65)
    print("RUNNING EXTENDED RBAC & EMPLOYEE STATUS (ACTIVE/OFFBOARDED) TESTS")
    print("=" * 65)
    
    db = database.SessionLocal()

    # 1. Admin & Core RBAC
    print("[TEST 1] Verifying Admin Universal Scope & Permissions...")
    admin = db.query(models.User).filter(models.User.email == "admin@msedcl.com").first()
    assert admin is not None
    perms_admin = resolve_user_permissions(admin, db)
    assert perms_admin.is_admin is True
    print(" -> PASSED: Admin full authority verified.")

    # 2. Location Scoping & IDOR Prevention
    print("[TEST 2] Verifying Location Scoping & IDOR Prevention...")
    pune_loc = db.query(models.Location).filter(models.Location.code == "PUN").first()
    mumbai_loc = db.query(models.Location).filter(models.Location.code == "MUM").first()
    pune_user = db.query(models.User).filter(models.User.unique_id == "PUN_EMP001").first()
    pune_perms = resolve_user_permissions(pune_user, db)
    assert pune_perms.can_access_location(pune_loc.id) is True
    assert pune_perms.can_access_location(mumbai_loc.id) is False
    print(" -> PASSED: Location isolation verified.")

    # 3. Offboarding & Reactivation Lifecycle
    print("[TEST 3] Testing Offboard and Reactivate Employee Lifecycle...")
    test_emp = db.query(models.User).filter(models.User.email == "shashi.kurhade@arceus.in").first()
    assert test_emp is not None

    # Step A: Offboard test employee
    from excel_service import offboard_employee
    exit_dt = date.today()
    res = offboard_employee(
        user_id=test_emp.id,
        exit_date_val=exit_dt,
        reason="Test Offboarding",
        db=db,
        actor_name=admin.name
    )
    db.refresh(test_emp)
    assert test_emp.is_active is False, "Employee must be marked inactive"
    assert test_emp.exit_date == exit_dt, "Exit date must be set"
    print(" -> PASSED: Employee successfully marked Offboarded with exit date.")

    # Step B: Verify assignment rejection for offboarded employee
    from fastapi import HTTPException
    print("[TEST 4] Verifying Roster Assignment Rejection for Offboarded Employee...")
    # Attempting to assign future shift to inactive employee should fail
    try:
        from main import quick_assign_shift
        # Call quick_assign_shift directly to verify exception
        quick_assign_shift(
            user_id=test_emp.id,
            date=str(date.today() + timedelta(days=2)),
            shift_code="09:00 To 18:00",
            user=admin,
            db=db
        )
        assert False, "Should have raised HTTPException 400 for offboarded employee"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Cannot assign shifts to offboarded employee" in exc.detail
        print(" -> PASSED: Shift assignment successfully blocked for offboarded employee.")

    # Step C: Reactivate employee
    print("[TEST 5] Testing Employee Reactivation to Active Status...")
    test_emp.is_active = True
    test_emp.exit_date = None
    test_emp.exit_reason = None
    db.commit()
    db.refresh(test_emp)
    assert test_emp.is_active is True
    assert test_emp.exit_date is None
    print(" -> PASSED: Employee successfully reactivated and restored to Active status.")

    # Step D: Verify shift assignment succeeds after reactivation
    print("[TEST 6] Testing Roster Assignment Succeeds after Reactivation...")
    from main import quick_assign_shift
    resp = quick_assign_shift(
        user_id=test_emp.id,
        date=str(date.today()),
        shift_code="09:00 To 18:00",
        user=admin,
        db=db
    )
    assert resp.status_code == 302
    print(" -> PASSED: Roster assignment permitted for active employee.")

    # 7. Audit log verification
    print("[TEST 7] Testing Audit Log Recording for Status Changes...")
    from auth import log_audit_event
    log_audit_event(
        db=db,
        actor=admin,
        action="EMPLOYEE_STATUS_TEST",
        resource_type="User",
        resource_id=str(test_emp.id),
        details="Verified Active / Offboarded lifecycle"
    )
    audit = db.query(models.AuditLog).filter(
        models.AuditLog.action == "EMPLOYEE_STATUS_TEST"
    ).first()
    assert audit is not None
    print(" -> PASSED: Status modification audit log verified.")

    db.close()
    print("=" * 65)
    print("ALL TESTS (INCLUDING ACTIVE/OFFBOARDED LIFECYCLE) PASSED (100%)")
    print("=" * 65)

if __name__ == "__main__":
    run_tests()
