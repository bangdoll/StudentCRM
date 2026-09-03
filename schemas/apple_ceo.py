"""schemas/apple_ceo.py
蘋果總裁班領域模型 (Apple CEO Class Domain Entities)。
"""

from typing import Optional
from pydantic import BaseModel, Field


class AppleAttendanceRecord(BaseModel):
    """蘋果總裁班單堂出席記錄實體。"""
    date: str = Field(..., description="開課日期 (YYYY-MM-DD)")
    attendees: list[str] = Field(default_factory=list, description="當天出席學員名冊")
    cost_per_person: int = Field(default=150, ge=0, description="每人場地費用")
    total_cost: int = Field(default=0, ge=0, description="當天場地費總額")
    count: int = Field(default=0, ge=0, description="當天出席總人數")


class AppleLedgerItem(BaseModel):
    """場地費收支流水帳實體。"""
    id: str = Field(..., description="流水唯一識別碼")
    date: str = Field(..., description="記帳日期 (YYYY-MM-DD)")
    type: str = Field(..., description="類型 (支出 / 收入 / 儲值)")
    amount: int = Field(..., description="異動金額")
    balance_after: int = Field(..., description="結餘金額")
    note: Optional[str] = Field(default="", description="記帳備註")
