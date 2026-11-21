import json
from datetime import datetime, timezone
from time import perf_counter
from app.errors import DataError
from app.manifest import manifest
from app.pipeline import execute
from app.modules.runs.repository import fetch
from app.modules.runs.service import get
from . import repository
from .analysis import analyze


def cutover(predecessor_id, source, book):
    """以已确认批次为前版，用更订来源生成后继；切换失败不触碰旧批次。"""
    previous_row = fetch(predecessor_id)
    previous = json.loads(previous_row['result'])
    proof = manifest(source, book)
    if proof['run_id'] == predecessor_id:
        raise DataError('CUTOVER_NO_CHANGE', '更订来源与前版完全一致，未产生后继版本')
    started = perf_counter()
    # 先在事务外完整复算：复算抛错时数据库完全不写入，旧批次原样可用。
    result = execute(source, book)
    created = datetime.now(timezone.utc).isoformat()
    proof.update(elapsed_ms=round((perf_counter() - started) * 100, 2), created=created)
    result['manifest'] = proof
    links = repository.save_cutover(predecessor_id, proof['run_id'], source, book, result, created)
    report = analyze(previous, result)
    return {'manifest': proof, 'predecessor': predecessor_id, 'created': created,
            'lineage': links, 'cutover': report,
            **{key: result[key] for key in
               ('counts', 'balanced', 'accepted', 'quarantine', 'suppressed', 'book')}}


def diff(predecessor_id, successor_id):
    return analyze(get(predecessor_id), get(successor_id))
