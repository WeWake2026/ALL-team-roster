# ShiftFlow Pro — MSEDCL Workforce, Location & Combined Roster Management System

ShiftFlow Pro is an enterprise-grade workforce management, employee scheduling, attendance tracking, and role-based roster management ERP built for MSEDCL operations across Maharashtra.

---

## 🚀 How to Run Locally

### 1. Requirements
- Python 3.10+ (configured via `./venv`)
- SQLite 3 (database in `shiftflow.db`)

### 2. Run Local Development Server
Execute in PowerShell:
```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Open in Browser
- **Sign In Portal**: [http://127.0.0.1:8000/login](http://127.0.0.1:8000/login)
- **Employee Dashboard**: [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard)
- **Team Roster**: [http://127.0.0.1:8000/roster](http://127.0.0.1:8000/roster)
- **Workforce Reports**: [http://127.0.0.1:8000/reports](http://127.0.0.1:8000/reports)

---

## 🌟 Key Features & Modules

### 1. Enhanced Employee Dashboard (Pixel-Perfect UI)
- **Blue-Purple Welcome Banner**: Displays live operational date, operational timing window (09:00 AM – 10:00 PM), employee role, branch, unique employee ID, and direct action buttons (**Apply Leave** and **Full Team Roster**).
- **Green "Ready for Work" Operational Panel**:
  - Live animated duty halo indicator (Green Check / Play / Coffee Break).
  - Assigned shift details and status (e.g. `13:00 To 22:00` • Scheduled).
  - 5 soft pastel real-time metrics cards: **Break** (`0m / 60m`), **Preview** (`00:00`), **Ringing** (`00:00`), **ACW Work** (`00:00`), and **Talk Time** (`00:00`).
  - Shift control actions: **Start Work Shift**, **Take Break**, **Resume Work**, **Complete Shift**, and **Login Logs** popup.
- **4 Key Stat Cards**:
  - **Today's Shift**: Displays assigned timings with soft blue circular pin.
  - **Casual Leave (CL)**: Shows remaining days, taken days, and total eligible quota.
  - **Sick Leave (SL)**: Shows remaining days, taken days, and total eligible quota.
  - **Comp-Off (CO)**: Displays accrued overtime comp-off balance.
- **My Upcoming 7-Day Schedule Strip**:
  - Filter pills: **All**, **Working**, and **WO / Leave**.
  - Color-coded day badges with dot indicators (Blue for active shift, Red for Approved Leave, Slate for Week-Off).
- **Interactive Monthly Attendance Matrix & Calendar**:
  - Monthly navigation (`← Month Year →`).
  - 8 real-time KPI counters: **Present Days**, **Absent Days**, **Weekly Offs**, **Holidays**, **Approved Leaves**, **Half Days**, **Late Marks**, and **Scheduled Days**.
  - Interactive calendar grid: click any day to view complete shift timing, login punch-in time, logout punch-out time, net hours worked, and remarks.
  - Authorized export downloads: **Excel (.xlsx)**, **PDF Report**, **CSV**, and browser **Print**.

### 2. Location-Separated Timetables (Nagpur vs. Mumbai)
- **Nagpur Circle Timetable**:
  - Morning Shift (`07:00 To 16:00`)
  - General Shift (`09:00 To 18:00`)
  - Evening Shift (`16:00 To 01:00` Overnight)
  - Late Evening Shift (`18:00 To 03:00` Overnight)
  - Night Shift (`22:00 To 07:00` Overnight)
  - Plus `WO`, `CO`, `CL`, `SL`, `HD`.
- **Mumbai Circle Timetable**:
  - Morning Shift (`07:00 To 16:00`)
  - General Shift (`09:00 To 18:00`)
  - Mid-Day Shift (`11:00 To 20:00`)
  - Afternoon Shift (`13:00 To 22:00`)
  - Late Night Ops (`20:00 To 05:00` Overnight)
  - Night Shift (`22:00 To 07:00` Overnight)
  - Plus `WO`, `CO`, `CL`, `SL`, `HD`.
- Modal dropdowns (`Change Shift`, `Batch Timetable`, `Quick Cell Attendance`) dynamically adapt to the employee's assigned work circle.

### 3. Granular Schedule Cleanup & Roster Actions
- Precision cleanup tools: **Clear by Week**, **Clear by Single Day**, and **Clear by Shift Slot**.
- Impact calculation preview with audit confirmations to prevent accidental data wipes.

### 4. Interactive Weekday Picker & Headcount Analytics
- Monday–Sunday weekly date navigator with direct weekday pill selectors.
- 8 Headcount KPI cards with exact employee drill-down modals (Planned, In-Office, Present, WO, CL, SL, CO, Absent).
- Location-scoped data protection ensuring non-admin supervisors view only their circle.

### 5. Role-Based Access Control (RBAC) & Pinned Sidebar Navigation
- Sleek dark navy sidebar (`#0B1120`) with smooth accordion drawer and collapsible width.
- Dynamic navigation matching user roles:
  - **Employee**: Dashboard, Team Roster, Leave Approvals, Reports, Settings.
  - **Supervisor / Lead / Admin**: Full suite with Location Roster, Combined Matrix, Shift Management, Leave Audit Master, User Accounts, and Audit Trail.

---

## 👥 Default Personas for Testing

| Persona / Role | Email / Unique ID | Password | Scope / Capabilities |
| :--- | :--- | :--- | :--- |
| **System Administrator** | `admin@msedcl.com` (`ADMIN001`) | `password123` | Universal access across all locations, user details editor, headcount manager, leave master & assignments |
| **Operational Staff** | `shashi.kurhade@arceus.in` (`AIPLCC175`) | `Welcome@123` | Operational staff, personal dashboard, 7-day schedule, monthly attendance matrix & export downloads |
| **Team Leader** | `poonam.gaikwad@arceus.in` (`AIPLCC114`) | `Welcome@123` | Team-scoped roster view, shift approvals, and subordinate scheduling |
| **Branch Employee** | `bhakti.chavan@arceus.in` (`AIPLCC899`) | `Welcome@123` | Schedule matrix & leave balance review |

---

## 🧪 Verification & Testing Commands

To run automated template and data verification tests:
```powershell
.\venv\Scripts\python.exe -c "import jinja2; env = jinja2.Environment(loader=jinja2.FileSystemLoader('templates')); [env.get_template(t) for t in ['base.html', 'dashboard.html', 'roster.html', 'reports.html', 'leaves.html']]; print('ALL TEMPLATES VALID')"
```

---

## 📂 Project Structure

```text
├── main.py                   # FastAPI core application, routes, APIs, and authentication
├── attendance_service.py     # Monthly attendance calculation and XLSX/PDF/CSV report generators
├── database.py               # SQLAlchemy database session and engine setup
├── models.py                 # Database schemas and ORM entities
├── excel_service.py          # Roster and leave import/export services
├── shiftflow.db              # SQLite operational database
├── templates/
│   ├── base.html             # Base shell, dark navy sidebar, and header layout
│   ├── dashboard.html        # Employee dashboard, Ready for Work panel, stats & calendar
│   ├── roster.html           # Team roster spreadsheet matrix and modals
│   ├── reports.html          # Analytics and operations report downloads
│   └── leaves.html           # Leave management and application portal
└── uploads/                  # User attachments and leave medical certificates
```
