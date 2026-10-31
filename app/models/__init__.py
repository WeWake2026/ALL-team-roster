import models

# Re-export all models from root models.py for seamless compatibility
User = models.User
Location = models.Location
Department = models.Department
Team = models.Team
UserAssignment = models.UserAssignment
AuditLog = models.AuditLog
LeaveBalance = models.LeaveBalance
Shift = models.Shift
Holiday = models.Holiday
Notification = models.Notification
ShiftChangeHistory = models.ShiftChangeHistory
RosterViewLog = models.RosterViewLog
RosterEntry = models.RosterEntry
LeaveRequest = models.LeaveRequest
LeaveHistory = models.LeaveHistory
LeaveAttachment = models.LeaveAttachment
UserPreference = models.UserPreference
CompanySetting = models.CompanySetting
UserSessionLog = models.UserSessionLog
WorkSession = models.WorkSession
SessionBreak = models.SessionBreak

__all__ = [
    "User", "Location", "Department", "Team", "UserAssignment", "AuditLog",
    "LeaveBalance", "Shift", "Holiday", "Notification", "ShiftChangeHistory",
    "RosterViewLog", "RosterEntry", "LeaveRequest", "LeaveHistory",
    "LeaveAttachment", "UserPreference", "CompanySetting", "UserSessionLog",
    "WorkSession", "SessionBreak"
]
