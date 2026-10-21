"""Smoke-test the installed wheel from outside the source checkout.

Run with the fresh wheel environment's Python -I. A missing resource or import
must fail rather than silently importing the editable source tree.
"""
import importlib.metadata
import importlib.util
import os
from pathlib import Path
import sys
import tempfile


def main():
    installed_main = Path(importlib.util.find_spec("main").origin).resolve()
    assert installed_main.is_relative_to(Path(sys.prefix).resolve()), installed_main
    with tempfile.TemporaryDirectory(prefix="studentcrm-wheel-") as directory:
        os.environ["STUDENTCRM_CACHE_DIR"] = directory
        os.environ["OPEN_CLAW_BASE_DIR"] = str(installed_main.parent)
        os.environ["STUDENTCRM_DATA_BACKEND"] = "local"
        for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
            os.environ[key] = ""
        from main import app
        from data_gateway import StudentDataGateway
        from fastapi.testclient import TestClient
        from teaching_reads import TeachingReads
        from asset_audit import audit_teaching_assets
        from merge_students import find_student
        from routers.student import router
        from schemas.student import StudentProfile

        gateway = StudentDataGateway(str(installed_main.parent))
        assert len(gateway.load_students()) >= 64
        assert len(gateway.load_all_teaching_records()) >= 698
        with TestClient(app) as client:
            page = client.get("/cases")
            assert page.status_code == 200
            assert "100+ 堂真實實戰見證庫" in page.text
            cases = client.get("/api/cases")
            assert cases.status_code == 200 and len(cases.json()) == 100
            for asset in ("style.css", "icon-192.png"):
                response = client.get(f"/static/{asset}")
                assert response.status_code == 200 and response.content
            manifest = client.get("/site.webmanifest")
            assert manifest.status_code == 200, f"Manifest status: {manifest.status_code}"
            assert manifest.headers["content-type"].startswith("application/manifest+json")
            document = manifest.json()
            assert document["display"] == "standalone" and document["start_url"] == "/"
            assert document["icons"]
            head = client.head("/site.webmanifest")
            assert head.status_code == 200 and not head.content
            assert head.headers["content-length"] == str(len(manifest.content))
            for icon in document["icons"]:
                assert icon["src"].startswith("/static/")
                image = client.get(icon["src"])
                assert image.status_code == 200 and image.content
                assert image.headers["content-type"].startswith("image/")
            params = {"path": "20260813 1359.蘋果總裁班.md"}
            assert client.get("/note", params=params).status_code == 403
            from auth_service import SESSION_COOKIE_NAME, get_session_token
            client.cookies.set(SESSION_COOKIE_NAME, get_session_token())
            response = client.get("/note", params=params)
            assert response.status_code == 200
            assert "1359.蘋果總裁班" in response.text
        print(f"Installed studentcrm {importlib.metadata.version('studentcrm')}: imports, HTML, static assets, PWA manifest GET/HEAD/icons, bundled data and legacy note link passed")


if __name__ == "__main__":
    main()
