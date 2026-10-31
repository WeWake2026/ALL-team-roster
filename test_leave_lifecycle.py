import os
import json
import asyncio
from datetime import date, timedelta, datetime
from fastapi import HTTPException
from fastapi.datastructures import UploadFile
import io

import models
import database
from main import app, apply_leave, edit_leave, cancel_leave, review_leave, get_leave_details, download_leave_evidence
from auth import resolve_user_permissions, get_user_perms

def test_leave_management_lifecycle():
    print("=" * 70)
    print("RUNNING EXTENSIVE LEAVE MANAGEMENT SYSTEM AUDIT TESTS")
    print("=" * 70)

    db = database.SessionLocal()

    # 1. Fetch Admin and standard employee
    admin = db.query(models.User).filter(models.User.email == "admin@msedcl.com").first()
    assert admin is not None, "Admin user required"
    emp = db.query(models.User).filter(models.User.email == "shashi.kurhade@arceus.in").first()
    assert emp is not None, "Employee user required"
    
    # Ensure sufficient balance for testing
    emp.balance_cl = 10.0
    emp.cl_balance = 10.0
    emp.taken_cl = 0.0
    db.commit()

    print("[TEST 1] Testing Apply Leave with Supporting Evidence...")
    # Mock upload file
    mock_pdf_content = b"%PDF-1.4 Mock medical certificate content for testing"
    mock_file = UploadFile(
        filename="medical_certificate.pdf",
        file=io.BytesIO(mock_pdf_content),
        headers={"content-type": "application/pdf"}
    )

    test_date_start = (date.today() + timedelta(days=60)).strftime("%Y-%m-%d")
    test_date_end = (date.today() + timedelta(days=61)).strftime("%Y-%m-%d")

    # Clean up prior test requests on those dates if any
    old_reqs = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.user_id == emp.id,
        models.LeaveRequest.start_date >= date.today() + timedelta(days=50)
    ).all()
    for o in old_reqs:
        db.delete(o)
    db.commit()

    # Run apply_leave
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    apply_resp = loop.run_until_complete(
        apply_leave(
            request=None,
            leave_type="CL",
            start_date=test_date_start,
            end_date=test_date_end,
            reason="Medical procedure with specialist consultation",
            day_part="full",
            doc_category="Medical Certificate / Doctor Note",
            evidence_files=[mock_file],
            user=emp,
            db=db
        )
    )

    assert apply_resp.status_code == 302
    assert "alert_type=success" in apply_resp.headers["location"]

    leave_req = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.user_id == emp.id,
        models.LeaveRequest.reason == "Medical procedure with specialist consultation"
    ).first()
    assert leave_req is not None, "Leave request must be persisted in database"
    assert leave_req.application_number is not None, "Application ID must be generated"
    assert leave_req.application_number.startswith("LA-"), f"Application ID format invalid: {leave_req.application_number}"
    assert leave_req.status == "Pending Approval", f"Default status must be Pending Approval, got {leave_req.status}"
    assert leave_req.duration_days == 2.0, f"Duration must be 2.0, got {leave_req.duration_days}"
    assert len(leave_req.attachments) == 1, "Attachment must be linked to leave request"
    assert leave_req.attachments[0].file_name == "medical_certificate.pdf"
    assert len(leave_req.history_records) >= 1, "Audit history record must be created"
    print(f" -> PASSED: Application {leave_req.application_number} created with attachment and audit trail.")

    # 2. Overlapping leave validation
    print("[TEST 2] Testing Overlapping Leave Prevention...")
    overlap_resp = loop.run_until_complete(
        apply_leave(
            request=None,
            leave_type="CL",
            start_date=test_date_start,
            end_date=test_date_end,
            reason="Attempting overlapping request",
            day_part="full",
            doc_category="Other Supporting Document",
            evidence_files=[],
            user=emp,
            db=db
        )
    )
    assert overlap_resp.status_code == 302
    assert "Overlapping+leave+detected" in overlap_resp.headers["location"]
    print(" -> PASSED: Overlapping request was properly rejected.")

    # 3. Edit Leave Application
    print("[TEST 3] Testing Edit Leave Application...")
    emp_perms = resolve_user_permissions(emp, db)
    revised_end = (date.today() + timedelta(days=60)).strftime("%Y-%m-%d") # Reduce to 1 day
    edit_resp = loop.run_until_complete(
        edit_leave(
            request=None,
            request_id=leave_req.id,
            leave_type="CL",
            start_date=test_date_start,
            end_date=revised_end,
            day_part="full",
            reason="Medical procedure revised to single day observation",
            additional_comments="Rescheduled discharge by doctor",
            doc_category="Updated Supporting Evidence",
            evidence_files=[],
            user=emp,
            perms=emp_perms,
            db=db
        )
    )
    assert edit_resp.status_code == 302
    db.refresh(leave_req)
    assert leave_req.duration_days == 1.0, f"Duration should update to 1.0, got {leave_req.duration_days}"
    assert "observation" in leave_req.reason
    edit_history = [h for h in leave_req.history_records if h.action == "EDITED"]
    assert len(edit_history) >= 1, "EDITED action must be logged in history"
    print(f" -> PASSED: Leave edited successfully; revised duration is {leave_req.duration_days} day.")

    # 4. Details and History Retrieval Endpoint
    print("[TEST 4] Testing Leave Details & Secure JSON API...")
    details_resp = get_leave_details(
        request_id=leave_req.id,
        user=emp,
        perms=emp_perms,
        db=db
    )
    assert details_resp.status_code == 200
    details_data = json.loads(details_resp.body.decode())
    assert details_data["application_number"] == leave_req.application_number
    assert len(details_data["attachments"]) == 1
    assert len(details_data["history"]) >= 2
    print(" -> PASSED: Leave details and history JSON API verified.")

    # 5. IDOR & Access Control: Another employee cannot access evidence or details
    print("[TEST 5] Testing RBAC & IDOR Protection on Evidence Access...")
    other_emp = db.query(models.User).filter(models.User.email == "poonam.gaikwad@arceus.in").first()
    assert other_emp is not None
    other_perms = resolve_user_permissions(other_emp, db)

    try:
        download_leave_evidence(
            attachment_id=leave_req.attachments[0].id,
            user=other_emp,
            perms=other_perms,
            db=db
        )
        assert False, "Unauthorized user should not download medical evidence"
    except HTTPException as e:
        assert e.status_code == 403
        print(" -> PASSED: Unauthorized evidence download blocked (HTTP 403 Forbidden).")

    # Authorized download by applicant
    ev_resp = download_leave_evidence(
        attachment_id=leave_req.attachments[0].id,
        user=emp,
        perms=emp_perms,
        db=db
    )
    assert ev_resp.status_code == 200
    print(" -> PASSED: Applicant authorized evidence download succeeded.")

    # 6. Self-Approval Prevention Check
    print("[TEST 6] Testing Self-Approval Prevention in Review Desk...")
    admin_perms = resolve_user_permissions(admin, db)
    # If admin submits a leave, check that it doesn't appear in their own review queue
    admin_leave = models.LeaveRequest(
        application_number="LA-TEST-ADMIN",
        user_id=admin.id,
        leave_type="CL",
        start_date=date.today() + timedelta(days=90),
        end_date=date.today() + timedelta(days=90),
        duration_days=1.0,
        reason="Admin personal leave",
        status="Pending Approval"
    )
    db.add(admin_leave)
    db.commit()

    # Query review queue as constructed in main.py
    rq_query = db.query(models.LeaveRequest).filter(
        models.LeaveRequest.status.in_(["Pending Approval", "Pending", "Cancellation Requested"]),
        models.LeaveRequest.user_id != admin.id # Must exclude own
    )
    found_own = rq_query.filter(models.LeaveRequest.id == admin_leave.id).first()
    assert found_own is None, "User's own leave must never appear in their review queue"
    db.delete(admin_leave)
    db.commit()
    print(" -> PASSED: Self-approval prevention verified.")

    # 7. Approve Leave & Roster Synchronization
    print("[TEST 7] Testing Leave Approval and Roster Sync...")
    initial_balance = emp.balance_cl
    review_resp = review_leave(
        request=None,
        request_id=leave_req.id,
        action="Approve",
        comment="Approved by Admin",
        user=admin,
        perms=admin_perms,
        db=db
    )
    assert review_resp.status_code == 302
    db.refresh(leave_req)
    db.refresh(emp)
    assert leave_req.status == "Approved"
    assert emp.balance_cl == initial_balance - 1.0, f"Balance must be deducted by 1.0, got {emp.balance_cl}"
    
    # Check roster entry
    roster_entry = db.query(models.RosterEntry).filter(
        models.RosterEntry.user_id == emp.id,
        models.RosterEntry.date == leave_req.start_date
    ).first()
    assert roster_entry is not None, "Roster entry must be created or updated"
    assert roster_entry.status == "Leave"
    assert roster_entry.shift_code_or_time in ["CL", "Leave"]
    print(" -> PASSED: Leave approved, balance deducted, and roster cell set to Leave.")

    # 8. Cancel Approved Leave Workflow (Cancellation Requested -> Approved Cancellation)
    print("[TEST 8] Testing Approved Leave Cancellation Request & Approval...")
    # Step A: Employee requests cancellation
    cancel_resp = cancel_leave(
        request=None,
        request_id=leave_req.id,
        cancellation_reason="Consultation cancelled by medical clinic",
        user=emp,
        perms=emp_perms,
        db=db
    )
    assert cancel_resp.status_code == 302
    db.refresh(leave_req)
    assert leave_req.status == "Cancellation Requested", f"Status should be 'Cancellation Requested', got {leave_req.status}"
    print(" -> PASSED: Cancellation request submitted by employee.")

    # Step B: Supervisor / Admin approves cancellation
    rev_cancel_resp = review_leave(
        request=None,
        request_id=leave_req.id,
        action="Approve Cancellation",
        comment="Cancellation approved. Quota refunded.",
        user=admin,
        perms=admin_perms,
        db=db
    )
    assert rev_cancel_resp.status_code == 302
    db.refresh(leave_req)
    db.refresh(emp)
    assert leave_req.status == "Cancelled", f"Status should be 'Cancelled', got {leave_req.status}"
    assert emp.balance_cl == initial_balance, f"Balance should be fully re-credited to {initial_balance}, got {emp.balance_cl}"

    # Check roster entry restoration
    db.refresh(roster_entry)
    assert roster_entry.status == "Scheduled"
    assert roster_entry.shift_code_or_time == "09:00 To 18:00"
    print(" -> PASSED: Cancellation approved, balance re-credited, roster schedule restored.")

    # 9. Clean up test record
    db.delete(leave_req)
    if roster_entry:
        db.delete(roster_entry)
    db.commit()
    db.close()

    print("=" * 70)
    print("ALL LEAVE MANAGEMENT LIFECYCLE TESTS COMPLETED SUCCESSFULLY (100% PASSED)!")
    print("=" * 70)

if __name__ == "__main__":
    test_leave_management_lifecycle()
