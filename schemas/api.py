"""
schemas/api.py
API 強型別回傳契約 (API Response Contracts)。
依據 Matt Pocock 深模組原則與 FastAPI 規範，為路由層提供明確、防禦性高之型別契約。
"""

from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict


class APIStatusResponse(BaseModel):
    """通用狀態回傳契約。"""
    model_config = ConfigDict(extra="ignore")

    status: str = Field(..., description="回應狀態，如 'ok' 或 'error'")
    message: Optional[str] = Field(default=None, description="詳細訊息或錯誤提示")


class SyncStatusResponse(BaseModel):
    """資料庫同步狀態回傳契約。"""
    model_config = ConfigDict(extra="ignore")

    engine: str = Field(..., description="儲存引擎，如 'supabase' 或 'local'")
    source: str = Field(..., description="資料來源檔案或資料表")
    cache_path: str = Field(..., description="快取檔案路徑")
    last_error: Optional[str] = Field(default="", description="最後異常訊息")
    checked_at: Optional[str] = Field(default=None, description="檢查時間戳 (ISO8601)")


class StudentDetailResponse(BaseModel):
    """單一學員完整詳情 API 回傳契約。"""
    model_config = ConfigDict(extra="ignore")

    status: str = Field(..., description="狀態，'ok' 或 'not_found'")
    student_id: Optional[str] = Field(default=None, description="學員 ID")
    student: Optional[dict[str, Any]] = Field(default=None, description="學員核心資料")
    features: Optional[dict[str, Any]] = Field(default=None, description="AI 提取特徵")
    prediction: Optional[dict[str, Any]] = Field(default=None, description="學習與流失預測")
    sync: Optional[dict[str, Any]] = Field(default=None, description="資料同步狀態")


class DigitalManagementStudentItem(BaseModel):
    """數位管理個別學員資料契約。"""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="學員識別碼")
    name: str = Field(..., description="學員姓名")
    tags: list[str] = Field(default_factory=list, description="標籤")
    current_lesson: int = Field(default=0, description="目前完成堂數")
    next_lesson: Optional[str] = Field(default=None, description="下次排定上課時間")
    latest_lesson_date: Optional[str] = Field(default=None, description="最後上課日期")
    lessons: list[dict[str, Any]] = Field(default_factory=list, description="課表/出席紀錄")
    notes: list[dict[str, Any]] = Field(default_factory=list, description="教學筆記清單")
    source_summary: list[str] = Field(default_factory=list, description="資料來源匯總")


class DigitalManagementListResponse(BaseModel):
    """數位管理教學學員清單回傳契約。"""
    model_config = ConfigDict(extra="ignore")

    status: str = Field(default="ok", description="狀態")
    count: int = Field(default=0, description="學員總數")
    students: list[DigitalManagementStudentItem] = Field(default_factory=list, description="學員檔案清單")
    calendar_event_count: int = Field(default=0, description="日曆事件數")
    local_note_count: int = Field(default=0, description="本地筆記數")
    teaching_note_count: int = Field(default=0, description="教學紀錄數")
    calendar_cache: Optional[str] = Field(default="", description="日曆快取路徑")
    heptabase_backup_root: Optional[str] = Field(default="", description="Heptabase 備份路徑")


class DigitalManagementDetailResponse(BaseModel):
    """數位管理個別學員 API 回傳契約。"""
    model_config = ConfigDict(extra="ignore")

    status: str = Field(..., description="狀態，'ok' 或 'not_found'")
    student_id: Optional[str] = Field(default=None, description="學員 ID")
    student: Optional[dict[str, Any]] = Field(default=None, description="學員數位檔案")
    calendar_cache: Optional[str] = Field(default="", description="日曆快取路徑")
    heptabase_backup_root: Optional[str] = Field(default="", description="Heptabase 備份根目錄")


class RadarRefreshResponse(BaseModel):
    """成效雷達手動重算回傳契約。"""
    model_config = ConfigDict(extra="ignore")

    success: bool = Field(..., description="是否重算成功")
    generated_at: str = Field(..., description="生成時間戳 (ISO8601)")
    items_count: int = Field(default=0, description="雷達評估學員總數")


class CSMFollowupUpdateResponse(BaseModel):
    """CSM 回訪紀錄更新回傳契約。"""
    model_config = ConfigDict(extra="ignore")

    success: bool = Field(..., description="是否更新成功")
    student_id: str = Field(..., description="學員 ID")
    followup: dict[str, Any] = Field(default_factory=dict, description="最新跟進狀態資料")
