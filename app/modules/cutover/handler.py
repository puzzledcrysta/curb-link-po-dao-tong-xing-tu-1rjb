from fastapi import APIRouter
from app.errors import DataError
from app.inputs import Cutover
from app.modules.runs.repository import fetch
from . import repository
from .service import cutover, diff

router = APIRouter()


@router.post('/api/cutover/{run_id}')
def create_successor(run_id: str, payload: Cutover):
    return cutover(run_id, payload.raw(), payload.ledger())


@router.get('/api/cutover/lineage')
def lineage_view():
    return {'links': repository.get_lineage()}


@router.get('/api/cutover/{predecessor_id}/{successor_id}')
def comparison(predecessor_id: str, successor_id: str):
    fetch(successor_id)
    links = { (item['predecessor'], item['successor']) for item in repository.get_lineage() }
    if (predecessor_id, successor_id) not in links:
        raise DataError('CUTOVER_UNLINKED', '两个批次之间没有后继关系', 404)
    return diff(predecessor_id, successor_id)
