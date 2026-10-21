"""Cloud contracts: no local student files, HTTP boundary only."""
import json
import re
import uuid
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
import pytest
from data_gateway import StudentDataGateway


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    monkeypatch.setenv('STUDENTCRM_DATA_BACKEND', 'supabase')
    monkeypatch.setenv('SUPABASE_URL', 'https://fixture.invalid')
    monkeypatch.setenv('SUPABASE_ANON_KEY', 'fixture')
    monkeypatch.setenv('STUDENTCRM_CACHE_DIR', str(tmp_path / 'cache'))
    gateway = StudentDataGateway(str(tmp_path))
    gateway.teaching_records_file = str(tmp_path / 'absent.json')
    return gateway


def test_cloud_list_has_no_body_and_returns_a_next_page(cloud):
    rows = [{'id': str(uuid.UUID(int=i)), 'student_id': str(uuid.UUID(int=9999)),
             'date': '2026-10-01', 'title': f'Lesson {i}'} for i in range(1, 52)]
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return json.dumps(rows).encode()
    with patch('data_gateway.urlopen', return_value=Response()):
        page = cloud.list_teaching_records(limit=50)
    assert len(page['items']) == 50
    assert page['next_cursor']
    assert all('content' not in item and 'raw' not in item for item in page['items'])


def test_detail_supports_old_path_without_trying_uuid_column(cloud):
    record = {'id': str(uuid.UUID(int=1)), 'student_id': str(uuid.UUID(int=9999)), 'title': 'Old note',
              'path': '/01.Docs/teaching/中文 note.md', 'content': 'body only keyword'}
    seen = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return json.dumps([record]).encode()
    def request(req, **kwargs):
        params = parse_qs(urlsplit(req.full_url).query)
        seen.append(params)
        assert not params.get('id',[''])[0].startswith('eq.')  # legacy paths cannot be UUID predicates
        if params.get('id',[''])[0].startswith('neq.'):
            class Empty(Response):
                def read(self): return b'[]'
            return Empty()
        return Response()
    with patch('data_gateway.urlopen', side_effect=request):
        assert cloud.load_teaching_record_detail(record['path'])['content'] == 'body only keyword'
    assert seen


def split_terms(text):
    terms, start, depth, quoted, escaped = [], 0, 0, False, False
    for i, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == '\\':
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif not quoted:
            if char == '(': depth += 1
            elif char == ')': depth -= 1
            elif char == ',' and depth == 0:
                terms.append(text[start:i]); start = i + 1
    return terms + [text[start:]]


def value(row, field):
    if '->>' in field:
        a, b = field.split('->>')
        return (row.get(a) or {}).get(b)
    return row.get(field)


def matches(row, expr):
    if expr.startswith('or(') or expr.startswith('and('):
        op, inner = expr.split('(', 1)
        checks = [matches(row, e) for e in split_terms(inner[:-1])]
        return any(checks) if op == 'or' else all(checks)
    field, op, arg = expr.split('.', 2)
    current = value(row, field)
    if op == 'not': return current is not None  # not.is.null
    if op == 'is': return current is None
    if op == 'in': return str(current) in arg.strip('()').split(',')
    if arg.startswith('"'): arg = json.loads(arg)
    if op == 'ilike':
        # PostgREST maps every '*' to '%' before PostgreSQL interprets LIKE.
        # Keep SQL's escaped %, _ and backslash behavior instead of turning
        # the entire predicate into a Python substring assertion.
        pattern, escaped = '', False
        for char in arg.replace('*', '%'):
            if escaped:
                pattern += re.escape(char)
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '%':
                pattern += '.*'
            elif char == '_':
                pattern += '.'
            else:
                pattern += re.escape(char)
        return current is not None and re.fullmatch(pattern, str(current), re.I | re.S) is not None
    if op == 'imatch':
        return current is not None and re.search(arg, str(current), re.I) is not None
    if op == 'eq': return str(current) == arg
    if op == 'neq': return str(current) != arg
    if current is None: return False
    return str(current) < arg if op == 'lt' else str(current) > arg


