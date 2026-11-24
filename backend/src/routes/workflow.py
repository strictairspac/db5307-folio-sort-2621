from fastapi import APIRouter, Depends, Response
from sqlalchemy import text

from src.config.settings import cache, engine
from src.controllers.workflow import download
from src.models.tables import audit, cases, evidence, runs
from src.schemas.workflow import CaseForm, ChunkForm, LoginForm, ReviewForm, SealForm
from src.services import domain, intake, workflow
from src.services.security import current_user, login, operator, reviewer

router = APIRouter()


@router.get('/health')
def health():
    with engine.connect() as conn:
        conn.execute(text('SELECT 1')).scalar_one()
    cache.ping()
    return {'ok': True}


@router.post('/login')
def sign_in(form: LoginForm):
    return login(form.username, form.password)


@router.get('/spec')
def spec(_=Depends(current_user)):
    return domain.SPEC


@router.get('/cases')
def list_cases(_=Depends(current_user)):
    return workflow.recent(cases)


@router.post('/cases', status_code=201)
def create_case(form: CaseForm, actor=Depends(operator)):
    return workflow.make_case(form.title, form.payload, actor)


@router.get('/runs')
def list_runs(_=Depends(current_user)):
    return workflow.recent(runs)


@router.post('/cases/{case_id}/runs', status_code=202)
def start_run(case_id: int, actor=Depends(operator)):
    return workflow.enqueue(case_id, actor)


@router.get('/cases/{case_id}/intake')
def intake_progress(case_id: int, _=Depends(current_user)):
    return intake.progress(case_id)


@router.post('/cases/{case_id}/chunks')
def submit_chunk(case_id: int, form: ChunkForm, response: Response, actor=Depends(operator)):
    body, created = intake.add_chunk(case_id, form.start, form.records, actor)
    if created:
        response.status_code = 201
    return body


@router.post('/cases/{case_id}/seal')
def seal_case(case_id: int, form: SealForm | None = None, actor=Depends(operator)):
    return intake.seal(case_id, form.start if form else None, form.records if form else None, actor)


@router.get('/evidence')
def list_evidence(_=Depends(current_user)):
    return workflow.recent(evidence)


@router.get('/evidence/{identity}/download')
def export_evidence(identity: int, _=Depends(current_user)):
    return download(identity)


@router.post('/evidence/{identity}/review')
def review_evidence(identity: int, form: ReviewForm, actor=Depends(reviewer)):
    return workflow.review(identity, form.note, actor)


@router.get('/audit')
def list_audit(_=Depends(current_user)):
    return workflow.recent(audit)
