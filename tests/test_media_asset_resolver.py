"""MediaAssetResolver 深模組單元測試。"""

import os
from unittest.mock import patch

import pytest

from media_asset_resolver import MediaAssetResolver, get_media_resolver


@pytest.fixture(autouse=True)
def reset_media_resolver():
    yield
    get_media_resolver(reload=True)


def test_default_local_resolver():
    """驗證預設本地解析行為。"""
    resolver = MediaAssetResolver()
    assert not resolver.is_cloud_enabled()
    assert resolver.base_url == "/static/teaching_assets"

    # 純檔名
    assert resolver.resolve_url("photo.png") == "/static/teaching_assets/photo.png"
    # assets/ 前綴
    assert resolver.resolve_url("assets/photo.png") == "/static/teaching_assets/photo.png"
    # /assets/ 前綴
    assert resolver.resolve_url("/assets/photo.png") == "/static/teaching_assets/photo.png"
    # /static/teaching_assets/ 前綴
    assert resolver.resolve_url("/static/teaching_assets/photo.png") == "/static/teaching_assets/photo.png"


def test_custom_cdn_base_url():
    """驗證自訂 CDN Base URL。"""
    resolver = MediaAssetResolver(base_url="https://cdn.rd.coach/teaching_assets/")
    assert resolver.is_cloud_enabled()
    assert resolver.base_url == "https://cdn.rd.coach/teaching_assets"
    assert resolver.resolve_url("assets/lesson1.jpg") == "https://cdn.rd.coach/teaching_assets/lesson1.jpg"
    assert resolver.resolve_url("lesson1.jpg") == "https://cdn.rd.coach/teaching_assets/lesson1.jpg"


def test_external_urls_passthrough():
    """驗證外部絕對 URL 或 data URI 不被重複拼裝。"""
    resolver = MediaAssetResolver(base_url="https://cdn.rd.coach/teaching_assets")
    ext_url = "https://images.unsplash.com/photo-12345?w=500"
    assert resolver.resolve_url(ext_url) == ext_url
    data_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA"
    assert resolver.resolve_url(data_uri) == data_uri


def test_env_var_configuration():
    """驗證環境變數動態配置。"""
    with patch.dict(os.environ, {"STUDENTCRM_MEDIA_BASE_URL": "https://media.rd.coach"}, clear=False):
        resolver = MediaAssetResolver()
        assert resolver.is_cloud_enabled()
        assert resolver.base_url == "https://media.rd.coach"
        assert resolver.resolve_url("sample.webp") == "https://media.rd.coach/sample.webp"


def test_supabase_storage_configuration():
    """驗證 Supabase Storage 配置推導。"""
    env_mock = {
        "STUDENTCRM_USE_SUPABASE_STORAGE": "true",
        "SUPABASE_URL": "https://xyzcompany.supabase.co",
        "STUDENTCRM_STORAGE_BUCKET": "teaching_media",
    }
    with patch.dict(os.environ, env_mock, clear=False):
        resolver = MediaAssetResolver()
        assert resolver.is_cloud_enabled()
        assert resolver.base_url == "https://xyzcompany.supabase.co/storage/v1/object/public/teaching_media"
        assert resolver.resolve_url("chart.svg") == "https://xyzcompany.supabase.co/storage/v1/object/public/teaching_media/chart.svg"


def test_transform_markdown_media_local():
    """驗證本地模式下的 Markdown 圖片轉譯。"""
    resolver = MediaAssetResolver()
    raw_md = (
        "# 課堂教學紀錄\n\n"
        "今天討論架構如下：\n"
        "![架構圖](assets/architecture-diagram.png)\n"
        "以及另一張圖：\n"
        "![流程圖](/assets/flow.jpg \"流程概述\")\n"
        "外部參考圖片：\n"
        "![Logo](https://example.com/logo.png)\n"
    )

    transformed = resolver.transform_markdown_media(raw_md)
    assert "![架構圖](/static/teaching_assets/architecture-diagram.png)" in transformed
    assert "![流程圖](/static/teaching_assets/flow.jpg \"流程概述\")" in transformed
    assert "![Logo](https://example.com/logo.png)" in transformed


