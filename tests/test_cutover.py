import csv
import io
from concurrent.futures import ThreadPoolExecutor
from app.settings import CUTOVER_STATES


def _rows(source):
    reader = list(csv.reader(io.StringIO(source.decode('utf-8-sig'))))
    return reader[0], reader[1:]


def _write(header, rows):
    stream = io.StringIO(newline='')
    csv.writer(stream).writerows([header, *rows])
    return stream.getvalue().encode()


def _modify(source, key, field, value, drop_key=None, add_key=None):
    header, rows = _rows(source)
    out = []
    for row in rows:
        if len(row) != len(header):
            out.append(row)
            continue
        if drop_key and row[0] == drop_key:
            continue
        row = row.copy()
        if row[0] == key:
            row[header.index(field)] = value
        out.append(row)
    if add_key:
        template = next(r for r in rows if len(r) == len(header) and r[0] == key).copy()
        template[0] = add_key
        out.append(template)
    return _write(header, out)


def _cutover(client, run_id, source, book):
    return client.post(f'/api/cutover/{run_id}',
                       json={'data': source.decode(), 'book': book.decode()})


def test_cutover_creates_successor_and_keeps_predecessor(client, source, book):
    first = client.post('/api/runs', json={}).json()
    pid = first['manifest']['run_id']
    changed = _modify(source, '00101', '最小净宽厘米', '150')
    response = _cutover(client, pid, changed, book)
    assert response.status_code == 200
    report = response.json()
    sid = report['manifest']['run_id']
    assert sid != pid and report['predecessor'] == pid
    # 旧批次与凭据原样保留，仍可打开、可导出
    assert client.get(f'/api/runs/{pid}').status_code == 200
    assert client.get(f'/api/export/{pid}').status_code == 200
    links = client.get('/api/cutover/lineage').json()['links']
    assert [item['successor'] for item in links] == [sid]


def test_kept_rows_skip_recheck_recast_rows_require_it(client, source, book):
    pid = client.post('/api/runs', json={}).json()['manifest']['run_id']
    changed = _modify(source, '00101', '最小净宽厘米', '150', add_key='00200')
    report = _cutover(client, pid, changed, book).json()['cutover']
    by_key = {row['key']: row for row in report['rows']}
    assert by_key['00101']['state'] == 'RECAST'
    assert by_key['00101']['changed_fields'] == ['最小净宽厘米']
    assert by_key['00101']['recheck_required'] is True
    assert by_key['00200']['state'] == 'NEW' and by_key['00200']['recheck_required'] is True
    kept = next(row for row in report['rows'] if row['state'] == 'KEPT')
    assert kept['recheck_required'] is False and kept['changed_fields'] == []
    assert report['counts']['recheck_required'] == 2
    assert set(CUTOVER_STATES) == {'KEPT', 'RECAST', 'NEW', 'WITHDRAWN'}


def test_withdrawn_key_is_flagged(client, source, book):
    pid = client.post('/api/runs', json={}).json()['manifest']['run_id']
    shrunk = _modify(source, '00101', '最小净宽厘米', '150', drop_key='00102')
    report = _cutover(client, pid, shrunk, book).json()['cutover']
    withdrawn = [row for row in report['rows'] if row['state'] == 'WITHDRAWN']
    assert [row['key'] for row in withdrawn] == ['00102']
    assert withdrawn[0]['recheck_required'] is True


def test_failed_switch_leaves_old_batch_intact(client, source, book):
    first = client.post('/api/runs', json={}).json()
    pid = first['manifest']['run_id']
    broken = client.post(f'/api/cutover/{pid}', json={'data': '"broken', 'book': book.decode()})
    assert broken.status_code == 422 and broken.json()['code'] == 'CSV'
    # 没有产生任何后继关系，旧批次结果不变
    assert client.get('/api/cutover/lineage').json()['links'] == []
    assert client.get(f'/api/runs/{pid}').json() == first


def test_identical_inputs_rejected(client, source, book):
    pid = client.post('/api/runs', json={}).json()['manifest']['run_id']
    response = _cutover(client, pid, source, book)
    assert (response.status_code, response.json()['code']) == (422, 'CUTOVER_NO_CHANGE')


def test_chain_must_stay_linear_and_acyclic(client, source, book):
    pid = client.post('/api/runs', json={}).json()['manifest']['run_id']
    changed = _modify(source, '00101', '最小净宽厘米', '150')
    sid = _cutover(client, pid, changed, book).json()['manifest']['run_id']
    # 同一前版不能分叉出第二个后继
    other = _modify(source, '00101', '最大纵坡百分比', '6')
    branch = _cutover(client, pid, other, book)
    assert (branch.status_code, branch.json()['code']) == (422, 'CUTOVER_BRANCH')
    # 后继不能把祖先重新挂为自己的后继（成环）
    loop_back = _cutover(client, sid, source, book)
    assert (loop_back.status_code, loop_back.json()['code']) == (422, 'CUTOVER_CYCLE')


def test_successor_review_is_independent(client, source, book):
    pid = client.post('/api/runs', json={}).json()['manifest']['run_id']
    client.post(f'/api/review/{pid}', json={'version': 0, 'decision': '确认', 'note': '前版已签字'})
    changed = _modify(source, '00101', '最小净宽厘米', '150')
    sid = _cutover(client, pid, changed, book).json()['manifest']['run_id']
    # 后继是全新复核线，不能借用前版签字
    assert client.get(f'/api/review/{sid}').json() == []
    assert [item['decision'] for item in client.get(f'/api/review/{pid}').json()] == ['确认']


def test_diff_requires_linked_pair(client, source, book):
    first = client.post('/api/runs', json={}).json()['manifest']['run_id']
    changed = _modify(source, '00101', '最小净宽厘米', '150')
    second = client.post('/api/runs', json={'data': changed.decode(), 'book': book.decode()}).json()
    sid = second['manifest']['run_id']
    response = client.get(f'/api/cutover/{first}/{sid}')
    assert (response.status_code, response.json()['code']) == (404, 'CUTOVER_UNLINKED')
    linked = _cutover(client, first, changed, book)
    assert linked.status_code == 200
    assert client.get(f'/api/cutover/{first}/{sid}').status_code == 200


def test_cutover_requires_explicit_source(client, source, book):
    pid = client.post('/api/runs', json={}).json()['manifest']['run_id']
    response = client.post(f'/api/cutover/{pid}', json={})
    assert (response.status_code, response.json()['code']) == (422, 'CONTRACT')


def test_unknown_predecessor(client, source, book):
    response = _cutover(client, 'missing', source, book)
    assert (response.status_code, response.json()['code']) == (404, 'RUN_UNKNOWN')


def test_concurrent_cutovers_keep_single_linear_link(client, source, book):
    pid = client.post('/api/runs', json={}).json()['manifest']['run_id']
    changed = _modify(source, '00101', '最小净宽厘米', '150')
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(
            lambda _: client.post(f'/api/cutover/{pid}',
                                  json={'data': changed.decode(), 'book': book.decode()}),
            range(4)))
    assert all(response.status_code == 200 for response in outcomes)
    links = client.get('/api/cutover/lineage').json()['links']
    assert len(links) == 1 and links[0]['predecessor'] == pid
