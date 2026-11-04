import httpx
import io
import openpyxl

BASE = "http://127.0.0.1:8000"

def test_export_formats_and_data_isolation():
    admin = httpx.Client(base_url=BASE, follow_redirects=True)
    admin.post("/login", data={"identifier": "admin@msedcl.com", "password": "password123"})
    
    # 1. Admin Excel export integrity
    r_xlsx = admin.get("/roster/export?start_date=2026-10-01&end_date=2026-10-31")
    assert r_xlsx.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r_xlsx.content))
    assert wb.active.max_row > 10

    # 2. Employee personal PDF export integrity
    emp = httpx.Client(base_url=BASE, follow_redirects=True)
    emp.post("/login", data={"identifier": "bhakti.chavan@arceus.in", "password": "Welcome@123"})
    r_pdf = emp.get("/api/employee/attendance/export?format=pdf&year=2026&month=10")
    assert r_pdf.status_code == 200
    assert r_pdf.content.startswith(b"%PDF-")

    # 3. Employee personal CSV export
    r_csv = emp.get("/api/employee/attendance/export?format=csv&year=2026&month=10")
    assert r_csv.status_code == 200
    assert len(r_csv.content) > 200

    # 4. Strict isolation: Employee forbidden from workforce-wide roster export
    r_forbidden = emp.get("/roster/export?start_date=2026-10-01&end_date=2026-10-31")
    assert r_forbidden.status_code == 403

if __name__ == "__main__":
    test_export_formats_and_data_isolation()
    print("ALL EXPORT AUTOMATED TESTS PASSED!")

