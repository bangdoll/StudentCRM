"""Required integration contract against an isolated real PostgREST server.

Only the Supabase /rest/v1 transport prefix is adapted. PostgreSQL executes all
filters, projection, NULL/date ordering and pagination. No query simulator is
used. The runner creates only anonymous fixtures in disposable Docker services.
"""
from pathlib import Path
import base64
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from unittest.mock import patch
from uuid import UUID

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / 'tests')]
from search_contract_cases import LITERAL_SEARCH_CASES

SID = str(UUID(int=9999))
JWT_SECRET = 'studentcrm-disposable-contract-secret-only'


def rows():
    return [
        {'id': str(UUID(int=index + 1)), 'student_id': SID, 'student_name': 'Contract Student',
         'title': f'SymbolResult-{index:02}', 'date': None if index % 3 == 0 else '2026-10-20',
         'content': body if index % 2 == 0 else '',
         'raw': {'content': body if index % 2 else '', 'preview': 'preview',
                 'path': f'/contract/{index}.md', 'filename': f'{index}.md'}}
        for index, (_, body) in enumerate(LITERAL_SEARCH_CASES)
    ]


def seed_sql():
    return '''
CREATE ROLE contract_reader NOLOGIN;
CREATE TABLE teaching_records (
  id uuid PRIMARY KEY, student_id uuid, student_name text, title text,
  date text, lesson_num integer, lesson_sub text, source text,
  updated_at timestamptz, content text, raw jsonb
);
GRANT USAGE ON SCHEMA public TO contract_reader;
GRANT SELECT ON teaching_records TO contract_reader;
INSERT INTO teaching_records (id, student_id, student_name, title, date, content, raw)
SELECT id, student_id, student_name, title, date, content, raw
FROM jsonb_to_recordset($contract$''' + json.dumps(rows() + scope_body_rows(), ensure_ascii=False) + '''$contract$::jsonb)
  AS fixture(id uuid, student_id uuid, student_name text, title text, date text, content text, raw jsonb);
'''


def scope_body_rows():
    return [
        {'id': str(UUID(int=8001)), 'student_id': str(UUID(int=9997)), 'student_name': 'Contract Class',
         'title': 'Blank class body', 'date': '2026-10-21', 'content': ' \n\t',
         'raw': {'path': '/class/blank.md', 'filename': '0.md', 'content': 'CLASS_LEGACY_BODY'}},
        {'id': str(UUID(int=8002)), 'student_id': str(UUID(int=9996)), 'student_name': 'Other Student',
         'title': 'Private note', 'date': '2026-10-21', 'content': 'PRIVATE_OTHER_BODY',
         'raw': {'path': '/other/private.md', 'filename': 'private.md'}},
    ]


def token():
    def encode(value):
        return base64.urlsafe_b64encode(value).decode().rstrip('=')
    header = encode(b'{"alg":"HS256","typ":"JWT"}')
    payload = encode(json.dumps({'role': 'contract_reader', 'exp': int(time.time()) + 600}).encode())
    signature = encode(hmac.new(JWT_SECRET.encode(), f'{header}.{payload}'.encode(), hashlib.sha256).digest())
    return f'{header}.{payload}.{signature}'


def main():
    base = os.environ['STUDENTCRM_CONTRACT_POSTGREST_URL'].rstrip('/')
    parsed = urlsplit(base)
    if parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.scheme != 'http':
        raise ValueError('Contract tests must use an isolated loopback server')

    def transport(request, **kwargs):
        path = urlsplit(request.full_url)
        assert path.path.startswith('/rest/v1/')
        forwarded = Request(base + path.path.removeprefix('/rest/v1') + '?' + path.query,
                            headers=dict(request.header_items()))
        return urlopen(forwarded, **kwargs)

    with tempfile.TemporaryDirectory(prefix='studentcrm-postgrest-contract-') as temporary:
        os.environ.update(STUDENTCRM_DATA_BACKEND='supabase', SUPABASE_URL=base,
                          SUPABASE_ANON_KEY=token(), SUPABASE_SERVICE_ROLE_KEY='', STUDENTCRM_CACHE_DIR=temporary)
        from data_gateway import StudentDataGateway
        gateway = StudentDataGateway(temporary)
        gateway.teaching_records_file = str(Path(temporary) / 'absent.json')
        with patch('data_gateway.urlopen', transport):
            for index, (query, _) in enumerate(LITERAL_SEARCH_CASES):
                result = gateway.list_teaching_records(query=query)
                assert [row['id'] for row in result['items']] == [str(UUID(int=index + 1))], (query, result)
                assert all('content' not in row and 'raw' not in row for row in result['items'])
            # Server max_rows=1 must not truncate the alias-scoped result set.
            ids, cursor = [], None
            while True:
                result = gateway.list_teaching_records(query='AliasForStudent', student_ids=[SID], cursor=cursor)
                ids.extend(row['id'] for row in result['items'])
                cursor = result['next_cursor']
                if not cursor:
                    break
            assert len(ids) == len(set(ids)) == len(LITERAL_SEARCH_CASES)
            assert set(ids) == {row['id'] for row in rows()}
            # The server cap is 1: combined personal/class scope and legacy-body
            # reads must remain precise, including duplicate filename rejection.
            from teaching_reads import TeachingReadError
            scope = (SID, str(UUID(int=9997)))
            detail = gateway.load_teaching_record_detail(str(UUID(int=8001)), student_ids=scope)
            assert detail['content'] == 'CLASS_LEGACY_BODY'
            assert gateway.load_teaching_record_detail('/class/blank.md', student_ids=scope)['id'] == detail['id']
            assert gateway.load_teaching_record_detail(str(UUID(int=8002)), student_ids=scope) is None
            try:
                gateway.load_teaching_record_detail('0.md', student_ids=scope)
            except TeachingReadError:
                pass
            else:
                raise AssertionError('Ambiguous personal/class filename was accepted')
        print(f'Real PostgREST: {len(LITERAL_SEARCH_CASES)} literal/legacy-body searches and capped alias pagination passed')
        print('Real PostgREST: scoped class detail, whitespace fallback, isolation and capped ambiguity passed')


if __name__ == '__main__':
    if sys.argv[1:] == ['--seed-sql']:
        print(seed_sql())
    else:
        main()
