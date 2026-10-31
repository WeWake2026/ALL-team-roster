import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shiftflow.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. Create new organizational and RBAC tables if they don't exist
cur.execute("""
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    code VARCHAR(20) NOT NULL UNIQUE,
    address TEXT,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(location_id) REFERENCES locations(id)
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    department_id INTEGER,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(30),
    team_lead_id INTEGER,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(department_id) REFERENCES departments(id),
    FOREIGN KEY(team_lead_id) REFERENCES users(id)
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS user_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    location_id INTEGER,
    department_id INTEGER,
    team_id INTEGER,
    team_lead_id INTEGER,
    assigned_employee_id INTEGER,
    can_view BOOLEAN DEFAULT 1,
    can_create BOOLEAN DEFAULT 0,
    can_edit BOOLEAN DEFAULT 0,
    can_approve BOOLEAN DEFAULT 0,
    can_export BOOLEAN DEFAULT 0,
    effective_from DATE NOT NULL,
    effective_to DATE,
    status VARCHAR(20) DEFAULT 'Active',
    notes TEXT,
    created_by_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(location_id) REFERENCES locations(id),
    FOREIGN KEY(department_id) REFERENCES departments(id),
    FOREIGN KEY(team_id) REFERENCES teams(id),
    FOREIGN KEY(team_lead_id) REFERENCES users(id),
    FOREIGN KEY(assigned_employee_id) REFERENCES users(id),
    FOREIGN KEY(created_by_id) REFERENCES users(id)
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    actor_name VARCHAR(120),
    action VARCHAR(80) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(50),
    details TEXT,
    ip_address VARCHAR(50),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(actor_id) REFERENCES users(id)
);
""")

# 2. Add columns to users table safely if missing
cur.execute("PRAGMA table_info(users);")
user_cols = [c[1] for c in cur.fetchall()]

if "location_id" not in user_cols:
    cur.execute("ALTER TABLE users ADD COLUMN location_id INTEGER REFERENCES locations(id);")
if "department_id" not in user_cols:
    cur.execute("ALTER TABLE users ADD COLUMN department_id INTEGER REFERENCES departments(id);")
if "team_id" not in user_cols:
    cur.execute("ALTER TABLE users ADD COLUMN team_id INTEGER REFERENCES teams(id);")
if "team_lead_id" not in user_cols:
    cur.execute("ALTER TABLE users ADD COLUMN team_lead_id INTEGER REFERENCES users(id);")

# 3. Add columns to roster_entries table safely if missing
cur.execute("PRAGMA table_info(roster_entries);")
roster_cols = [c[1] for c in cur.fetchall()]

if "location_id" not in roster_cols:
    cur.execute("ALTER TABLE roster_entries ADD COLUMN location_id INTEGER REFERENCES locations(id);")
if "approval_status" not in roster_cols:
    cur.execute("ALTER TABLE roster_entries ADD COLUMN approval_status VARCHAR(20) DEFAULT 'Approved';")
if "approved_by" not in roster_cols:
    cur.execute("ALTER TABLE roster_entries ADD COLUMN approved_by VARCHAR(100);")
if "version" not in roster_cols:
    cur.execute("ALTER TABLE roster_entries ADD COLUMN version INTEGER DEFAULT 1;")

# 4. Seed standard locations and departments if empty
cur.execute("SELECT COUNT(*) FROM locations;")
if cur.fetchone()[0] == 0:
    locations_data = [
        ("Mumbai", "MUM", "MSEDCL Operational Center, Bandra East, Mumbai"),
        ("Pune", "PUN", "MSEDCL Zonal Office, Rasta Peth, Pune"),
        ("Nagpur", "NAG", "MSEDCL Regional Operations, Civil Lines, Nagpur"),
        ("Headquarters", "HQ", "MSEDCL Corporate Central, Prakashgad, Mumbai")
    ]
    cur.executemany("INSERT INTO locations (name, code, address) VALUES (?, ?, ?);", locations_data)

# Fetch location IDs
cur.execute("SELECT id, name FROM locations;")
loc_map = {row[1].upper(): row[0] for row in cur.fetchall()}

