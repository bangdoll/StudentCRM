"""schemas/radar.py
成效雷達與 CSM 續約決策領域模型 (Effectiveness Radar & CSM Domain Entities)。
"""

from typing import Optional, Any, Literal
from pydantic import BaseModel, Field


AIImportStageEnum = Literal["數位地基", "核心提示詞", "MVP自動化", "AI OS系統"]
RetentionSignalEnum = Literal["stable", "attention", "at_risk", "upgrade_ready"]


class ProductRecommendation(BaseModel):
    """產品階梯推薦。"""
    title: str = Field(..., description="推薦產品名稱 (e.g. 數位基礎救援包, 90分鐘工作流啟動課, MVP工作流建置, 90天AI OS陪跑)")
    slug: str = Field(..., description="產品唯一識別代碼")
    pitch_message: str = Field(..., description="教練提案與續課溝通話術建議")


class CSMFollowupRecord(BaseModel):
    """CSM 回訪與追蹤狀態記錄。"""
    status: Literal["pending", "contacted", "deferred"] = Field(default="pending", description="跟進狀態：待關心/已跟進/暫緩")
    last_contacted_date: Optional[str] = Field(default=None, description="最後聯繫日期 (YYYY-MM-DD)")
    next_followup_date: Optional[str] = Field(default=None, description="下次預計跟進日期")
    coach_notes: str = Field(default="", description="教練私密備忘錄")
    updated_at: str = Field(default="", description="最後更新時間戳記")


class EffectivenessRadarItem(BaseModel):
    """單一學員成效雷達完整項目。"""
    student_id: str = Field(..., description="學員唯一識別碼")
    name: str = Field(..., description="學員名稱")
    lessons_count: int = Field(default=0, ge=0, description="累計課次")
    current_cycle_lesson: int = Field(default=1, ge=0, description="當前梯次課次 (1~8)")
    latest_date: Optional[str] = Field(default="", description="最後上課日期")
    days_since_last: int = Field(default=999, description="距離上次上課天數")
    ai_import_stage: str = Field(default="數位地基", description="AI 導入階段")
    ai_stage_detail: str = Field(default="", description="導入階段成熟度說明")
    primary_pain: str = Field(default="", description="近期關鍵卡點或主要痛點")
    micro_action_cards: list[dict[str, Any]] = Field(default_factory=list, description="末次課堂 3 張微行動卡")
    task_staleness_warning: bool = Field(default=False, description="7天微任務卡是否停滯 (>14天)")
    retention_signal: str = Field(default="stable", description="留存與續約訊號代碼 (stable/attention/at_risk/upgrade_ready)")
    retention_signal_text: str = Field(default="穩定推進", description="留存訊號中文描述")
    retention_badge_class: str = Field(default="badge-success", description="前端徽章樣式類別")
    product_recommendation: ProductRecommendation = Field(..., description="對應推薦之產品階梯")
    followup: CSMFollowupRecord = Field(default_factory=CSMFollowupRecord, description="CSM 追蹤狀態")
    followup_copy: str = Field(default="", description="一鍵複製 7 天追蹤問候訊息")


class FollowupUpdateRequest(BaseModel):
    """CSM 跟進更新請求。"""
    student_id: str = Field(..., description="學員 ID")
    status: Literal["pending", "contacted", "deferred"] = Field(..., description="更新之狀態")
    next_followup_date: Optional[str] = Field(default="", description="下次追蹤日期")
    coach_notes: Optional[str] = Field(default="", description="教練備忘錄")
