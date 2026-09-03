"""schemas/teaching.py
教學記錄領域模型 (Teaching Record Domain Entity)。
"""

from typing import Optional
from pydantic import BaseModel, Field


class TeachingRecordItem(BaseModel):
    """單篇課堂教學記錄實體。"""
    date: str = Field(..., description="上課日期 (YYYY-MM-DD)")
    title: str = Field(..., description="教案標題")
    filename: str = Field(..., description="Markdown 檔案名稱")
    student_name: Optional[str] = Field(default="", description="學員名稱")
    student_id: Optional[str] = Field(default="", description="學員 ID")
    path: Optional[str] = Field(default="", description="相對於專案之檔案路徑")
    preview: Optional[str] = Field(default="", description="課堂摘要預覽 (280 字)")
    content: Optional[str] = Field(default="", description="教案全文內容")
    word_count: Optional[int] = Field(default=0, ge=0, description="教案總字數")
    lesson_num: Optional[int] = Field(default=None, description="第幾堂課")
