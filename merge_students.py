"""Portable identity checks and read-only merge planning.

The old tests imported an unversioned workspace script. This module deliberately
has no default database, filesystem discovery or write operation. Applying a
merge requires a separate, transactional workflow and is outside this API.
"""
from itertools import combinations

DO_NOT_MERGE_PAIRS = {frozenset(("腦波Annie", "Annie"))}


def _names(student):
    return {str(name).strip().casefold() for name in (student.get("name", ""), *student.get("aliases", [])) if name}


def find_student(identifier, students):
    by_id = [s for s in students if s.get("id") == identifier]
    query = identifier.strip().casefold()
    exact = by_id or [s for s in students if query in _names(s)]
    matches = exact or [s for s in students if query and any(query in name for name in _names(s))]
    if len(matches) > 1:
        raise ValueError("學員身分不明確，請使用 ID")
    return matches[0] if matches else None


def _protected(left, right):
    return frozenset((left, right)) in DO_NOT_MERGE_PAIRS


def scan_duplicate_candidates(students):
    candidates = []
    for left, right in combinations(students, 2):
        if _protected(left.get("name"), right.get("name")):
            continue
        if any(a in b or b in a for a in _names(left) for b in _names(right)):
            target, source = sorted((left, right), key=lambda s: (len(s.get("name", "")), s.get("id", "")))
            candidates.append((target, source, "名稱包含或別名相同，需人工確認"))
    return candidates


def merge_two_students(target, source, *, dry_run=True, students=()):
    """Compatibility name for a plan, never an implicit write to live data."""
    if not dry_run:
        raise ValueError("此介面僅提供 dry-run 計畫，不執行合併")
    if _protected(target, source):
        return False
    target_student = find_student(target, students)
    source_student = find_student(source, students)
    if not target_student or not source_student:
        raise ValueError("必須提供明確的學員資料")
    if target_student["id"] == source_student["id"] or _protected(target_student["name"], source_student["name"]):
        return False
    return {"target_id": target_student["id"], "source_id": source_student["id"], "dry_run": True}
