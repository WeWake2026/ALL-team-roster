import sqlite3
from datetime import date, datetime

conn = sqlite3.connect('shiftflow.db')
cursor = conn.cursor()

print("=== 1. Checking Users Table Integrity ===")
cursor.execute("SELECT count(*) FROM users WHERE email IS NULL OR email = '';")
print(f"Users missing email: {cursor.fetchone()[0]}")

cursor.execute("SELECT count(*) FROM users WHERE unique_id IS NULL OR unique_id = '';")
print(f"Users missing unique_id: {cursor.fetchone()[0]}")

cursor.execute("SELECT count(*) FROM users WHERE hashed_password IS NULL OR hashed_password = '';")
print(f"Users missing password hash: {cursor.fetchone()[0]}")

print("\n=== 2. Checking Roster Entries Integrity ===")
cursor.execute("SELECT count(*) FROM roster_entries WHERE user_id NOT IN (SELECT id FROM users);")
print(f"Orphaned roster entries: {cursor.fetchone()[0]}")

cursor.execute("SELECT count(*) FROM roster_entries WHERE shift_code_or_time IS NULL OR shift_code_or_time = '';")
print(f"Roster entries with blank shift: {cursor.fetchone()[0]}")

# Check duplicate roster entries for same user on same date
cursor.execute("""
SELECT user_id, date, count(*) as cnt 
FROM roster_entries 
GROUP BY user_id, date 
HAVING cnt > 1;
""")
dups = cursor.fetchall()
print(f"Duplicate roster entries (same user & date): {len(dups)}")

print("\n=== 3. Checking Leave Requests & Balances Integrity ===")
cursor.execute("SELECT count(*) FROM leave_requests WHERE user_id NOT IN (SELECT id FROM users);")
print(f"Orphaned leave requests: {cursor.fetchone()[0]}")

cursor.execute("SELECT count(*) FROM leave_requests WHERE end_date < start_date;")
print(f"Leave requests with end_date before start_date: {cursor.fetchone()[0]}")

# Check negative leave balances
cursor.execute("SELECT count(*) FROM users WHERE cl_balance < 0 OR sl_balance < 0 OR balance_cl < 0 OR balance_sl < 0;")
print(f"Users with negative leave balances: {cursor.fetchone()[0]}")

print("\n=== 4. Checking Shifts & Rotations Integrity ===")
cursor.execute("SELECT count(*) FROM shifts WHERE start_time IS NULL OR end_time IS NULL;")
print(f"Shifts with null start or end time: {cursor.fetchone()[0]}")

print("\n=== 5. Checking Session Logs & Active Sessions ===")
cursor.execute("SELECT count(*) FROM user_session_logs WHERE logout_time IS NOT NULL AND duration_seconds <= 0;")
print(f"Logged out sessions with invalid duration: {cursor.fetchone()[0]}")

conn.close()

