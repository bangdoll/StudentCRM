import json
import os
import pytest
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from merge_students import scan_duplicate_candidates, find_student


def test_find_student_by_id_and_name_and_alias():
    sample_students = [
        {"id": "id-1", "name": "陳海陸", "aliases": ["海陸哥"]},
        {"id": "id-2", "name": "陳海陸 20 4", "aliases": []},
    ]
    assert find_student("id-1", sample_students)["name"] == "陳海陸"
    assert find_student("陳海陸", sample_students)["id"] == "id-1"
    assert find_student("海陸哥", sample_students)["id"] == "id-1"
    assert find_student("20 4", sample_students)["id"] == "id-2"


def test_scan_duplicate_candidates_detects_pairs():
    sample_students = [
        {"id": "id-1", "name": "陳海陸", "aliases": ["海陸哥"], "lessons_count": 25},
        {"id": "id-2", "name": "陳海陸 20 4", "aliases": [], "lessons_count": 25},
        {"id": "id-3", "name": "Charlotte", "aliases": [], "lessons_count": 96},
    ]
    candidates = scan_duplicate_candidates(sample_students)
    assert len(candidates) == 1
    target, source, reason = candidates[0]
    assert target["name"] == "陳海陸"
    assert source["name"] == "陳海陸 20 4"
    assert "名稱包含" in reason
