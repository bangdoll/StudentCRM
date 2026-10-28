"""Bounded metadata and detail reads after integrating the keyset reader.

The old all-history memory-cache stub bypassed the PR's cloud reader and used
invalid UUIDs. Assert the current HTTP-query boundary and freshness instead.
"""
from unittest.mock import patch
from uuid import UUID
from data_gateway import StudentDataGateway


def test_metadata_pages_are_bounded_and_do_not_hide_fresh_changes(tmp_path):
    gateway = StudentDataGateway(str(tmp_path))
    gateway.backend = 'supabase'
    rows = [{'id': str(UUID(int=i)), 'date':'2026-10-28', 'title':f'Lesson {i}'}
            for i in range(51, 0, -1)]
    with patch.object(gateway, '_teaching_query', side_effect=lambda params: rows) as query:
        first = gateway.list_teaching_records(limit=50)
        assert len(first['items']) == 50 and first['next_cursor']
        rows[0]['title'] = 'Updated metadata'
        second = gateway.list_teaching_records(limit=50)
    assert second['items'][0]['title'] == 'Updated metadata'
    assert query.call_count == 2
    assert all(call.args[0]['limit'] == '51' for call in query.call_args_list)
    assert all('content' not in item and 'raw' not in item for item in second['items'])


def test_metadata_projection_excludes_complete_raw_and_body(tmp_path):
    gateway = StudentDataGateway(str(tmp_path))
    gateway.backend = 'supabase'
    sid = str(UUID(int=9999))
    with patch.object(gateway, '_teaching_query', return_value=[]) as query:
        gateway.list_teaching_records(sid, limit=50)
    query.assert_called_once()
    params = query.call_args.args[0]
    columns = params['select'].split(',')
    assert '*' not in columns and 'raw' not in columns and 'content' not in columns
    assert params['student_id'] == 'eq.' + sid
    assert int(params['limit']) <= 101
    # A projected scalar path is valid; downloading the whole raw JSON is not.
    assert 'path:raw->>path' in columns


def test_single_note_detail_remains_id_scoped_and_bounded(tmp_path):
    gateway = StudentDataGateway(str(tmp_path))
    gateway.backend = 'supabase'
    rid, sid = str(UUID(int=1)), str(UUID(int=9999))
    record = {'id':rid, 'student_id':sid, 'content':'Full Markdown Body'}
    with patch.object(gateway, '_teaching_query', return_value=[record]) as query:
        result = gateway.load_teaching_record_detail(rid, student_id=sid)
    assert result['content'] == 'Full Markdown Body'
    query.assert_called_once()
    params = query.call_args.args[0]
    assert params['id'] == 'eq.' + rid
    assert params['student_id'] == 'eq.' + sid
    assert int(params['limit']) <= 2
    assert '*' not in params['select'].split(',')
