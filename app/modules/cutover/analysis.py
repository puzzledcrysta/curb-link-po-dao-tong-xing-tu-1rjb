"""逐笔比对前后两个批次，标出哪些结论仍有效、哪些因来源变化失效。"""
from app.settings import HEADER_COLUMNS, CUTOVER_STATES


def _index(report):
    """按业务键汇总一个批次的全部来源记录（采信、隔离、替代都保留凭据）。"""
    rows = {}
    for section in ('accepted', 'quarantine', 'suppressed'):
        for item in report.get(section, []):
            key = item.get('key') or ''
            if not key:
                continue
            rows.setdefault(key, []).append(
                {'signature': tuple(item.get('raw', [])), 'revision': item.get('revision'),
                 'line': item['line'], 'code': item.get('code'), 'section': section})
    return rows


def changed_fields(before, after):
    """同一业务键的来源行按顺序配对，逐列找出真正发生变化的字段。"""
    names = []
    for index, name in enumerate(HEADER_COLUMNS):
        old_values = {item['signature'][index] if index < len(item['signature']) else ''
                      for item in before}
        new_values = {item['signature'][index] if index < len(item['signature']) else ''
                      for item in after}
        if old_values != new_values:
            names.append(name)
    return names


def analyze(previous, current):
    """返回逐笔更订清单与汇总。KEPT 表示来源未变、原结论与凭据继续有效。"""
    before, after = _index(previous), _index(current)
    rows = []
    for key in sorted(before.keys() | after.keys()):
        old_records, new_records = before.get(key), after.get(key)
        if old_records and new_records:
            old_signatures = {item['signature'] for item in old_records}
            new_signatures = {item['signature'] for item in new_records}
            if old_signatures == new_signatures:
                state, detail, changed = 'KEPT', CUTOVER_STATES['KEPT'], []
            else:
                state, detail = 'RECAST', CUTOVER_STATES['RECAST']
                changed = changed_fields(old_records, new_records)
        elif new_records:
            state, detail, changed = 'NEW', CUTOVER_STATES['NEW'], []
        else:
            state, detail, changed = 'WITHDRAWN', CUTOVER_STATES['WITHDRAWN'], []
        chosen = (new_records or old_records)[0]
        rows.append({'key': key, 'state': state, 'detail': detail,
                     'revision': chosen['revision'], 'line': chosen['line'],
                     'changed_fields': changed,
                     'recheck_required': state != 'KEPT'})
    counts = {state: sum(1 for row in rows if row['state'] == state)
              for state in CUTOVER_STATES}
    counts['recheck_required'] = sum(1 for row in rows if row['recheck_required'])
    return {'rows': rows, 'counts': counts}
