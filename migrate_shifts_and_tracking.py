import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shiftflow.db")

def migrate_shifts_and_tracking():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("Migrating shifts table schema...")
    cursor.execute("PRAGMA table_info(shifts);")
    shift_cols = [c[1] for c in cursor.fetchall()]

    if "is_overnight" not in shift_cols:
        cursor.execute("ALTER TABLE shifts ADD COLUMN is_overnight BOOLEAN DEFAULT 0;")
        print(" -> Added is_overnight column")

    if "break_duration_mins" not in shift_cols:
        cursor.execute("ALTER TABLE shifts ADD COLUMN break_duration_mins INTEGER DEFAULT 60;")
        print(" -> Added break_duration_mins column")

    if "applicable_locations" not in shift_cols:
        cursor.execute("ALTER TABLE shifts ADD COLUMN applicable_locations VARCHAR(255) DEFAULT 'All';")
        print(" -> Added applicable_locations column")

    if "effective_from" not in shift_cols:
        cursor.execute("ALTER TABLE shifts ADD COLUMN effective_from DATE;")
        print(" -> Added effective_from column")

    # Update default colors to match spec: Morning=blue, General=green, Afternoon=orange, Night=purple
    cursor.execute("UPDATE shifts SET color_code = 'blue' WHERE name LIKE '%Morning%';")
    cursor.execute("UPDATE shifts SET color_code = 'green' WHERE name LIKE '%General%';")
    cursor.execute("UPDATE shifts SET color_code = 'orange' WHERE name LIKE '%Afternoon%';")
    cursor.execute("UPDATE shifts SET color_code = 'purple', is_overnight = 1 WHERE name LIKE '%Night%';")

    # Create shift_change_history table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shift_change_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        roster_date DATE NOT NULL,
        previous_shift VARCHAR(50),
        new_shift VARCHAR(50) NOT NULL,
        previous_timings VARCHAR(50),
        new_timings VARCHAR(50),
        previous_location_id INTEGER,
        new_location_id INTEGER,
        changed_by_id INTEGER NOT NULL,
        changed_by_name VARCHAR(120) NOT NULL,
        change_reason TEXT,
        approval_status VARCHAR(30) DEFAULT 'Approved',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (changed_by_id) REFERENCES users(id),
        FOREIGN KEY (previous_location_id) REFERENCES locations(id),
        FOREIGN KEY (new_location_id) REFERENCES locations(id)
    );
    """)
    print(" -> Created/verified shift_change_history table")

    # Create roster_view_logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS roster_view_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        user_name VARCHAR(120) NOT NULL,
        user_role VARCHAR(50),
        view_type VARCHAR(50) NOT NULL,
        location_id INTEGER,
        location_name VARCHAR(80),
        team_context VARCHAR(100),
        view_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (location_id) REFERENCES locations(id)
    );
    """)
    print(" -> Created/verified roster_view_logs table")

    conn.commit()
    conn.close()
    print("Migration completed successfully!")

if __name__ == "__main__":
    migrate_shifts_and_tracking()
