"""分段交清册、封单与排队。"""

from __future__ import annotations

import hashlib

from fastapi import HTTPException
from sqlalchemy import select

from src.config.settings import cache, engine
from src.constants.workflow import Status
from src.models.tables import cases, chunks, intakes, runs
from src.services import domain
from src.services.workflow import found, log
from src.utils.encoding import canonical
from src.utils.time import utc_time

MAX_SEGMENT_BYTES = 512 * 1024


def _register(conn, case_id, lock=False):
    query = select(intakes).where(intakes.c.case_id == case_id)
    if lock:
        query = query.with_for_update()
    row = conn.execute(query).mappings().first()
    if row is None:
        raise HTTPException(404, '该档案没有分段交册登记')
    return dict(row)


def _wake_worker():
    try:
        cache.lpush('worker:wake', 'queued')
        cache.ltrim('worker:wake', 0, 99)
    except Exception:
        # 数据库队列会被轮询，Redis 暂时不可用不影响排队。
        pass


def _check_segment(total_rows, run_bytes, start, records):
    if not isinstance(records, list) or not records:
        raise HTTPException(422, '分段清册必须是非空记录数组')
    blob = canonical(records)
    if len(blob) > MAX_SEGMENT_BYTES:
        raise HTTPException(422, '分段清册超过 512 KiB')
    end = start + len(records) - 1
    if end > total_rows:
        raise HTTPException(422, f'分段行号 {start}–{end} 超出登记总行数 {total_rows}')
    try:
        domain.validate_rows(run_bytes, start, records)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return hashlib.sha256(blob).hexdigest()


def _record_segment(conn, case, register, start, records, actor):
    """登记一个分段；原段重投返回 'duplicate'，新段写入后返回 'created'。"""
    case_id = case['id']
    digest = _check_segment(register['total_rows'], case['payload']['run_bytes'], start, records)
    end = start + len(records) - 1
    overlapping = conn.execute(
        select(chunks.c.start_row, chunks.c.row_count, chunks.c.digest)
        .where(chunks.c.case_id == case_id,
               chunks.c.start_row <= end,
               chunks.c.start_row + chunks.c.row_count - 1 >= start)).all()
    if overlapping:
        exact = [row for row in overlapping
                 if row.start_row == start and row.row_count == len(records)]
        if exact and exact[0].digest == digest:
            return 'duplicate'
        if exact:
            raise HTTPException(409, f'第 {start}–{end} 行已收讫，新送内容与原段不一致，已退回')
        raise HTTPException(409, f'第 {start}–{end} 行与已收分段的行号重叠，不予受理')
    conn.execute(chunks.insert().values(case_id=case_id, start_row=start,
                 row_count=len(records), digest=digest, records=records,
                 created_at=utc_time()))
    conn.execute(intakes.update().where(intakes.c.case_id == case_id)
                 .values(received_rows=register['received_rows'] + len(records)))
    log(conn, actor, 'intake_chunk', f'{case_id}:{start}')
    return 'created'


def _next_row(total_rows, segments):
    expected = 1
    for segment in segments:
        if segment['start_row'] > expected:
            break
        expected = max(expected, segment['start_row'] + segment['row_count'])
    return expected if expected <= total_rows else None


def _progress_body(conn, case_id, duplicate=None):
    register = _register(conn, case_id)
    segments = [dict(row) for row in conn.execute(
        select(chunks.c.start_row, chunks.c.row_count, chunks.c.created_at)
        .where(chunks.c.case_id == case_id).order_by(chunks.c.start_row)).mappings()]
    body = {
        'case_id': case_id,
        'total_rows': register['total_rows'],
        'received_rows': register['received_rows'],
        'next_row': _next_row(register['total_rows'], segments),
        'sealed_at': register['sealed_at'],
        'run_id': register['run_id'],
        'segments': segments,
    }
    if duplicate is not None:
        body['duplicate'] = duplicate
    return body


def progress(case_id):
    with engine.connect() as conn:
        found(conn, cases, case_id)
        return _progress_body(conn, case_id)


def add_chunk(case_id, start, records, actor):
    """收件一个分段，返回 (进度, 是否新收)。原段重投不重复收件。"""
    with engine.begin() as conn:
        case = found(conn, cases, case_id)
        register = _register(conn, case_id, lock=True)
        if register['sealed_at']:
            raise HTTPException(409, '清册已封单，不再收件')
        outcome = _record_segment(conn, case, register, start, records, actor)
        return _progress_body(conn, case_id, duplicate=outcome == 'duplicate'), outcome == 'created'


def seal(case_id, start, records, actor):
    """封单：可附带最后一段。收齐才排队；封单重试不重复排队。缺行时整单退回。"""
    if (start is None) != (records is None):
        raise HTTPException(422, '最后一段需要同时提供起始行号和清册记录')
    with engine.begin() as conn:
        case = found(conn, cases, case_id)
        register = _register(conn, case_id, lock=True)
        if register['sealed_at']:
            return found(conn, runs, register['run_id'])
        received = register['received_rows']
        if records is not None:
            if _record_segment(conn, case, register, start, records, actor) == 'created':
                received += len(records)
        missing = register['total_rows'] - received
        if missing > 0:
            raise HTTPException(409, f'清册缺 {missing} 行，收齐后才能封单排队')
        run_id = conn.execute(runs.insert().values(case_id=case_id, status=Status.QUEUED,
                              owner=actor, created_at=utc_time())).inserted_primary_key[0]
        conn.execute(intakes.update().where(intakes.c.case_id == case_id)
                     .values(sealed_at=utc_time(), run_id=run_id))
        log(conn, actor, 'enqueue', run_id)
        result = found(conn, runs, run_id)
    _wake_worker()
    return result