# Seed departments if empty
cur.execute("SELECT COUNT(*) FROM departments;")
if cur.fetchone()[0] == 0:
    depts_data = [
        (loc_map.get("MUMBAI"), "Operations", "OPS"),
        (loc_map.get("MUMBAI"), "Quality Audit", "QA"),
        (loc_map.get("MUMBAI"), "Customer Relations", "CRM"),
        (loc_map.get("HEADQUARTERS"), "Human Resources", "HR"),
        (loc_map.get("HEADQUARTERS"), "Administration", "ADMIN"),
        (loc_map.get("PUNE"), "Regional Operations", "RO-PUN"),
        (loc_map.get("NAGPUR"), "Regional Operations", "RO-NAG")
    ]
    cur.executemany("INSERT INTO departments (location_id, name, code) VALUES (?, ?, ?);", depts_data)

# Fetch department IDs
cur.execute("SELECT id, name FROM departments;")
dept_map = {row[1].upper(): row[0] for row in cur.fetchall()}

# Seed teams if empty
cur.execute("SELECT COUNT(*) FROM teams;")
if cur.fetchone()[0] == 0:
    teams_data = [
        (dept_map.get("OPERATIONS"), "Twitter/DM/Mail Response Team", "OPS-TWT"),
        (dept_map.get("OPERATIONS"), "Floor Operations Alpha", "OPS-FLR-A"),
        (dept_map.get("QUALITY AUDIT"), "Quality Assessment Squad", "QA-SQD"),
        (dept_map.get("HUMAN RESOURCES"), "HR & People Ops", "HR-CORE")
    ]
    cur.executemany("INSERT INTO teams (department_id, name, code) VALUES (?, ?, ?);", teams_data)

# 5. Populate location_id and department_id for existing users
cur.execute("SELECT id, location, department, role_title FROM users;")
all_users = cur.fetchall()

mumbai_id = loc_map.get("MUMBAI")
hq_id = loc_map.get("HEADQUARTERS")
ops_dept_id = dept_map.get("OPERATIONS")
admin_dept_id = dept_map.get("ADMINISTRATION")

for uid, uloc, udept, urole in all_users:
    target_loc_id = hq_id if (uloc and "HEADQUARTERS" in uloc.upper()) else mumbai_id
    target_dept_id = admin_dept_id if (udept and "ADMIN" in udept.upper()) else ops_dept_id
    cur.execute("UPDATE users SET location_id = ?, department_id = ? WHERE id = ?;", (target_loc_id, target_dept_id, uid))

# 6. Populate location_id in roster_entries based on user's location
cur.execute("""
UPDATE roster_entries 
SET location_id = (SELECT location_id FROM users WHERE users.id = roster_entries.user_id)
WHERE location_id IS NULL;
""")

# 7. Create TL and HR persona user records if not already present
cur.execute("SELECT id FROM users WHERE email = 'tl.poonam@msedcl.com';")
if not cur.fetchone():
    from auth import get_password_hash
    pwd_hash = get_password_hash("Welcome@123")
    # Promote or add Poonam as Team Leader
    cur.execute("""
    INSERT INTO users (unique_id, name, email, role_title, access_level, department, location, location_id, department_id, hashed_password, is_active)
    VALUES ('TL001', 'Poonam Gaikwad (TL)', 'tl.poonam@msedcl.com', 'Team Leader', 'Team Leader', 'Operations', 'Mumbai', ?, ?, ?, 1);
    """, (mumbai_id, ops_dept_id, pwd_hash))

cur.execute("SELECT id FROM users WHERE email = 'hr.sneha@msedcl.com';")
if not cur.fetchone():
    from auth import get_password_hash
    pwd_hash = get_password_hash("Welcome@123")
    hr_dept_id = dept_map.get("HUMAN RESOURCES")
    cur.execute("""
    INSERT INTO users (unique_id, name, email, role_title, access_level, department, location, location_id, department_id, hashed_password, is_active)
    VALUES ('HR001', 'Sneha Kulkarni (HR)', 'hr.sneha@msedcl.com', 'HR Officer', 'HR', 'Human Resources', 'Headquarters', ?, ?, ?, 1);
    """, (hq_id, hr_dept_id, pwd_hash))

cur.execute("SELECT id FROM users WHERE email = 'mgr.rajesh@msedcl.com';")
if not cur.fetchone():
    from auth import get_password_hash
    pwd_hash = get_password_hash("Welcome@123")
    cur.execute("""
    INSERT INTO users (unique_id, name, email, role_title, access_level, department, location, location_id, department_id, hashed_password, is_active)
    VALUES ('MGR001', 'Rajesh Patil (Ops Mgr)', 'mgr.rajesh@msedcl.com', 'Operations Manager', 'Location Manager', 'Operations', 'Mumbai', ?, ?, ?, 1);
    """, (mumbai_id, ops_dept_id, pwd_hash))

conn.commit()
conn.close()
print("Migration completed successfully!")
