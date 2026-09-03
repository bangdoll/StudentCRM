"""schemas/__init__.py
領域實體與資料契約套件 (Domain Entities & Data Contracts)。
"""

from .student import StudentProfile
from .teaching import TeachingRecordItem
from .apple_ceo import AppleAttendanceRecord, AppleLedgerItem

__all__ = [
    "StudentProfile",
    "TeachingRecordItem",
    "AppleAttendanceRecord",
    "AppleLedgerItem",
]
