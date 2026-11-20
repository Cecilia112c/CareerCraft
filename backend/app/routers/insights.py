from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from backend.app.auth import get_current_user
from backend.app.db import get_session
from backend.app.models import User
from backend.app.routers.jobs import JOB_STATUSES
from backend.app.services.insights import latest_market, library_insight, market_insight
from backend.app.services.jobs import get_push_setting
from backend.app.services.tasks import submit

router = APIRouter(prefix="/api/insights", tags=["insights"])


class MarketBody(BaseModel):
    titles: list[str] = Field(default_factory=list, max_length=3)
    cities: list[str] = Field(default_factory=list, max_length=5)


@router.get("/library")
def library(status: str = "", user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if status and status not in JOB_STATUSES:
        raise HTTPException(400, "无效的投递状态")
    return library_insight(session, user.id, status or None)


@router.get("/market")
def market(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return latest_market(session, user.id)


@router.post("/market")
def refresh_market(body: MarketBody, background: BackgroundTasks, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)):
    setting = get_push_setting(session, user.id)
    titles = [t.strip() for t in (body.titles or setting.titles or []) if t.strip()]
    cities = [c.strip() for c in (body.cities or setting.cities or []) if c.strip()]
    if not titles:
        raise HTTPException(400, "请先填写目标职位")
    user_id = user.id
    return {"task_id": submit(background, session, user_id, "insights:market",
                              lambda report: market_insight(user_id, titles, cities, report)).id}
