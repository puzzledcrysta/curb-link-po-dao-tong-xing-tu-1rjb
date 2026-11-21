import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT / 'sample_data'
DB = Path(os.getenv('WORKBENCH_DB', str(ROOT/'state/ledger.sqlite3')))
TITLE = '坡道通行图'
SLUG = 'curb-link'
KEY = '踏勘单'
FIELDS = ('始点', '终点', '最小净宽厘米', '最大纵坡百分比', '路段')
HEADER_COLUMNS = (KEY, '修订号', '提交时间', *FIELDS, '原始备注')
ROLE = '街道无障碍巡检员'
UNIT = '米'
RULE_VERSION = 'curb-link-1.0'
SIGNATURE = '可通行路段'
TABS = {'intake': '踏勘上传', 'contract': '路网字段', 'quality': '不可用踏勘', 'domain': '通行选路', 'reconcile': '里程对读', 'runs': '踏勘档次', 'cutover': '后继更订', 'review': '巡检交付'}
CUTOVER_STATES = {
    'KEPT': '来源未变 · 结论仍有效',
    'RECAST': '来源变化 · 结论失效需重算',
    'NEW': '新增踏勘单 · 待首算',
    'WITHDRAWN': '后继已移除 · 旧结论停用',
}