def test_transform_markdown_media_cloud():
    """驗證雲端模式下的 Markdown 圖片轉譯。"""
    resolver = MediaAssetResolver(base_url="https://cdn.rd.coach/assets")
    raw_md = (
        "筆記圖檔：\n"
        "![筆記](assets/note-01.png)\n"
        "既有靜態路徑：\n"
        "![舊圖](/static/teaching_assets/note-02.png)\n"
    )

    transformed = resolver.transform_markdown_media(raw_md)
    assert "![筆記](https://cdn.rd.coach/assets/note-01.png)" in transformed
    assert "![舊圖](https://cdn.rd.coach/assets/note-02.png)" in transformed


def test_extract_image_references():
    """驗證從 Markdown 萃取圖片引用檔名。"""
    resolver = MediaAssetResolver()
    md = (
        "![圖一](assets/image1.png)\n"
        "重複的：![圖一重複](/assets/image1.png)\n"
        "![圖二](/static/teaching_assets/image2.jpg \"標題\")\n"
        "外部圖：![外部](https://foo.bar/ext.png)\n"
        "純檔名：![圖三](image3.webp)\n"
    )

    images = resolver.extract_image_references(md)
    assert images == ["image1.png", "image2.jpg", "image3.webp"]


def test_singleton_get_media_resolver():
    """驗證全域單例行為。"""
    r1 = get_media_resolver(reload=True)
    r2 = get_media_resolver()
    assert r1 is r2

    r3 = get_media_resolver(base_url="https://temp.cdn", reload=True)
    assert r3.base_url == "https://temp.cdn"


def test_transform_markdown_media_with_spaces():
    """驗證包含空白字元與角括號的教學圖片檔名轉譯與萃取。"""
    resolver = MediaAssetResolver()
    raw_md = (
        "包含空格的貼上圖片：\n"
        "![截圖](assets/Pasted 2025-12-29-22-56-15-57266873-6241-4f05-a0ae-bc6ffee1581a.png)\n"
        "包含空格與標題的 ChatGPT 圖片：\n"
        "![AI生成圖](assets/ChatGPT Image 2026年6月4日.png \"課堂生成成果\")\n"
        "使用角括號語法：\n"
        "![角括號](<assets/my custom photo.jpg> \"自訂圖片\")\n"
    )

    transformed = resolver.transform_markdown_media(raw_md)
    assert "![截圖](/static/teaching_assets/Pasted 2025-12-29-22-56-15-57266873-6241-4f05-a0ae-bc6ffee1581a.png)" in transformed
    assert "![AI生成圖](/static/teaching_assets/ChatGPT Image 2026年6月4日.png \"課堂生成成果\")" in transformed
    assert "![角括號](/static/teaching_assets/my custom photo.jpg \"自訂圖片\")" in transformed

    refs = resolver.extract_image_references(raw_md)
    assert refs == [
        "Pasted 2025-12-29-22-56-15-57266873-6241-4f05-a0ae-bc6ffee1581a.png",
        "ChatGPT Image 2026年6月4日.png",
        "my custom photo.jpg",
    ]


def test_static_teaching_assets_and_fallback_endpoints():
    """驗證在 FastAPI 實例中，/static/teaching_assets 與 /assets 均能雙向存取教學圖片。"""
    from starlette.testclient import TestClient
    from main import app

    client = TestClient(app)

    # 1. 驗證今日新課堂 (1365.蘋果總裁班) 圖片可正常存取 (HTTP 200)
    asset_name = "42F96ECB-23F6-4734-9407-04AB4E718B1A-2970c806-1c76-41c9-8ee0-fea967d459ab.png"
    r1 = client.get(f"/static/teaching_assets/{asset_name}")
    assert r1.status_code == 200
    assert r1.headers["content-type"].startswith("image/")

    r2 = client.get(f"/assets/{asset_name}")
    assert r2.status_code == 200
    assert r2.headers["content-type"].startswith("image/")

    # 2. 驗證含空白字元的真實課堂圖片可正常存取
    space_img = "Pasted 2025-12-29-22-56-15-57266873-6241-4f05-a0ae-bc6ffee1581a.png"
    r3 = client.get(f"/static/teaching_assets/{space_img}")
    assert r3.status_code == 200
    assert r3.headers["content-type"].startswith("image/")


