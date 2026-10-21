import json
import os
import pytest
from pathlib import Path
import sys

from merge_students import (
    scan_duplicate_candidates,
    find_student,
    DO_NOT_MERGE_PAIRS,
    merge_two_students,
)


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


def test_annie_aliases_and_brainwave_distinct_protection():
    """驗證教練指定規則：
    1. 腦波Annie != Annie (不可合併)
    2. 安妮老師 == Annie老師 (別名)
    3. Annie == 安妮 (別名)
    """
    sample_students = [
        {
            "id": "annie-id",
            "name": "Annie",
            "aliases": ["安妮", "安妮老師", "Annie老師"],
            "lessons_count": 83,
        },
        {
            "id": "brainwave-id",
            "name": "腦波Annie",
            "aliases": ["腦波Annie"],
            "lessons_count": 1,
        },
    ]

    # 1. 驗證別名檢索
    assert find_student("Annie", sample_students)["id"] == "annie-id"
    assert find_student("安妮", sample_students)["id"] == "annie-id"
    assert find_student("安妮老師", sample_students)["id"] == "annie-id"
    assert find_student("Annie老師", sample_students)["id"] == "annie-id"

    # 2. 驗證腦波Annie 檢索獨立
    brainwave = find_student("腦波Annie", sample_students)
    assert brainwave["id"] == "brainwave-id"
    assert brainwave["id"] != "annie-id"

    # 3. 驗證防護清單包含此組
    assert frozenset(["腦波Annie", "Annie"]) in DO_NOT_MERGE_PAIRS

    # 4. 驗證 scan 不會將其列為重複候選
    candidates = scan_duplicate_candidates(sample_students)
    assert len(candidates) == 0

    # 5. 驗證 merge 執行時會被防護清單攔截
    assert merge_two_students("腦波Annie", "Annie", dry_run=True) is False


def test_merge_planning_is_explicit_and_never_writes():
    students = [{"id": "a", "name": "範例"}, {"id": "b", "name": "範例舊檔"}]
    before = json.dumps(students, ensure_ascii=False)
    assert merge_two_students("a", "b", students=students) == {"target_id": "a", "source_id": "b", "dry_run": True}
    assert json.dumps(students, ensure_ascii=False) == before
    with pytest.raises(ValueError, match="僅提供 dry-run"):
        merge_two_students("a", "b", students=students, dry_run=False)


def test_ambiguous_partial_name_requires_an_id():
    with pytest.raises(ValueError, match="身分不明確"):
        find_student("範例", [{"id": "a", "name": "範例甲"}, {"id": "b", "name": "範例乙"}])


def test_protected_pair_is_also_rejected_when_identified_by_id():
    students = [{"id": "a", "name": "Annie"}, {"id": "b", "name": "腦波Annie"}]
    assert merge_two_students("a", "b", students=students) is False

