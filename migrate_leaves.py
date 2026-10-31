import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shiftflow.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. Create leave_attachments table
cur.execute("""
CREATE TABLE IF NOT EXISTS leave_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    leave_request_id INTEGER NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    stored_path VARCHAR(500) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_size_bytes INTEGER,
    doc_category VARCHAR(80) DEFAULT 'Medical / Supporting Evidence',
    uploaded_by_id INTEGER,
    is_active BOOLEAN DEFAULT 1,
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(leave_request_id) REFERENCES leave_requests(id),
    FOREIGN KEY(uploaded_by_id) REFERENCES users(id)
);
""")

# 2. Create leave_history table
cur.execute("""
CREATE TABLE IF NOT EXISTS leave_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    leave_request_id INTEGER NOT NULL,
    action VARCHAR(80) NOT NULL,
    actor_id INTEGER,
    actor_name VARCHAR(120),
    previous_state TEXT,
    new_state TEXT,
    remarks TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(leave_request_id) REFERENCES leave_requests(id),
    FOREIGN KEY(actor_id) REFERENCES users(id)
);
""")

# 3. Add columns to leave_requests if missing
cur.execute("PRAGMA table_info(leave_requests);")
cols = [c[1] for c in cur.fetchall()]

if "application_number" not in cols:
    cur.execute("ALTER TABLE leave_requests ADD COLUMN application_number VARCHAR(50);")
if "day_part" not in cols:
    cur.execute("ALTER TABLE leave_requests ADD COLUMN day_part VARCHAR(20) DEFAULT 'full';")
if "updated_at" not in cols:
    cur.execute("ALTER TABLE leave_requests ADD COLUMN updated_at DATETIME;")
if "cancellation_reason" not in cols:
    cur.execute("ALTER TABLE leave_requests ADD COLUMN cancellation_reason TEXT;")
if "cancellation_requested_at" not in cols:
    cur.execute("ALTER TABLE leave_requests ADD COLUMN cancellation_requested_at DATETIME;")
if "cancelled_by" not in cols:
    cur.execute("ALTER TABLE leave_requests ADD COLUMN cancelled_by VARCHAR(100);")
if "cancelled_at" not in cols:
    cur.execute("ALTER TABLE leave_requests ADD COLUMN cancelled_at DATETIME;")

# Populate application_number for existing leave requests if null
cur.execute("SELECT id, created_at FROM leave_requests WHERE application_number IS NULL;")
rows = cur.fetchall()
for rid, c_at in rows:
    prefix = c_at[:10].replace("-", "") if c_at else "20261026"
    app_num = f"LA-{prefix}-{rid:04d}"
    cur.execute("UPDATE leave_requests SET application_number = ? WHERE id = ?;", (app_num, rid))

conn.commit()
conn.close()
print("Leave management tables and schema migration completed successfully!")
