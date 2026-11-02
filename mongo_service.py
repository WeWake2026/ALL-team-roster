"""
MongoDB Atlas Connector & Data Mirror Service
Manages connection to MongoDB Atlas and provides dual-write / backup functionality
for ShiftFlow Pro workforce records, roster matrices, and user session logs.
"""

import os
from typing import Optional, Dict, Any, List
from datetime import datetime, date
from pymongo import MongoClient
from pymongo.database import Database

# MongoDB Atlas URI from environment or default
MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "msedcl_workforce")

_client: Optional[MongoClient] = None
_db: Optional[Database] = None

def get_mongo_db() -> Optional[Database]:
    """
    Initializes and returns the MongoDB database client instance if configured.
    Falls back gracefully if connection is not configured or offline.
    """
    global _client, _db
    if _db is not None:
        return _db
    
    uri = os.getenv("MONGODB_URI") or MONGODB_URI
    if not uri or "<db_password>" in uri:
        return None
    
    try:
        _client = MongoClient(
            uri,
            serverSelectionTimeoutMS=4000,
            connectTimeoutMS=4000
        )
        # Test connection ping
        _client.admin.command('ping')
        _db = _client[MONGODB_DB_NAME]
        print(f"[MongoDB] Successfully connected to MongoDB Atlas database: {MONGODB_DB_NAME}")
        return _db
    except Exception as e:
        print(f"[MongoDB] Warning: Could not connect to MongoDB Atlas ({e}). Running in standalone SQL mode.")
        _db = None
        return None

def is_mongo_connected() -> bool:
    """Checks if MongoDB connection is active and responsive"""
    db = get_mongo_db()
    return db is not None

def mongo_sync_document(collection_name: str, key_field: str, key_value: Any, document: Dict[str, Any]) -> bool:
    """
    Upserts a document into MongoDB Atlas collection asynchronously/safely.
    """
    db = get_mongo_db()
    if db is None:
        return False
    try:
        doc = dict(document)
        # Convert date and datetime objects for clean BSON storage
        for k, v in doc.items():
            if isinstance(v, date) and not isinstance(v, datetime):
                doc[k] = datetime.combine(v, datetime.min.time())
        
        doc["updated_at_mongo"] = datetime.utcnow()
        db[collection_name].update_one(
            {key_field: key_value},
            {"$set": doc},
            upsert=True
        )
        return True
    except Exception as e:
        print(f"[MongoDB] Failed to sync document to {collection_name}: {e}")
        return False

def mongo_log_audit_event(event_dict: Dict[str, Any]) -> bool:
    """Logs an audit or session event directly into MongoDB Atlas audit_events collection"""
    db = get_mongo_db()
    if db is None:
        return False
    try:
        ev = dict(event_dict)
        ev["logged_at"] = datetime.utcnow()
        db["audit_logs"].insert_one(ev)
        return True
    except Exception as e:
        print(f"[MongoDB] Audit log error: {e}")
        return False

def sync_all_sqlite_to_mongodb(sql_session) -> Dict[str, Any]:
    """
    Full migration / snapshot tool: reads all tables from SQLite and mirrors
    them into MongoDB Atlas collections.
    """
    import models
    db = get_mongo_db()
    if db is None:
        return {"status": "error", "message": "MongoDB is not connected or URI is missing credentials."}

    counts = {}
    try:
        # 1. Sync Users
        users = sql_session.query(models.User).all()
        user_docs = []
        for u in users:
            doc = {
                "user_id": u.id,
                "unique_id": u.unique_id,
                "name": u.name,
                "email": u.email,
                "crm_id": u.crm_id,
                "bm_id": u.bm_id,
                "ecn": u.ecn,
                "role_title": u.role_title,
                "access_level": u.access_level,
                "location": u.location,
                "department": u.department,
                "is_active": u.is_active,
                "cl_balance": u.cl_balance,
                "sl_balance": u.sl_balance,
                "pl_balance": u.pl_balance,
                "co_balance": u.co_balance,
                "synced_at": datetime.utcnow()
            }
            db["users"].update_one({"unique_id": u.unique_id}, {"$set": doc}, upsert=True)
            user_docs.append(doc)
        counts["users"] = len(user_docs)

        # 2. Sync Roster Entries
        entries = sql_session.query(models.RosterEntry).all()
        roster_count = 0
        for re in entries:
            doc = {
                "entry_id": re.id,
                "user_id": re.user_id,
                "date": datetime.combine(re.date, datetime.min.time()) if re.date else None,
                "shift_code": re.shift_code_or_time,
                "status": re.status,
                "updated_by": re.updated_by,
                "synced_at": datetime.utcnow()
            }
            db["roster_entries"].update_one({"entry_id": re.id}, {"$set": doc}, upsert=True)
            roster_count += 1
        counts["roster_entries"] = roster_count

        # 3. Sync Leave Requests
        leaves = sql_session.query(models.LeaveRequest).all()
        leave_count = 0
        for lv in leaves:
            doc = {
                "request_id": lv.id,
                "application_number": lv.application_number,
                "user_id": lv.user_id,
                "leave_type": lv.leave_type,
                "start_date": datetime.combine(lv.start_date, datetime.min.time()) if lv.start_date else None,
                "end_date": datetime.combine(lv.end_date, datetime.min.time()) if lv.end_date else None,
                "duration_days": lv.duration_days,
                "status": lv.status,
                "reason": lv.reason,
                "synced_at": datetime.utcnow()
            }
            db["leave_requests"].update_one({"request_id": lv.id}, {"$set": doc}, upsert=True)
            leave_count += 1
        counts["leave_requests"] = leave_count

        return {"status": "success", "counts": counts, "database": MONGODB_DB_NAME}
    except Exception as e:
        return {"status": "error", "message": str(e)}
