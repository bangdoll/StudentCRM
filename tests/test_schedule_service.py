from datetime import datetime
from schedule_service import get_next_occurrence, get_next_lesson_sort_key, get_document_exceptions


def test_get_next_occurrence_thursday():
    # Wednesday 2026-09-02
    fixed_now = datetime(2026, 9, 2, 10, 0, 0)
    # Thursday 14:00
    res = get_next_occurrence("weekly:3:14:00", now=fixed_now)
    assert res == "2026-09-03（四）14:00"


def test_get_next_occurrence_skips_exception():
    fixed_now = datetime(2026, 9, 2, 10, 0, 0)
    # Thursday 14:00, but 2026-09-03 is exception
    res = get_next_occurrence("weekly:3:14:00", exceptions=["2026-09-03"], now=fixed_now)
    assert res == "2026-09-10（四）14:00"


def test_get_next_lesson_sort_key_ordering():
    fixed_now = datetime(2026, 9, 2, 10, 0, 0)
    s_future = {"next_lesson": "2026-09-03（四）14:00"}
    s_past = {"next_lesson": "2026-08-27（四）14:00"}
    s_tbd = {"next_lesson": "安排中"}

    k_future = get_next_lesson_sort_key(s_future, now=fixed_now)
    k_past = get_next_lesson_sort_key(s_past, now=fixed_now)
    k_tbd = get_next_lesson_sort_key(s_tbd, now=fixed_now)

    assert k_future[0] == 0  # upcoming
    assert k_past[0] == 1    # past
    assert k_tbd[0] == 2     # unscheduled
    assert k_future < k_past < k_tbd
