import json
from app.errors import DataError
from app.store import connection


def lineage(db):
    return list(map(dict, db.execute(
        'SELECT predecessor, successor, created FROM successions ORDER BY created')))


def ancestry(db, run_id):
    """沿后继链向上追溯全部祖先，防止把旧批次挂到自己的后代下面。"""
    seen, current = [], run_id
    while True:
        row = db.execute('SELECT predecessor FROM successions WHERE successor=?', (current,)).fetchone()
        if row is None:
            return seen
        current = row['predecessor']
        seen.append(current)


def save_cutover(predecessor, successor, source, book, result, created):
    """整批切换在单事务内完成：任一步失败，旧批次与旧凭据原样保留。"""
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM runs WHERE id=?', (predecessor,)).fetchone() is None:
            raise DataError('RUN_UNKNOWN', '没有此批次', 404)
        if db.execute('SELECT 1 FROM runs WHERE id=?', (successor,)).fetchone() is None:
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?)',
                       (successor, source, book, json.dumps(result, ensure_ascii=False), created))
        if successor in ancestry(db, predecessor) or predecessor == successor:
            raise DataError('CUTOVER_CYCLE', '不能把旧批次挂到自己后代的后继上')
        existing = db.execute('SELECT successor FROM successions WHERE predecessor=?',
                              (predecessor,)).fetchone()
        if existing is not None and existing['successor'] != successor:
            raise DataError('CUTOVER_BRANCH', '该批次已有后继版本，整批只能线性更订')
        db.execute('INSERT OR IGNORE INTO successions VALUES (?,?,?)',
                   (predecessor, successor, created))
        return lineage(db)


def get_lineage():
    with connection() as db:
        return lineage(db)
