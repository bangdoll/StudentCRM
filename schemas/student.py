"""schemas/student.py
學員領域模型 (Student Domain Entity)。
嚴格保證 first_lesson_date 等關鍵資產非空且符合 YYYY-MM-DD 規格。
"""

import re
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator


class StudentProfile(BaseModel):
    """學員核心檔案實體。"""
    id: str = Field(..., description="學員唯一 UUID 或識別碼")
    name: str = Field(..., description="學員顯示名稱")
    file: Optional[str] = Field(default="", description="對應 Markdown 教案路徑")
    lessons_count: int = Field(default=0, ge=0, description="累計上課堂數")
    current_cycle_lesson: int = Field(default=1, ge=0, description="當前梯次進度 (1~8)")
    first_lesson_date: Optional[str] = Field(default=None, description="首次上課日期 (YYYY-MM-DD)")
    latest_date: Optional[str] = Field(default=None, description="最後上課日期 (YYYY-MM-DD)")
    next_lesson: Optional[str] = Field(default=None, description="下次預約日期")
    aliases: list[str] = Field(default_factory=list, description="別名/稱呼清單")
    hardware: list[str] = Field(default_factory=list, description="學員使用硬體")
    status: str = Field(default="active", description="學員生命週期狀態：active, paused, graduated, memorial")
    status_reason: Optional[str] = Field(default=None, description="狀態備註或原因，例如 deceased, long_term_inactive")
    raw: dict[str, Any] = Field(default_factory=dict, description="自訂擴充屬性")

    @field_validator("first_lesson_date")
    @classmethod
    def validate_first_lesson_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("", "未記錄", "TBD"):
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                raise ValueError(f"first_lesson_date 格式錯誤：{v}，必須為 YYYY-MM-DD")
        return v
