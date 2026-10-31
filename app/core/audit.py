from typing import Optional
from sqlalchemy.orm import Session
import models

def log_audit_event(
    db: Session,
    actor: Optional[models.User],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None
):
    """
    Standardized Audit Trail Recorder across all routers.
    """
    actor_id = actor.id if actor else None
    actor_name = actor.name if actor else "System"

    audit_entry = models.AuditLog(
        actor_id=actor_id,
        actor_name=actor_name,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        details=details,
        ip_address=ip_address
    )
    db.add(audit_entry)
    db.commit()
