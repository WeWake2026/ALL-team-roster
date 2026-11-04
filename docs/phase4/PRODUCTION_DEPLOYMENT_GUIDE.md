# ShiftFlow Pro – Production Deployment & Operations Guide

**System Target:** ShiftFlow Workforce & Leave ERP (MSEDCL System)  
**Architecture:** Linux (Ubuntu 22.04 LTS or Enterprise Linux), Python 3.11+, Uvicorn, Nginx/Caddy, SQLite WAL  

---

## 1. Directory Structure & Permissions

Recommended production layout:
```text
/opt/shiftflow/
├── venv/                  # Python virtual environment (owned by shiftflow:shiftflow, 750)
├── main.py                # Core application entrypoint
├── database.py            # SQLite engine configuration
├── shiftflow.db           # Production database (mode 600, owned by shiftflow:shiftflow)
├── backups/               # Automated backups directory (mode 700)
│   └── automated/
├── logs/                  # Application logs (mode 750)
│   ├── app.log
│   └── backups.log
└── static/                # Static assets (mode 755)
```

Ensure the service user has exclusive ownership:
```bash
sudo useradd -r -s /bin/false shiftflow
sudo chown -R shiftflow:shiftflow /opt/shiftflow
sudo chmod 600 /opt/shiftflow/shiftflow.db
sudo chmod 700 /opt/shiftflow/backups
```

---

## 2. Environment Variables

Create `/opt/shiftflow/.env` (mode 600):
```ini
ENVIRONMENT=production
PYTHONUNBUFFERED=1
SECRET_KEY=msedcl_production_master_secret_key_change_in_production
ALLOWED_HOSTS=shiftflow.msedcl.com,127.0.0.1
```

---

## 3. Web Server & Reverse Proxy Setup

### Option A: Nginx (Recommended)
Copy [deploy/nginx_shiftflow.conf](file:///c:/Users/Vivek/Downloads/MSEDCL_Quality_Audit_System_Starter/New%20folder/deploy/nginx_shiftflow.conf) to `/etc/nginx/sites-available/shiftflow.conf`:
```bash
sudo ln -s /etc/nginx/sites-available/shiftflow.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Option B: Caddy (Automatic TLS)
Copy [deploy/Caddyfile](file:///c:/Users/Vivek/Downloads/MSEDCL_Quality_Audit_System_Starter/New%20folder/deploy/Caddyfile) to `/etc/caddy/Caddyfile`:
```bash
sudo systemctl reload caddy
```

---

## 4. Systemd Service Daemon

Copy [deploy/shiftflow.service](file:///c:/Users/Vivek/Downloads/MSEDCL_Quality_Audit_System_Starter/New%20folder/deploy/shiftflow.service) to `/etc/systemd/system/shiftflow.service`:
```bash
sudo systemctl daemon-reload
sudo systemctl enable shiftflow
sudo systemctl start shiftflow
sudo systemctl status shiftflow
```

---

## 5. Automated Backup Cron Job

Configure daily automated backups at 02:00 AM:
```bash
sudo crontab -u shiftflow -e
```
Add:
```cron
0 2 * * * /opt/shiftflow/venv/bin/python /opt/shiftflow/scripts/backup_database.py >> /opt/shiftflow/logs/backups.log 2>&1
```

---

## 6. Health & Readiness Verification
```bash
curl -f http://127.0.0.1:8000/health
curl -f http://127.0.0.1:8000/ready
```
Both probes must return HTTP 200 with JSON status `ok` and `ready`.

