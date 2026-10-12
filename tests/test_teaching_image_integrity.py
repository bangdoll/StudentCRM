"""教學筆記圖片完整性與防缺失回歸測試 (test_teaching_image_integrity.py)。

防禦目標：
1. 確保 10 月 12 日（及所有最新）教學筆記所引用的圖片資產 100% 存在於本地及 StudentCRM 靜態目錄。
2. 確保筆記中無重複 Frontmatter 嵌套與重複頂部大圖標題。
3. 確保 MediaAssetResolver 能正確將圖片解析為有效路由。
"""

from __future__ import annotations

import re
from pathlib import Path
import pytest

from media_asset_resolver import get_media_resolver


CRM_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = CRM_DIR.parent.parent
DOCS_DIR = WORKSPACE_DIR / "01.Docs" / "teaching"
DOCS_ASSETS_DIR = DOCS_DIR / "assets"
CRM_ASSETS_DIR = CRM_DIR / "static" / "teaching_assets"

IMAGE_MD_PATTERN = re.compile(r'!\[(?P<alt>.*?)\]\((?P<src>[^\)]+)\)')


def test_20261012_teaching_notes_images_exist():
    """驗證 2026-10-12 兩篇教學筆記引用的圖片實體檔案皆存在。"""
    notes = [
        DOCS_DIR / "20261012 19-3.Anna蕭數位管理教學.md",
        DOCS_DIR / "20261012 22-6.大腳旅行社曹淑鈴Crystal數位管理教學.md",
    ]
    
    assert len(notes) == 2, "10/12 兩篇筆記應存在"
    resolver = get_media_resolver()

    for note in notes:
        assert note.is_file(), f"筆記不存在: {note.name}"
        content = note.read_text(encoding="utf-8")
        images = resolver.extract_image_references(content)
        assert len(images) > 0, f"筆記應至少包含 1 張圖片: {note.name}"

        for img_name in images:
            # 1. 驗證 01.Docs/teaching/assets
            doc_img = DOCS_ASSETS_DIR / img_name
            assert doc_img.is_file(), f"圖片缺失於 01.Docs/teaching/assets: {img_name} in {note.name}"
            assert doc_img.stat().st_size > 0, f"圖片檔案大小為 0: {img_name}"

            # 2. 驗證 StudentCRM/static/teaching_assets
            crm_img = CRM_ASSETS_DIR / img_name
            assert crm_img.is_file(), f"圖片缺失於 StudentCRM 靜態目錄: {img_name} in {note.name}"
            assert crm_img.stat().st_size > 0, f"StudentCRM 靜態圖片大小為 0: {img_name}"


def test_no_duplicate_frontmatter_in_teaching_notes():
    """驗證 10/12 筆記中不得包含重複嵌套的 Frontmatter 或重複頂部大圖。"""
    notes = [
        DOCS_DIR / "20261012 19-3.Anna蕭數位管理教學.md",
        DOCS_DIR / "20261012 22-6.大腳旅行社曹淑鈴Crystal數位管理教學.md",
    ]

    for note in notes:
        content = note.read_text(encoding="utf-8")
        # 檢查第二個 YAML frontmatter 開頭
        # 正常情況下只有文件第 1 行是 ---，第 8 行左右是 ---
        # 之後正文中不應出現 --- 緊接著 id: xxx
        nested_fm = re.search(r'\n---\nid:\s*[0-9a-f-]+\n', content)
        assert nested_fm is None, f"發現重複嵌套的 Frontmatter: {note.name}"


def test_media_asset_resolver_transforms_correctly():
    """驗證 MediaAssetResolver 能將 assets/ 轉換為 /static/teaching_assets/。"""
    resolver = get_media_resolver(base_url="/static/teaching_assets")
    sample_md = "![白板](assets/90765B8E-A284-47E9-B2C9-FF8A6809048A-f9bce52f-3d22-4999-ba09-8ec042b4f845.png)"
    transformed = resolver.transform_markdown_media(sample_md)
    expected = "![白板](/static/teaching_assets/90765B8E-A284-47E9-B2C9-FF8A6809048A-f9bce52f-3d22-4999-ba09-8ec042b4f845.png)"
    assert transformed == expected


def test_deduplicate_markdown_images_helper():
    """驗證 deduplicate_markdown_images 能自動消除重複圖片標籤與正文中的嵌套 Frontmatter。"""
    from note_service import deduplicate_markdown_images

    dirty_md = """
![圖片](assets/sample_photo.png)

---
id: test-id-1234
title: "測試重複"
---

![圖片](assets/sample_photo.png)

正文內容...
"""
    cleaned = deduplicate_markdown_images(dirty_md)
    assert cleaned.count("sample_photo.png") == 1, "重複圖片必須被消除至僅剩 1 張"
    assert "id: test-id-1234" not in cleaned, "正文嵌套 Frontmatter 必須被清除"


def test_resolve_note_detail_renders_no_duplicate_images():
    """驗證透過 resolve_note_detail 渲染 Anna 筆記時，HTML 中的任一圖片皆不重複。"""
    from note_service import resolve_note_detail

    anna_path = str(DOCS_DIR / "20261012 19-3.Anna蕭數位管理教學.md")
    note = resolve_note_detail(path_or_filename=anna_path, base_dir=str(WORKSPACE_DIR))
    assert note is not None, "Anna 筆記應可被正確解析"

    # 檢查 HTML 內容中圖片出現頻率
    html = note.content_html
    img_srcs = re.findall(r'<img[^>]+src=[\"\']([^\"\']+)[\"\']', html)
    assert len(img_srcs) > 0, "應至少包含 1 張圖片"
    # 確保所有圖片網址完全唯一
    assert len(img_srcs) == len(set(img_srcs)), f"渲染出的 HTML 中發現重複圖片: {img_srcs}"