class Postgrest:
    """HTTP contract simulator, validates against the observed production schema."""
    columns = {'id','student_id','card_id','title','date','content','source','created_at','student_name','lesson_num','lesson_sub','created','edited','raw','updated_at'}
    def __init__(self, rows):
        self.rows, self.calls, self.error = rows, [], None
        self.tables = {}
        self.row_cap = 1000
        self.students = [{'id': str(uuid.UUID(int=9999)), 'name': 'Fixture A', 'public_token': 'fixture-a', 'status': 'active', 'latest_date': '2026-10-20', 'lessons_count': 12},
                         {'id': str(uuid.UUID(int=9998)), 'name': 'Fixture B', 'public_token': 'fixture-b', 'status': 'active', 'latest_date': '2026-10-20', 'lessons_count': 8}]
    def __call__(self, req, **kwargs):
        from urllib.error import HTTPError
        url = urlsplit(req.full_url)
        table = url.path.rsplit('/', 1)[-1]
        params = {k:v[0] for k,v in parse_qs(url.query).items()}
        self.calls.append((table, params))
        if self.error:
            raise HTTPError(req.full_url, self.error, 'Fixture failure', {}, None)
        rows = self.rows if table == 'teaching_records' else self.students if table == 'students' else self.tables.get(table, [])
        if table == 'teaching_records':
            fields = params.get('select', '*').split(',')
            assert '*' not in fields, 'No full cloud body history read'
            for field in fields:
                assert field.split(':')[-1].split('->>')[0] in self.columns, f'Unknown field {field}'
            assert 0 < int(params['limit']) <= 101
            for key, expr in params.items():
                if key in {'select','order','limit'}: continue
                predicate = key + expr if key in ('and', 'or') else key + '.' + expr
                rows = [r for r in rows if matches(r, predicate)]
            ascending = params.get('order','').startswith('date.asc')
            rows = sorted(rows, key=lambda r:(r.get('date') is not None, r.get('date') or '',r['id']), reverse=not ascending)[:min(int(params['limit']), self.row_cap)]
            projected = []
            for row in rows:
                projected.append({field.split(':')[0] if ':' in field else field: value(row,field.split(':')[-1]) for field in fields})
            rows = projected
        body = json.dumps(rows, ensure_ascii=False).encode()
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return body
        return Response()


@pytest.fixture
def web_cloud(cloud, monkeypatch, tmp_path):
    import main
    import media_asset_resolver
    monkeypatch.setattr(media_asset_resolver, "_DEFAULT_RESOLVER", None)
    from data_gateway import clear_gateway_memory_cache
    from fastapi.testclient import TestClient
    from auth_service import SESSION_COOKIE_NAME, get_session_token
    clear_gateway_memory_cache()
    cloud.students_file = str(tmp_path / 'no-students.json')
    cloud.app_dir = str(tmp_path)
    cloud.radar_file = str(tmp_path / 'radar.json')
    cloud.radar_cache_file = str(tmp_path / 'radar-cache.json')
    monkeypatch.setattr(main, 'BASE_DIR', str(tmp_path))
    import digital_management_service as dm
    monkeypatch.setattr(dm, 'APP_DIR', str(tmp_path))
    monkeypatch.setattr(dm, 'DIGITAL_MANAGEMENT_CALENDAR_CACHE', str(tmp_path / 'no-calendar.json'))
    monkeypatch.setattr(main, 'student_gateway', cloud)
    monkeypatch.setattr(main, '_APPLE_PROGRAM_CACHE', {'timestamp':0.,'data':None})
    rows = [{'id': str(uuid.UUID(int=i)), 'student_id': str(uuid.UUID(int=9999 if i % 2 else 9998)),
             'student_name': 'Fixture A' if i % 2 else 'Fixture B', 'title': f'Lesson {i}',
             'date': '2026-10-20', 'lesson_num': i, 'content': f'正文唯一詞{i} AI OS 微習慣：每天記錄',
             'raw': {'path': f'/01.Docs/teaching/中文 {i}.md','filename':f'中文 {i}.md','preview':'short preview'}} for i in range(1, 122)]
    remote = Postgrest(rows)
    monkeypatch.setattr('data_gateway.urlopen', remote)
    # A missing source must never be silently replaced by bundled teaching JSON.
    original_read = cloud._read_json
    def read(path):
        assert path != cloud.teaching_records_file, 'Cloud attempted local teaching fallback'
        return original_read(path)
    monkeypatch.setattr(cloud, '_read_json', read)
    client = TestClient(main.app)
    client.cookies.set(SESSION_COOKIE_NAME, get_session_token())
    yield client, remote, cloud
    clear_gateway_memory_cache()


