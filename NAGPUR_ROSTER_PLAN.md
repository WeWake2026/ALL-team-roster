# Nagpur Roster Integration & Data Ingestion Plan

## 1. Executive Summary

This document details the analysis, data audit, and implementation blueprint for integrating the **Nagpur Operational Workforce Roster** into the ShiftFlow Pro system (MSEDCL Quality Audit & Workforce Management Portal).

The dataset provided contains:
- **189 Active Operational Staff Members** operating across 5 round-the-clock shifts.
- **Roster Schedule for 8 Consecutive Operational Days**: Sunday, 01-Nov-2026 to Sunday, 08-Nov-2026.
- **Historical Offboarded Staff Records**: Documenting join dates, Last Working Days (LWD), and departure tracking from May 2025 through September 2026.
- **Shift Distribution**: Morning (`07:00-16:00`), General (`09:00-18:00`), Evening (`16:00-01:00`), Late (`18:00-03:00`), and Night (`22:00-07:00`).

---

## 2. Data Audit & Breakdown

### 2.1 Active Workforce Categories (Total: 189)

- **Customer Care Executives (CCE)**: 158
- **Trainees (TR)**: 24
- **Subject Matter Experts (SME)**: 5
- **Quality Auditors (QA)**: 1
- **Administrative Leads (Admin)**: 1

### 2.2 Shift Windows & Staff Allocation

| Shift Code | Time Slot | Primary Category | Headcount Allocated | Typical Week-Off Coverage |
| :--- | :--- | :--- | :--- | :--- |
| **Morning (1st)** | `07:00 To 16:00` | Inbound CCE | 77 - 80 | Rotational across Mon–Sun |
| **General (2nd)** | `09:00 To 18:00` | TR / Admin / Quality | 23 - 26 | Fixed / Sunday / Weekday |
| **Evening (3rd)** | `16:00 To 01:00` | Operational Inbound | 55 - 59 | Rotational |
| **Late Evening (4th)** | `18:00 To 03:00` | Night Operations | 6 - 7 | Rotational |
| **Night (5th)** | `22:00 To 07:00` | 24/7 Overnight Desk | 22 - 25 | Rotational |

---

## 3. Roster Date Columns & Attendance Mapping

The 8 target operational dates in November 2026 and their format in the system:
- **01-Nov-2026 (Sun)**
- **02-Nov-2026 (Mon)**
- **03-Nov-2026 (Tue)**
- **04-Nov-2026 (Wed)**
- **05-Nov-2026 (Thu)**
- **06-Nov-2026 (Fri)**
- **07-Nov-2026 (Sat)**
- **08-Nov-2026 (Sun)**

### Attendance Code Normalization Table
| Raw Marker in File | Database Normalized Status | ShiftCodeOrTime | Meaning / UI Badge |
| :--- | :--- | :--- | :--- |
| `P` | `Present` | `[Assigned Shift Timing]` | Present on Duty |
| `P+HD` | `Half-Day` | `HD` | Present Half-Day |
| `WO` | `WO` | `WO` | Scheduled Weekly Off |
| `CO` | `CO` | `CO` | Compensatory Off |
| `A` | `Absent` | `A` | Unplanned Absence |
| `SL` | `Leave` | `SL` | Sick Leave |
| `CL` | `Leave` | `CL` | Casual Leave |

---

## 4. Offboarded / Inactive Employee Tracking

Historical records contain staff who departed between **May 2025 and September 2026**.
- **Ingestion Mode**: Set `is_active = False` and populate `exit_date = LWD`.
- **Audit Benefit**: Prevents orphan shifts, preserves historical logs, and blocks inactive staff from logging in or receiving new assignments after their exit date.

---

## 5. Implementation Roadmap

### Step 1: Parser & Ingestion Script
- Create an automated, idempotent migration script: `scripts/import_nagpur_roster.py`.
- Parse the 189 active employees + historical offboarded personnel.
- Validate email uniqueness and map `location_id = 3` (Nagpur).

### Step 2: User Account Creation
- Hash default initial passwords (`Welcome@123`).
- Set access levels according to designation:
  - `Admin` -> Access Level: `Admin`
  - `Quality` -> Access Level: `Quality`
  - `SME` -> Access Level: `SME`
  - `TR` / `CCE` -> Access Level: `Employee`

### Step 3: Populate Roster Entries
- Insert entries for each date in `2026-11-01` to `2026-11-08`.
- Compute weekly totals: `WO`, `CO`, `Leave`, `Present`.

### Step 4: MongoDB Atlas Dual Synchronization
- Run `mongo_service.sync_all_sqlite_to_mongodb` to synchronize all newly ingested Nagpur users and roster rows to the MongoDB Atlas cluster.

### Step 5: Verification & UI Testing
- Test `/roster?location=Nagpur` and `/roster/manage?target_date=2026-11-01`.
- Verify floor attendance desk reflects Nagpur staff and counts accurately.

