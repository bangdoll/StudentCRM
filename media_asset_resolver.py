"""媒體資產儲存與 CDN 解析深模組 (MediaAssetResolver)。

依據 Ports & Adapters (Hexagonal Architecture) 與 John Ousterhout 深模組原則設計：
將教學筆記圖檔的 URL 解析、雲端 CDN / Supabase Storage 轉譯、
Markdown 內嵌圖片替換與圖片引用分析完全封裝於單一介面之後。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from dotenv import load_dotenv


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}


class MediaAssetResolver:
    """媒體資產解析器：負責在本地靜態伺服與遠端 CDN / Storage 間透明解析。"""

    def __init__(
        self,
        base_url: str | None = None,
        local_prefix: str = "/static/teaching_assets",
    ) -> None:
        """初始化解析器。

        優先順序：
        1. 顯式傳入之 base_url。
        2. 環境變數 STUDENTCRM_MEDIA_BASE_URL。
        3. 若有 SUPABASE_URL 且 STUDENTCRM_USE_SUPABASE_STORAGE 為 true，則使用 Supabase Storage 公開 bucket。
        4. 預設回退至本地靜態路由 local_prefix (如 /static/teaching_assets)。
        """
        self.local_prefix = local_prefix.rstrip("/")
        self._custom_base_url = base_url
        self._resolved_base_url = ""
        self._load_config()

    def _load_config(self) -> None:
        if self._custom_base_url is not None:
            self._resolved_base_url = self._custom_base_url.strip().rstrip("/")
            return

        # 嘗試從環境變數載入
        env_media_url = os.getenv("STUDENTCRM_MEDIA_BASE_URL", "").strip().rstrip("/")
        if env_media_url:
            self._resolved_base_url = env_media_url
            return

        use_supabase = os.getenv("STUDENTCRM_USE_SUPABASE_STORAGE", "").lower() in ("1", "true", "yes")
        supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        if use_supabase and supabase_url:
            bucket_name = os.getenv("STUDENTCRM_STORAGE_BUCKET", "teaching_assets").strip()
            self._resolved_base_url = f"{supabase_url}/storage/v1/object/public/{bucket_name}"
            return

        self._resolved_base_url = self.local_prefix

    @property
    def base_url(self) -> str:
        """當前解析器所使用的 Base URL。"""
        return self._resolved_base_url

    def is_cloud_enabled(self) -> bool:
        """判斷當前是否指向外部雲端 CDN 或 Storage (非本機相對路徑)。"""
        return self._resolved_base_url.startswith(("http://", "https://"))

    def sanitize_filename(self, image_ref: str) -> str:
        """從任何帶路徑的前綴中安全提取純檔案名稱。"""
        cleaned = image_ref.strip()
        # 移除 URL 查詢參數或 hash
        cleaned = cleaned.split("?")[0].split("#")[0]
        # 移除常見已知前綴
        for prefix in (
            "/static/teaching_assets/",
            "static/teaching_assets/",
            "/assets/",
            "assets/",
        ):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :]
                break
        return Path(cleaned).name

    def resolve_url(self, image_ref: str) -> str:
        """將圖片引用路徑解析為目標公開訪問 URL。

        若輸入已經是完整的 http/https 網址，直接回傳。
        若輸入為本地檔名或 assets/ 相對路徑，則拼裝為當前 Base URL。
        """
        ref = image_ref.strip()
        if not ref:
            return ""

        if ref.startswith(("http://", "https://", "data:")):
            return ref

        filename = self.sanitize_filename(ref)
        if not filename:
            return ref

        return f"{self._resolved_base_url}/{filename}"

    @staticmethod
    def _parse_markdown_image_target(inner_target: str) -> tuple[str, str]:
        """安全解析 Markdown 圖片括號內的路徑與標題。
        
        支援格式：
        - path.png
        - path with spaces.png
        - path.png "title"
        - path with spaces.png "title"
        - <path with spaces.png>
        - <path with spaces.png> "title"
        """
        inner = inner_target.strip()
        if not inner:
            return "", ""

        # 1. 處理角括號 <url>
        if inner.startswith("<") and ">" in inner:
            idx = inner.find(">")
            raw_url = inner[1:idx].strip()
            rest = inner[idx + 1 :].strip()
            title_part = f" {rest}" if rest else ""
            return raw_url, title_part

        # 2. 檢查尾部是否有以引號包裹的 title (如 "title" 或 'title')
        title_match = re.search(r'\s+([\"\'].*?[\"\'])$', inner)
        if title_match:
            title_part = f" {title_match.group(1)}"
            raw_url = inner[: title_match.start()].strip()
            return raw_url, title_part

        return inner, ""

    def extract_image_references(self, markdown_text: str) -> list[str]:
        """從 Markdown 文本中萃取所有引用的教學圖片檔案名稱 (去重並按出現順序排列)。"""
        if not markdown_text:
            return []

        pattern = r'!\[.*?\]\((.*?)\)'
        found: list[str] = []
        seen: set[str] = set()

        for match in re.finditer(pattern, markdown_text):
            raw_target, _ = self._parse_markdown_image_target(match.group(1))
            if not raw_target:
                continue
            # 若為外部網址，跳過本地同步提取
            if raw_target.startswith(("http://", "https://", "data:")):
                continue
            filename = self.sanitize_filename(raw_target)
            if filename and filename not in seen:
                suffix = Path(filename).suffix.lower()
                if suffix in IMAGE_EXTENSIONS or not suffix:
                    seen.add(filename)
                    found.append(filename)

        return found

    def transform_markdown_media(self, markdown_text: str) -> str:
        """單一法定管道：將 Markdown 文本中的圖片引用統一轉譯為當前環境的有效 URL。

        支援匹配：
        - ![alt](assets/image.png)
        - ![alt](/assets/image.png)
        - ![alt](/static/teaching_assets/image.png)
        - ![alt](image.png) (具常見圖檔副檔名)
        - 帶有空格的檔名：![alt](assets/Pasted image 2026.png)
        - 帶有 title 的語法：![alt](assets/image.png "標題")
        - 角括號語法：![alt](<assets/image with spaces.png>)
        """
        if not markdown_text:
            return ""

        pattern = r'!\[(.*?)\]\((.*?)\)'

        def _repl(match: re.Match) -> str:
            alt_text = match.group(1)
            raw_url, title_part = self._parse_markdown_image_target(match.group(2))
            if not raw_url:
                return match.group(0)

            # 外部 URL 或 data URI 直接保留
            if raw_url.startswith(("http://", "https://", "data:")):
                return match.group(0)

            # 判斷是否為本地教學圖片資產
            is_asset_path = any(
                raw_url.startswith(p)
                for p in ("/static/teaching_assets/", "static/teaching_assets/", "/assets/", "assets/")
            )
            has_img_ext = Path(raw_url).suffix.lower() in IMAGE_EXTENSIONS

            if is_asset_path or has_img_ext:
                new_url = self.resolve_url(raw_url)
                return f"![{alt_text}]({new_url}{title_part})"

            return match.group(0)

        return re.sub(pattern, _repl, markdown_text)


# 全域單例快取
_DEFAULT_RESOLVER: MediaAssetResolver | None = None


def get_media_resolver(
    base_url: str | None = None,
    reload: bool = False,
) -> MediaAssetResolver:
    """取得全域 MediaAssetResolver 單例。

    若指定 reload=True 或傳入自訂 base_url，則重新建構實例。
    """
    global _DEFAULT_RESOLVER
    if _DEFAULT_RESOLVER is None or reload or base_url is not None:
        _DEFAULT_RESOLVER = MediaAssetResolver(base_url=base_url)
    return _DEFAULT_RESOLVER
