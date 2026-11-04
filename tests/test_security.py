import httpx
import sqlite3

BASE = "http://127.0.0.1:8000"

def test_security_headers_and_cookies():
    # 1. OWASP ASVS Headers Check
    res = httpx.get(f"{BASE}/login")
    assert res.status_code == 200
    assert res.headers.get("x-frame-options") == "DENY"
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.headers.get("x-xss-protection") == "1; mode=block"
    assert "strict-origin" in res.headers.get("referrer-policy", "")
    assert "geolocation=()" in res.headers.get("permissions-policy", "")

def test_auth_and_bcrypt_migration():
    client = httpx.Client(base_url=BASE, follow_redirects=True)
    res = client.post("/login", data={"identifier": "admin@msedcl.com", "password": "password123"})
    assert res.status_code == 200
    assert "user_id" in client.cookies

    # Verify password hash upgraded in SQLite
    conn = sqlite3.connect("shiftflow.db")
    c = conn.cursor()
    c.execute("SELECT hashed_password FROM users WHERE email = 'admin@msedcl.com'")
    h = c.fetchone()[0]
    conn.close()
    assert h.startswith("$2b$12$"), f"Hash is not Bcrypt work factor 12: {h}"

def test_deactivated_account_rejection():
    client = httpx.Client(base_url=BASE, follow_redirects=True)
    res = client.post("/login", data={"identifier": "mgr.rajesh@msedcl.com", "password": "Welcome@123"})
    assert res.status_code == 200
    assert "deactivated" in res.text.lower() or "offboarded" in res.text.lower()
    assert "user_id" not in client.cookies

def test_rbac_unauthorized_access():
    emp = httpx.Client(base_url=BASE, follow_redirects=True)
    emp.post("/login", data={"identifier": "bhakti.chavan@arceus.in", "password": "Welcome@123"})
    
    # Attempt Admin Control Center
    r_cc = emp.get("/admin/control-center")
    assert r_cc.status_code == 403

    # Attempt Admin System Health API
    r_health = emp.get("/api/admin/system/health")
    assert r_health.status_code == 403

    # Attempt Organization Update API
    r_org = emp.post("/api/admin/organization/update", data={"name": "Hacked"})
    assert r_org.status_code == 403

if __name__ == "__main__":
    test_security_headers_and_cookies()
    test_auth_and_bcrypt_migration()
    test_deactivated_account_rejection()
    test_rbac_unauthorized_access()
    print("ALL SECURITY AUTOMATED TESTS PASSED!")

