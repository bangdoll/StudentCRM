"""Read-only checks for private workspace assets, separate from portable fixtures.

Run explicitly before publishing teaching assets; absence is a failure, never a
skip. This module neither discovers private folders nor writes student data.
"""
from pathlib import Path
import argparse
import json
import re

from media_asset_resolver import MediaAssetResolver

HANDBOOK_NAME = "One_Person_Company_Digital_Management_Handbook_Curriculum.md"
REQUIRED_HANDBOOK_SECTIONS = (
    "一人公司的『四層數位齒輪』", "30 個標準化實戰教學單元",
    "90 天一人公司實踐節奏表",
)
OCTOBER_NOTES = (
    "20261012 19-3.Anna蕭數位管理教學.md",
    "20261012 22-6.大腳旅行社曹淑鈴Crystal數位管理教學.md",
)


def audit_handbook(path: Path) -> list[str]:
    if not path.is_file():
        return ["missing handbook"]
    content = path.read_text(encoding="utf-8")
    expected = (*REQUIRED_HANDBOOK_SECTIONS, *(f"單元 {n:02}" for n in range(1, 31)))
    return [f"missing handbook section: {text}" for text in expected if text not in content]


def audit_teaching_assets(teaching_dir: Path, static_dir: Path, *, minimum_notes=1220, required_notes=OCTOBER_NOTES) -> dict:
    issues = []
    notes = list(teaching_dir.glob("*.md"))
    if not teaching_dir.is_dir():
        issues.append("missing teaching directory")
    if len(notes) < minimum_notes:
        issues.append(f"teaching inventory below {minimum_notes}: {len(notes)}")
    resolver = MediaAssetResolver(base_url="/static/teaching_assets")
    for name in required_notes:
        path = teaching_dir / name
        if not path.is_file():
            issues.append(f"missing required note: {name}")
            continue
        content = path.read_text(encoding="utf-8")
        images = resolver.extract_image_references(content)
        if not images:
            issues.append(f"note has no images: {name}")
        if re.search(r'\n---\nid:\s*[0-9a-f-]+\n', content):
            issues.append(f"nested frontmatter: {name}")
        for image in images:
            for parent in (teaching_dir / "assets", static_dir):
                image_path = parent / image
                if not image_path.is_file() or image_path.stat().st_size == 0:
                    issues.append(f"missing or empty image: {image}")
    return {"note_count": len(notes), "minimum_notes": minimum_notes, "issues": issues, "success": not issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--crm-dir", type=Path, required=True)
    args = parser.parse_args()
    result = audit_teaching_assets(args.workspace / "01.Docs/teaching", args.crm_dir / "static/teaching_assets")
    result["issues"].extend(audit_handbook(args.workspace / "01.Docs/products" / HANDBOOK_NAME))
    result["success"] = not result["issues"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
