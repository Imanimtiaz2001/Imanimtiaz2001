from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.catalogue import DESTINATIONS
from app.db import Session, StoredPlan, init_db
from app.models import PlanRequest, TravelPlan
from app.planner import create_plan

STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Wayfinder — AI Travel Planner", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/destinations")
def destinations():
    return [{"name": data[0], "key": key} for key, data in DESTINATIONS.items()]


@app.post("/api/plans", response_model=TravelPlan, status_code=201)
async def plan(request: PlanRequest):
    result = await create_plan(request)
    with Session.begin() as session:
        session.add(StoredPlan(id=str(result.id), payload=result.model_dump_json()))
    return result


@app.get("/api/plans/{plan_id}", response_model=TravelPlan)
def get_plan(plan_id: UUID):
    with Session() as session:
        row = session.get(StoredPlan, str(plan_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return TravelPlan.model_validate_json(row.payload)
