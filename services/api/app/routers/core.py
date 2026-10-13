from fastapi import APIRouter
from sqlalchemy import func, select

from app.deps import DB, CurrentUser
from app.models import Organisation, Site
from app.routers.auth import user_out
from app.schemas import DashboardHome, KpiTile, OrgOut, UserOut

router = APIRouter(tags=["core"])


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return user_out(user)


# The five executive headline KPIs (spec §9). Values arrive in Phase 3; until then each tile
# says plainly that there is no data rather than showing a misleading zero.
_HOME_KPIS = [
    ("saidi", "Outage minutes per customer (SAIDI)", "min", False),
    ("saifi", "Interruptions per customer (SAIFI)", "", False),
    ("faults_30d", "Faults in the last 30 days", "", False),
    ("availability", "Network availability", "%", True),
    ("sigma", "Sigma level", "σ", True),
]


@router.get("/dashboard/home", response_model=DashboardHome)
async def dashboard_home(user: CurrentUser, db: DB) -> DashboardHome:
    # No WHERE clause on purpose: Row-Level Security limits these to the caller's organisations/sites.
    orgs = (await db.execute(select(Organisation).order_by(Organisation.name))).scalars().all()
    site_count = (await db.execute(select(func.count()).select_from(Site))).scalar_one()
    return DashboardHome(
        organisations=[OrgOut(id=o.id, name=o.name) for o in orgs],
        site_count=site_count,
        kpis=[
            KpiTile(key=k, label=label, value=None, unit=unit, trend=None, higher_is_better=hib, trust="none")
            for k, label, unit, hib in _HOME_KPIS
        ],
        decisions_waiting=[],
        top_risks=[],
        what_changed=[
            "No fault data has been loaded yet. Upload records or connect SCADA to see insights here."
        ],
    )
