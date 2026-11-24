"""按原登记行号流式读出已收分段，避免把全部登记行拼成一份大档案。"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import select

from src.models.tables import chunks


def stored_records(engine, case_id: int) -> Iterator[tuple[int, object]]:
    """按清册行号顺序逐件产出 (原登记行号, 馆藏记录)。"""
    with engine.connect() as conn:
        result = conn.execution_options(stream_results=True).execute(
            select(chunks.c.start_row, chunks.c.records)
            .where(chunks.c.case_id == case_id)
            .order_by(chunks.c.start_row))
        for start_row, records in result:
            for offset, record in enumerate(records):
                yield start_row + offset, record