def test_keyset_paging_over_platform_cap_and_null_dates(web_cloud):
    _, remote, gateway = web_cloud
    remote.rows = [{'id':str(uuid.UUID(int=i)), 'student_id':str(uuid.UUID(int=9999)), 'date': None if i % 7 == 0 else '' if i % 9 == 0 else '2026-10-20', 'title':f'row {i}'} for i in range(1, 1202)]
    cursor, seen = None, []
    while True:
        page = gateway.list_teaching_records(cursor=cursor, limit=100)
        seen += [r['id'] for r in page['items']]
        cursor = page['next_cursor']
        if not cursor: break
    assert len(seen) == len(set(seen)) == 1201
    with pytest.raises(ValueError): gateway.list_teaching_records(cursor='not-a-cursor')


def test_cloud_note_old_link_body_and_neighbors(web_cloud):
    client, remote, _ = web_cloud
    response = client.get('/note', params={'path':'/01.Docs/teaching/中文 61.md'})
    assert response.status_code == 200
    assert '正文唯一詞61' in response.text
    assert '中文%2063' in response.text or '中文 63' in response.text or '中文+63' in response.text
    assert response.headers['cache-control'] == 'private, no-store'
    response = client.get('/open_file', params={'path':'中文 61.md'})
    assert response.status_code == 200 and '正文唯一詞61' in response.text
    assert all('content' not in p['select'].split(',') or int(p['limit']) <= 2 for t,p in remote.calls if t=='teaching_records')


def test_body_only_search_is_preserved(web_cloud):
    client, _, _ = web_cloud
    response = client.get('/search', params={'q':'正文唯一詞61'})
    assert response.status_code == 200
    assert 'Lesson 61' in response.text


def test_student_cannot_read_other_student_body(web_cloud):
    client, _, _ = web_cloud
    client.cookies.clear()
    response = client.get('/note', params={'path':'/01.Docs/teaching/中文 62.md','token':'fixture-a'},headers={'X-Test-Auth':'1'})
    assert response.status_code == 404
    assert '正文唯一詞62' not in response.text
    response = client.get('/note', params={'path':'/01.Docs/teaching/中文 61.md','token':'fixture-a'},headers={'X-Test-Auth':'1'})
    assert response.status_code == 200 and '正文唯一詞61' in response.text


def test_body_update_and_delete_visible_without_local_cache(web_cloud):
    client, remote, _ = web_cloud
    identifier = remote.rows[-1]['id']
    assert '正文唯一詞121' in client.get('/note',params={'path':identifier}).text
    remote.rows[-1]['content'] = 'REVISED_BODY'
    assert 'REVISED_BODY' in client.get('/note',params={'path':identifier}).text
    remote.rows.pop()
    assert client.get('/note',params={'path':identifier}).status_code == 404


def test_cloud_failures_are_visible_and_never_expand_reads(web_cloud):
    client, remote, _ = web_cloud
    remote.error = 402
    response = client.get('/api/teaching-records')
    assert response.status_code == 503
    assert len([p for t,p in remote.calls if t=='teaching_records']) == 1


def test_hub_and_student_pagination_load_only_latest_body(web_cloud):
    client, remote, _ = web_cloud
    response = client.get('/my/fixture-a')
    assert response.status_code == 200 and '較早的紀錄' in response.text
    bodies = [p for t,p in remote.calls if t=='teaching_records' and 'content' in p['select'].split(',')]
    assert all(p.get('student_id') and int(p['limit']) == 1 for p in bodies)
    response = client.get('/student/' + str(uuid.UUID(int=9999)))
    assert response.status_code == 200 and '較早的紀錄' in response.text


def test_radar_keeps_recent_body_analysis_without_loading_history(web_cloud):
    client, remote, _ = web_cloud
    response = client.get('/radar')
    assert response.status_code == 200
    assert 'Fixture A' in response.text and 'AI OS' in response.text
    bodies = [p for t,p in remote.calls if t=='teaching_records' and 'content' in p['select'].split(',')]
    assert bodies and all(p.get('id','').startswith('in.(') for p in bodies)
    ids = [i for p in bodies for i in p['id'][4:-1].split(',')]
    assert len(ids) == 6


def test_api_page_is_bounded_and_cursor_is_bound_to_filter(web_cloud):
    client, _, gateway = web_cloud
    response = client.get('/api/teaching-records',params={'limit':50})
    assert response.status_code == 200
    page = response.json()
    assert len(page['items']) == 50 and page['has_more']
    assert not any('content' in r or 'raw' in r for r in page['items'])
    assert client.get('/api/teaching-records',params={'limit':101}).status_code == 400
    with pytest.raises(ValueError): gateway.list_teaching_records(student_id=str(uuid.UUID(int=9999)),cursor=page['next_cursor'])


