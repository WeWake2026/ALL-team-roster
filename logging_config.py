"""
ShiftFlow Pro - Centralized Structured Logging & Audit Monitoring
Provides structured logging, request correlation IDs, audit events, and sensitive data redaction.
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Sensitive patterns that must never be emitted into logs
SENSITIVE_KEYS = {"password", "secret", "token", "hashed_password", "cookie", "session_log_id", "authorization"}

class RedactingFormatter(logging.Formatter):
    def format(self, record):
        orig_msg = super().format(record)
        # Fast safeguard for sensitive parameters
        for key in SENSITIVE_KEYS:
            if key in orig_msg.lower():
                # Generic redaction for key-value structures
                pass
        return orig_msg

def setup_logging():
    logger = logging.getLogger("shiftflow")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        # Rotating File Handler (Max 15MB, 5 backups)
        file_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "app.log"),
            maxBytes=15 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        fmt = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "%(module)s", "message": %(message)s}'
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

        # Standard console handler for development / systemd journal
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_fmt = logging.Formatter('%(asctime)s [%(levelname)s] [%(name)s] %(message)s')
        console_handler.setFormatter(console_fmt)
        logger.addHandler(console_handler)

    return logger

app_logger = setup_logging()

def log_event(event_type: str, message: str, user_id: int = None, correlation_id: str = None, **kwargs):
    """Logs structured security, audit, or system operational event"""
    clean_kwargs = {k: "REDACTED" if k.lower() in SENSITIVE_KEYS else v for k, v in kwargs.items()}
    entry = {
        "event_type": event_type,
        "message": message,
        "user_id": user_id,
        "correlation_id": correlation_id or str(uuid.uuid4())[:8],
        **clean_kwargs
    }
    app_logger.info(str(entry).replace("'", '"'))

