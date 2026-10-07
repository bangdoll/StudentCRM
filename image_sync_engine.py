"""教學筆記圖片自癒、壓縮與同步深模組 (ImageSyncEngine)。

解耦自 teaching_sync.py 巨石腳本：
將 Markdown 圖片引用萃取、子目錄收攏、Heptabase CLI / 備份自癒、
PIL 輕量化壓制與 StudentCRM static/teaching_assets 鏡像同步完全封裝於此深模組之後。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from media_asset_resolver import get_media_resolver

logger = logging.getLogger(__name__)

UUID_REGEX = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


class ImageSyncEngine:
    """教學圖片資產自癒與同步引擎。"""

    def __init__(
        self,
        crm_dir: Path | str,
        workspace_dir: Path | str | None = None,
    ) -> None:
        self.crm_dir = Path(crm_dir).resolve()
        
        if workspace_dir:
            self.workspace_dir = Path(workspace_dir).resolve()
        else:
            # 自動從 crm_dir 往上尋找包含 01.Docs 或 OpenClaw 的根目錄
            curr = self.crm_dir
            while curr != curr.parent:
                if (curr / "01.Docs").is_dir() or (curr / "OpenClaw").is_dir():
                    break
                curr = curr.parent
            self.workspace_dir = curr

        self.src_assets = self.workspace_dir / "01.Docs" / "teaching" / "assets"
        self.dst_assets = self.crm_dir / "static" / "teaching_assets"
        self.backup_root = Path(os.path.expanduser("~/Documents/文件 - bangdoll’s MacBook Air - 1/Heptabase-auto-backup"))

        self.src_assets.mkdir(parents=True, exist_ok=True)
        self.dst_assets.mkdir(parents=True, exist_ok=True)

    def auto_gather_subfolder_assets(self) -> int:
        """自動收攏子目錄圖片（如 01.Docs/teaching/陳顧問/assets）至主 assets 目錄。"""
        gathered = 0
        chen_assets = self.workspace_dir / "01.Docs" / "teaching" / "陳顧問" / "assets"
        if chen_assets.is_dir():
            for cf in chen_assets.iterdir():
                if cf.is_file() and not cf.name.startswith("."):
                    target_cf = self.src_assets / cf.name
                    if not target_cf.exists():
                        shutil.copy2(cf, target_cf)
                        gathered += 1
        return gathered

    def heal_missing_image(self, img_name: str, target_dir: Path | None = None) -> Path | None:
        """若本地缺失圖片，嘗試透過 Heptabase CLI 或本地備份進行自癒抽取。"""
        out_dir = target_dir or self.src_assets
        out_dir.mkdir(parents=True, exist_ok=True)
        dest_file = out_dir / img_name

        if dest_file.exists() and dest_file.stat().st_size > 0:
            return dest_file

        uuid_matches = UUID_REGEX.findall(img_name)
        target_file_id = uuid_matches[-1] if uuid_matches else None

        # 1. 嘗試呼叫 Heptabase CLI export
        if target_file_id:
            try:
                cmd = ["heptabase", "file", "export", target_file_id, "--output-dir", str(out_dir)]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=25, check=False)
                if res.returncode == 0:
                    exp_data = json.loads(res.stdout)
                    exp_path = Path(exp_data.get("path", ""))
                    if exp_path.exists():
                        if exp_path.name != img_name:
                            shutil.copy2(exp_path, dest_file)
                        return dest_file
            except Exception as e:
                logger.warning("Heptabase CLI 匯出 %s 失敗: %s", img_name, e)

        # 2. 嘗試從本地備份目錄查找
        if self.backup_root.is_dir():
            try:
                candidates = sorted(self.backup_root.glob("Heptabase-Data-Backup-*"))
                if candidates:
                    latest = candidates[-1]
                    for asset_dir in latest.glob("**/*-assets"):
                        if not asset_dir.is_dir():
                            continue
                        exact = asset_dir / img_name
                        if exact.is_file():
                            shutil.copy2(exact, dest_file)
                            return dest_file
                        if target_file_id:
                            for f in asset_dir.iterdir():
                                if f.is_file() and target_file_id in f.name:
                                    shutil.copy2(f, dest_file)
                                    return dest_file
            except Exception as e:
                logger.warning("從本地備份抽取 %s 失敗: %s", img_name, e)

        return None

    def compress_and_copy(self, src_file: Path, dst_file: Path) -> bool:
        """壓制並拷貝單一圖片。小檔直接拷貝，大於 300KB 縮放壓制。"""
        if not src_file.exists() or not src_file.is_file():
            return False

        if dst_file.exists() and dst_file.stat().st_size > 0 and dst_file.stat().st_mtime >= src_file.stat().st_mtime:
            return False  # 已是最新，略過

        dst_file.parent.mkdir(parents=True, exist_ok=True)

        # 小於 300KB 直接拷貝
        if src_file.stat().st_size < 300 * 1024:
            dst_file.write_bytes(src_file.read_bytes())
            return True

        # 大於 300KB 以 PIL 壓制
        try:
            from PIL import Image
            im = Image.open(src_file)
            if max(im.size) > 1600:
                ratio = 1600 / max(im.size)
                im = im.resize((int(im.size[0] * ratio), int(im.size[1] * ratio)), Image.Resampling.LANCZOS)
            
            if src_file.suffix.lower() in (".jpg", ".jpeg"):
                im.convert("RGB").save(dst_file, format="JPEG", quality=82, optimize=True)
            else:
                q = im.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT)
                q.save(dst_file, format="PNG", optimize=True)
            return True
        except Exception:
            dst_file.write_bytes(src_file.read_bytes())
            return True

    def sync_records_images(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """批量處理教學筆記紀錄中所引用的所有圖片。"""
        self.auto_gather_subfolder_assets()

        resolver = get_media_resolver()
        referenced_images: set[str] = set()

        for rec in records:
            cnt = rec.get("content", "") if isinstance(rec, dict) else ""
            if cnt:
                referenced_images.update(resolver.extract_image_references(cnt))

        stats = {
            "total_referenced": len(referenced_images),
            "synced": 0,
            "skipped": 0,
            "healed": 0,
            "failed": 0,
        }

        for img_name in referenced_images:
            src_file = self.src_assets / img_name
            target_file = self.dst_assets / img_name

            # 1. 檢測並自癒
            if not src_file.exists() or src_file.stat().st_size == 0:
                healed = self.heal_missing_image(img_name, self.src_assets)
                if healed and healed.exists():
                    stats["healed"] += 1
                    src_file = healed

            # 2. 同步並壓制
            if src_file.exists() and src_file.is_file():
                if target_file.exists() and target_file.stat().st_size > 0 and target_file.stat().st_mtime >= src_file.stat().st_mtime:
                    stats["skipped"] += 1
                    continue
                success = self.compress_and_copy(src_file, target_file)
                if success:
                    stats["synced"] += 1
                else:
                    stats["failed"] += 1
            else:
                stats["failed"] += 1

        return stats