def test_search_literal_special_characters_and_legacy_body(web_cloud):
    client, remote, _ = web_cloud
    remote.rows[-1]['content'] = ''
    remote.rows[-1]['raw']['content'] = "唯一%_字 O'Reilly (繁中)"
    for q in ['唯一%_字', "O'Reilly", '(繁中)']:
        result = client.get('/search',params={'q':q})
        assert result.status_code == 200 and 'Lesson 121' in result.text
    result = client.get('/note', params={'path':remote.rows[-1]['id']})
    assert result.status_code == 200 and '唯一%_字' in result.text


def test_unknown_or_ambiguous_old_link_is_not_arbitrary(web_cloud):
    client, remote, _ = web_cloud
    remote.rows[-1]['raw']['filename'] = remote.rows[0]['raw']['filename']
    assert client.get('/note',params={'path':remote.rows[0]['raw']['filename']}).status_code == 503
    assert client.get('/note',params={'path':'/etc/passwd'}).status_code == 404


def test_digital_profile_and_api_pagination_have_no_body(web_cloud):
    client, remote, _ = web_cloud
    sid = str(uuid.UUID(int=9999))
    result = client.get('/api/digital-management/students/' + sid)
    assert result.status_code == 200
    profile = result.json()['student']
    assert len(profile['notes']) == 50 and profile['next_cursor']
    assert all('content' not in note and 'raw' not in note for note in profile['notes'])
    next_page = client.get('/api/digital-management/students/' + sid,params={'cursor':profile['next_cursor']})
    assert len(next_page.json()['student']['notes']) == 11
    assert not any('content' in p['select'].split(',') for t,p in remote.calls if t=='teaching_records')
    response = client.get('/digital-management/student/' + sid)
    assert response.status_code == 200 and '較早的紀錄' in response.text
    assert '/note?path=' in response.text


def test_student_api_is_not_public(web_cloud):
    client, _, _ = web_cloud
    client.cookies.clear()
    assert client.get('/api/teaching-records', headers={'X-Test-Auth':'1'}).status_code == 401


def test_record_reassignment_revokes_old_student_access(web_cloud):
    client, remote, _ = web_cloud
    identifier = remote.rows[-1]['id']
    client.cookies.clear()
    params = {'path':identifier,'token':'fixture-a'}
    assert client.get('/note',params=params,headers={'X-Test-Auth':'1'}).status_code == 200
    remote.rows[-1]['student_id'] = str(uuid.UUID(int=9998))
    assert client.get('/note',params=params,headers={'X-Test-Auth':'1'}).status_code == 404


def test_current_note_does_not_transfer_duplicate_raw_body(web_cloud):
    client, remote, _ = web_cloud
    assert client.get('/note',params={'path':remote.rows[-1]['id']}).status_code == 200
    assert not any('legacy_content' in p['select'] for t,p in remote.calls if t=='teaching_records')


@pytest.mark.parametrize('status',[402,403,500])
def test_failure_after_success_cannot_return_cached_success(web_cloud,status):
    client, remote, _ = web_cloud
    assert client.get('/api/teaching-records').status_code == 200
    remote.error = status
    assert client.get('/api/teaching-records').status_code == 503


def test_empty_list_and_malformed_json(web_cloud,monkeypatch):
    client, remote, _ = web_cloud
    remote.rows.clear()
    page = client.get('/api/teaching-records').json()
    assert page == {'items':[],'next_cursor':None,'has_more':False}
    class BadResponse:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self): return b'not JSON'
    monkeypatch.setattr('data_gateway.urlopen',lambda *a,**kw:BadResponse())
    assert client.get('/api/teaching-records').status_code == 503


def test_class_note_legacy_link_remains_available(web_cloud):
    client, remote, _ = web_cloud
    remote.students.append({'id':str(uuid.UUID(int=9997)),'name':'蘋果總裁班','public_token':'fixture-class'})
    remote.tables['apple_programs'] = [{'id':'apple-ceo','name':'蘋果總裁班','raw':{'teaching_notes':[{'path':'/class.md','filename':'class.md','title':'班務筆記','date':'2026-10-20','content':'CLASS_NOTE_BODY'}]}}]
    client.cookies.clear()
    result = client.get('/note',params={'path':'/class.md','token':'fixture-class'},headers={'X-Test-Auth':'1'})
    assert result.status_code == 200 and 'CLASS_NOTE_BODY' in result.text


