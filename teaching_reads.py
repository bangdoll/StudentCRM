"""Bounded teaching-record reads. Cloud failures never become local success.

Only metadata may be enumerated; bodies are fetched by identity or for the
latest three records of an explicitly selected student. No cloud body cache:
updates/deletions are visible on the next read, independent of updated_at.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from urllib.parse import urlencode
from uuid import UUID, uuid5, NAMESPACE_URL

META = 'id,student_id,student_name,title,date,lesson_num,lesson_sub,source,updated_at,path:raw->>path,filename:raw->>filename,preview:raw->>preview'
DETAIL = META + ',content'
ORDER = 'date.desc.nullslast,id.desc'


class TeachingReadError(RuntimeError):
    pass


class TeachingQueryError(ValueError):
    pass


def uuid_text(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise TeachingQueryError('學員或筆記 ID 無效') from None


def literal(value):
    return json.dumps(str(value), ensure_ascii=False)


def older_than(date, rid):
    rid = uuid_text(rid)
    if date is None:
        return 'and(date.is.null,id.lt.' + rid + ')'
    return 'or(date.lt.' + literal(date) + ',and(date.eq.' + literal(date) + ',id.lt.' + rid + '),date.is.null)'


def normalize(row, body=False):
    raw = row.get('raw') if isinstance(row.get('raw'), dict) else {}
    keys = ('id', 'student_id', 'student_name', 'title', 'date', 'lesson_num', 'lesson_sub', 'source', 'updated_at', 'path', 'filename', 'preview')
    result = {key: row.get(key) if row.get(key) is not None else raw.get(key) for key in keys}
    result['id'] = result['id'] or str(uuid5(NAMESPACE_URL, 'studentcrm:teaching:' + str(row.get('card_id') or row.get('path') or row.get('title') or '')))
    result['title'] = str(result['title'] or '教學紀錄')
    result['student_name'] = str(result['student_name'] or '')
    result['path'] = result['path'] or result['id'] or result['filename'] or ''
    result['preview'] = str(result['preview'] or '')[:280]
    result['lesson_number'] = result['lesson_num']
    result['url'] = '/note?' + urlencode({'path': result['id'] or result['path']})
    if body:
        result['content'] = row.get('content') or row.get('legacy_content') or raw.get('content') or ''
    return result


def sort_key(row):
    return (row.get('date') is not None, str(row.get('date') or ''), str(row.get('id') or ''))


class TeachingReads:
    def _teaching_local(self):
        if not os.path.isfile(self.teaching_records_file):
            return []
        data = self._read_json(self.teaching_records_file)
        return data if isinstance(data, list) else data.get('records', [])

    def _teaching_query(self, params):
        # _load_supabase_table is the HTTP boundary. Never catch into local data.
        return self._load_supabase_table('teaching_records', query=urlencode(params))

    def list_teaching_records(self, student_id=None, *, cursor=None, limit=50, query='', student_ids=()):
        if not 1 <= limit <= 100:
            raise TeachingQueryError('每頁需為 1–100 筆')
        if len(query) > 200 or (cursor and len(cursor) > 2048):
            raise TeachingQueryError('查詢參數過長')
        scope = hashlib.sha256(json.dumps([student_id, query, sorted(student_ids)], ensure_ascii=False).encode()).hexdigest()[:20]
        after = None
        if cursor:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
                if decoded['scope'] != scope:
                    raise ValueError()
                after = decoded['after']
                if not isinstance(after, list) or len(after) != 2 or (after[0] is not None and not isinstance(after[0], str)) or not isinstance(after[1], str):
                    raise ValueError()
                if self.backend == "supabase":
                    UUID(after[1])
            except (ValueError, KeyError, TypeError, UnicodeError):
                raise TeachingQueryError('分頁游標無效或篩選條件已改變') from None
        if self.backend == 'supabase':
            params = {'select': META, 'order': ORDER, 'limit': str(limit + 1)}
            if student_id:
                params['student_id'] = 'eq.' + uuid_text(student_id)
            predicates = []
            if after:
                predicates.append(older_than(*after))
            if query:
                # Literal substring matching; SQL wildcard characters are escaped.
                term = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_').replace('*', '\\*')
                pattern = literal('%' + term + '%')
                matches = [key + '.ilike.' + pattern for key in ('title', 'student_name', 'content', 'raw->>content', 'raw->>preview')]
                if student_ids:
                    matches.append('student_id.in.(' + ','.join(uuid_text(sid) for sid in student_ids) + ')')
                predicates.append('or(' + ','.join(matches) + ')')
            if predicates:
                params['and'] = '(' + ','.join(predicates) + ')'
            rows = self._teaching_query(params)
        else:
            rows = [{**row, "id": normalize(row)["id"]} for row in self._teaching_local()]
            if student_id:
                rows = [r for r in rows if r.get('student_id') == student_id]
            if query:
                rows = [r for r in rows if query.lower() in json.dumps(r, ensure_ascii=False).lower() or r.get('student_id') in student_ids]
            rows = sorted(rows, key=sort_key, reverse=True)
            if after:
                key = (after[0] is not None, str(after[0] or ''), after[1])
                rows = [r for r in rows if sort_key(r) < key]
        items = [normalize(row) for row in rows[:limit]]
        next_cursor = None
        has_more = len(rows) > limit
        if self.backend == 'supabase' and items and not has_more:
            # A project may cap API rows below our requested page size. A bounded
            # ID probe distinguishes the actual end from a truncated response.
            last = items[-1]
            probe = {**params, 'select': 'id', 'limit': '1'}
            probe['and'] = '(' + ','.join(predicates + [older_than(last['date'], last['id'])]) + ')'
            has_more = bool(self._teaching_query(probe))
        if has_more and items:
            last = items[-1]
            next_cursor = base64.urlsafe_b64encode(json.dumps({'scope': scope, 'after': [last['date'], last['id']]}).encode()).decode().rstrip('=')
        return {'items': items, 'next_cursor': next_cursor, 'has_more': bool(next_cursor)}

    def iter_teaching_metadata(self, student_id=None):
        cursor = None
        while True:
            page = self.list_teaching_records(student_id, cursor=cursor, limit=100)
            yield from page['items']
            cursor = page['next_cursor']
            if not cursor:
                break

    def load_all_teaching_records(self):
        # Compatibility for metadata-only statistics. Body callers use detail/recent.
        if self.backend != 'supabase':
            return self._teaching_local()
        return list(self.iter_teaching_metadata())

    def load_teaching_records(self, student_id):
        if self.backend != 'supabase':
            return [r for r in self._teaching_local() if r.get('student_id') == student_id]
        return list(self.iter_teaching_metadata(student_id)) if student_id else []

    def load_teaching_record_detail(self, identifier, *, student_id=None):
        if not identifier:
            return None
        target = str(identifier).strip()
        try:
            rid = str(UUID(target))
        except ValueError:
            rid = None
        if self.backend == 'supabase':
            params = {'select': DETAIL, 'limit': '2'}
            if student_id:
                params['student_id'] = 'eq.' + uuid_text(student_id)
            if rid:
                params['id'] = 'eq.' + rid
                rows = self._teaching_query(params)
            else:
                params['raw->>path'] = 'eq.' + target
                rows = self._teaching_query(params)
                if not rows:
                    del params['raw->>path']
                    params['raw->>filename'] = 'eq.' + os.path.basename(target)
                    rows = self._teaching_query(params)
                if len(rows) == 1:
                    probe = {**params, 'select': 'id', 'id': 'neq.' + uuid_text(rows[0]['id']), 'limit': '1'}
                    if self._teaching_query(probe):
                        raise TeachingReadError('筆記名稱重複，請使用原始完整連結')
        else:
            rows = [r for r in self._teaching_local() if (not student_id or r.get('student_id') == student_id)
                    and (normalize(r)['id'] == target or r.get('path') == target)]
            if not rows:
                rows = [r for r in self._teaching_local() if (not student_id or r.get('student_id') == student_id)
                        and r.get('filename') == os.path.basename(target)]
        if len(rows) > 1:
            raise TeachingReadError('筆記名稱重複，請使用原始完整連結')
        return self._teaching_bodies(rows, student_id=student_id)[0] if rows else None

    def teaching_neighbors(self, record):
        """Only the two neighboring metadata rows, ordered within one student."""
        sid = record.get('student_id')
        if not sid:
            return []
        if self.backend != 'supabase':
            rows = sorted([normalize(r) for r in self._teaching_local() if r.get('student_id') == sid], key=sort_key)
            pos = next((i for i, r in enumerate(rows) if r['id'] == record['id']), -1)
            return [r for i, r in enumerate(rows) if pos >= 0 and abs(i - pos) == 1]
        rid = uuid_text(record['id'])
        date = record.get('date')
        neighbors = []
        for older in (True, False):
            op = 'lt' if older else 'gt'
            params = {'select': META, 'student_id': 'eq.' + uuid_text(sid), 'limit': '1',
                      'order': ORDER if older else 'date.asc.nullsfirst,id.asc'}
            if date is None:
                params['or'] = '(and(date.is.null,id.' + op + '.' + rid + ')' + (',date.not.is.null' if not older else '') + ')'
            else:
                params['or'] = '(date.' + op + '.' + literal(date) + ',and(date.eq.' + literal(date) + ',id.' + op + '.' + rid + ')' + (',date.is.null' if older else '') + ')'
            neighbors += [normalize(r) for r in self._teaching_query(params)]
        return neighbors

    def load_recent_teaching_records(self, student_id, limit=3):
        if not 1 <= limit <= 3:
            raise ValueError('最近紀錄最多 3 筆')
        if self.backend != 'supabase':
            return [normalize(r, body=True) for r in sorted(self.load_teaching_records(student_id), key=sort_key, reverse=True)[:limit]]
        rows = []
        while len(rows) < limit:
            params = {'select': DETAIL, 'student_id': 'eq.' + uuid_text(student_id), 'order': ORDER, 'limit': str(limit - len(rows))}
            if rows:
                params['and'] = '(' + older_than(rows[-1].get('date'), rows[-1]['id']) + ')'
            batch = self._teaching_query(params)
            if not batch:
                break
            rows += batch
        return self._teaching_bodies(rows, student_id=student_id)

    def load_radar_teaching_records(self, student_ids):
        """Batch bodies for each student's latest three; no body history scan."""
        if self.backend != 'supabase':
            return self._teaching_local()
        selected = []
        counts = {}
        wanted = set(student_ids)
        for row in self.iter_teaching_metadata():
            sid = row.get('student_id')
            if sid in wanted and counts.get(sid, 0) < 3:
                selected.append(uuid_text(row['id']))
                counts[sid] = counts.get(sid, 0) + 1
        return self._teaching_bodies(self._teaching_by_ids(selected, DETAIL))

    def _teaching_by_ids(self, ids, select, student_id=None):
        result = []
        for start in range(0, len(ids), 50):
            pending = set(ids[start:start + 50])
            while pending:
                params = {'select': select, 'id': 'in.(' + ','.join(sorted(pending)) + ')', 'limit': str(len(pending)), 'order': 'id.desc'}
                if student_id:
                    params['student_id'] = 'eq.' + uuid_text(student_id)
                rows = self._teaching_query(params)
                if not rows:
                    break  # Deleted since the metadata scan.
                found = {r['id'] for r in rows}
                if not found <= pending:
                    raise TeachingReadError('教學紀錄回傳了非預期的 ID')
                result += rows
                pending -= found
        return result

    def _teaching_bodies(self, rows, student_id=None):
        if self.backend != "supabase":
            return [normalize(row, body=True) for row in rows]
        missing = [uuid_text(r["id"]) for r in rows if not r.get("content")]
        legacy = {r["id"]: r.get("legacy_content") or "" for r in self._teaching_by_ids(missing, "id,legacy_content:raw->>content", student_id=student_id)}
        return [normalize({**row, "legacy_content": legacy.get(row["id"], "")}, body=True) for row in rows]
