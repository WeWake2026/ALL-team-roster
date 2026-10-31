# Setup & Deployment Guide — ShiftFlow Pro

## 1. System Requirements
- Operating System: Windows 10/11, macOS, or Linux
- Python: Version 3.10, 3.11, or 3.12
- Disk Space: At least 250 MB for dependencies and database storage

## 2. Local Environment Setup

### Step A: Clone or Navigate to Directory
```powershell
cd "c:\Users\Vivek\Downloads\MSEDCL_Quality_Audit_System_Starter\New folder"
```

### Step B: Virtual Environment Verification
The existing local virtual environment is present at `./venv`.
To verify package health:
```powershell
.\venv\Scripts\python.exe -c "import fastapi, openpyxl, pandas, sqlalchemy; print('Dependencies OK')"
```

If initializing a fresh virtual environment from scratch:
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Step C: Environment Configuration
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

### Step D: Database Verification & Migration
Run the non-destructive database schema migration to ensure all tables and relationships are created:
```powershell
.\venv\Scripts\python.exe migrate_db.py
```

### Step E: Start Local Web Server
```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

The portal will be accessible at: `http://127.0.0.1:8000`

---

## 3. Database Backup & Restore Operations

### How to Create a Point-in-Time Backup:
```powershell
Copy-Item "shiftflow.db" "shiftflow_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').db"
```

### How to Restore from Backup:
```powershell
Copy-Item "shiftflow_backup_20261026.db" "shiftflow.db" -Force
```