def test_same_date_neighbors_are_deterministic_and_scoped(web_cloud):
    client, remote, _ = web_cloud
    response = client.get('/note',params={'path':str(uuid.UUID(int=61))})
    assert response.status_code == 200
    assert '中文%2063' in response.text or '中文 63' in response.text or '中文+63' in response.text
    assert '中文%2059' in response.text or '中文 59' in response.text or '中文+59' in response.text
    assert '正文唯一詞60' not in response.text and '正文唯一詞62' not in response.text


def test_api_list_does_not_grow_with_body_size(web_cloud):
    client, remote, _ = web_cloud
    for row in remote.rows:
        row['content'] = '超大正文' * 50000
        row['raw']['content'] = row['content']
    response = client.get('/api/teaching-records')
    assert response.status_code == 200 and len(response.content) < 100 * 1024
    assert '超大正文' not in response.text


def test_paging_survives_a_server_row_cap_smaller_than_page(web_cloud):
    _, remote, gateway = web_cloud
    remote.row_cap = 7
    cursor, ids = None, []
    while True:
        page = gateway.list_teaching_records(cursor=cursor,limit=50)
        ids += [r['id'] for r in page['items']]
        cursor = page['next_cursor']
        if not cursor: break
    assert len(ids) == len(set(ids)) == 121


def test_recent_and_radar_reads_survive_one_row_server_cap(web_cloud):
    _, remote, gateway = web_cloud
    remote.row_cap = 1
    sid = str(uuid.UUID(int=9999))
    assert [r['lesson_num'] for r in gateway.load_recent_teaching_records(sid)] == [121,119,117]
    records = gateway.load_radar_teaching_records([s['id'] for s in remote.students])
    assert {r['lesson_num'] for r in records} == {121,120,119,118,117,116}


def test_nullable_title_remains_readable(web_cloud):
    client, remote, _ = web_cloud
    remote.rows[-1]['title'] = None
    response = client.get('/note',params={'path':remote.rows[-1]['id']})
    assert response.status_code == 200 and '正文唯一詞121' in response.text


def test_local_api_metadata_cursor_without_persisted_ids(cloud,tmp_path):
    cloud.backend = 'local'
    path = tmp_path / 'local-fixture.json'
    path.write_text(json.dumps({'records':[{'student_id':'offline-student','date':'2026-10-20','path':f'/fixture/{i}.md','title':str(i),'content':'offline body'} for i in range(60)]}))
    cloud.teaching_records_file = str(path)
    first = cloud.list_teaching_records(limit=50)
    second = cloud.list_teaching_records(limit=50,cursor=first['next_cursor'])
    assert len(first['items']) == 50 and len(second['items']) == 10
    assert cloud.load_teaching_record_detail(first['items'][0]['id'])['content'] == 'offline body'


def test_cloud_prediction_uses_recent_bodies_without_local_files(web_cloud):
    from datetime import datetime, timedelta
    from prediction_service import clear_features_cache
    client, remote, gateway = web_cloud
    sid = remote.students[0]['id']
    latest = (datetime.now() - timedelta(days=21)).strftime('%Y-%m-%d')
    remote.students[0]['latest_date'] = latest
    remote.rows = [dict(remote.rows[index], student_id=sid, date=latest, content='課' * 1400) for index in range(3)]
    clear_features_cache()
    result = client.get('/api/students/' + sid, headers={'X-Test-Auth': '1'})
    assert result.status_code == 200
    assert result.json()['features']['average_word_count'] == 1400
    assert result.json()['features']['lessons_reviewed'] == 3
    assert result.json()['prediction']['status'] == '冰凍期 (需關心)'
    page = client.get('/student/' + sid, headers={'X-Test-Auth': '1'})
    assert page.status_code == 200 and '1400 字' in page.text and '冰凍期' in page.text
    bodies = [params for table, params in remote.calls if table == 'teaching_records' and 'content' in params['select'].split(',')]
    assert bodies and all(params.get('student_id') == 'eq.' + sid and int(params['limit']) <= 3 for params in bodies)


def test_cloud_prediction_ignores_stale_files_and_cache_and_reports_failure(web_cloud, tmp_path):
    from datetime import datetime, timedelta
    client, remote, _ = web_cloud
    sid = remote.students[0]['id']
    remote.students[0]['latest_date'] = (datetime.now() - timedelta(days=21)).strftime('%Y-%m-%d')
    stale = tmp_path / 'stale.md'
    stale.write_text('stale local body ' * 1000)
    remote.rows = [{**remote.rows[0], 'content': '課' * 1400,
                    'raw': {'path': str(stale), 'filename': stale.name}}]
    first = client.get('/api/students/' + sid).json()
    assert first['features']['average_word_count'] == 1400
    remote.rows[0]['content'] = '課' * 80
    second = client.get('/api/students/' + sid).json()
    assert second['features']['average_word_count'] == 80
    assert second['prediction']['status'] == '高流失風險'
    remote.rows.clear()
    assert client.get('/api/students/' + sid).json()['features']['lessons_reviewed'] == 0
    remote.error = 402
    assert client.get('/api/students/' + sid).status_code == 503


def test_cloud_prediction_keeps_date_inference_without_reading_local_files(web_cloud):
    from datetime import datetime, timedelta
    client, remote, _ = web_cloud
    sid = remote.students[0]['id']
    latest = (datetime.now() - timedelta(days=21)).strftime('%Y-%m-%d')
    remote.students[0]['latest_date'] = None
    remote.rows = [{**remote.rows[0], 'date': latest, 'content': '課' * 1400,
                    'raw': {'path': '/absent/' + latest.replace('-', '') + ' lesson.md'}}]
    result = client.get('/api/students/' + sid)
    assert result.status_code == 200
    assert result.json()['features']['days_since_last_lesson'] == 21
    assert result.json()['prediction']['status'] == '冰凍期 (需關心)'


from search_contract_cases import LITERAL_SEARCH_CASES


@pytest.mark.parametrize('query,body', LITERAL_SEARCH_CASES)
def test_literal_search_distinguishes_symbols_and_returns_metadata(web_cloud, query, body):
    client, remote, _ = web_cloud
    sid = remote.students[0]['id']
    remote.rows = [
        {'id': str(uuid.UUID(int=index + 1)), 'student_id': sid,
         'title': f'SymbolResult-{index:02}', 'date': '2026-10-20', 'content': value,
         'raw': {'path': f'/symbol/{index}.md', 'filename': f'{index}.md', 'preview': 'preview'}}
        for index, (_, value) in enumerate(LITERAL_SEARCH_CASES)
    ]
    expected_index = LITERAL_SEARCH_CASES.index((query, body))
    expected_id = str(uuid.UUID(int=expected_index + 1))
    response = client.get('/api/teaching-records', params={'q': query})
    assert response.status_code == 200
    assert [row['id'] for row in response.json()['items']] == [expected_id]
    assert all('content' not in row and 'raw' not in row for row in response.json()['items'])
    page = client.get('/search', params={'q': query})
    assert page.status_code == 200 and f'SymbolResult-{expected_index:02}' in page.text
    assert all(f'SymbolResult-{index:02}' not in page.text for index in range(len(LITERAL_SEARCH_CASES)) if index != expected_index)


def test_calendar_only_student_keeps_overview_and_detail_links(web_cloud, monkeypatch):
    import main
    client, remote, _ = web_cloud
    monkeypatch.setattr(main, 'load_digital_management_calendar_events', lambda: [{
        'id': 'calendar-only-event', 'title': '01.CalendarOnly數位管理教學',
        'date': '2026-10-20', 'start': '2026-10-20T14:00:00+08:00',
    }])
    overview = client.get('/api/digital-management/students')
    assert overview.status_code == 200
    entry = next(row for row in overview.json()['students'] if row['name'] == 'CalendarOnly')
    assert entry['id'] == 'digital-calendaronly'
    remote.calls.clear()
    detail = client.get('/api/digital-management/students/' + entry['id'])
    assert detail.status_code == 200
    profile = detail.json()['student']
    assert profile['id'] == entry['id'] and profile['name'] == 'CalendarOnly'
    assert profile['lessons'][0]['date'] == '2026-10-20'
    assert profile['notes'] == [] and profile['next_cursor'] is None
    page = client.get('/digital-management/student/' + entry['id'])
    assert page.status_code == 200 and 'CalendarOnly' in page.text
    assert entry['note_count'] == 0 and entry['notes_url'] is None
    assert not any(table == 'teaching_records' for table, _ in remote.calls)
