from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import PlanRequest
from app.planner import create_plan


def request(**overrides):
    today = datetime.now(UTC).date()
    data = {"destination": "Istanbul", "start_date": today + timedelta(days=20),
            "end_date": today + timedelta(days=22), "budget_usd": 1800,
            "travelers": 2, "interests": ["history", "food"], "origin_iata": "KHI"}
    data.update(overrides)
    return PlanRequest(**data)


@pytest.mark.asyncio
async def test_parallel_agents_compose_and_balance_the_group_ledger():
    with patch("app.planner.weather_for", new_callable=AsyncMock, return_value=[]), \
         patch("app.planner.Amadeus") as provider:
        provider.return_value.flight = AsyncMock(return_value=None)
        provider.return_value.hotel = AsyncMock(return_value=None)
        plan = await create_plan(request())
    assert len(plan.days) == 3
    assert len({day.theme for day in plan.days}) == 3
    assert {x.agent for x in plan.trace} == {
        "flights", "hotels", "activities", "weather", "orchestrator", "pricing"}
    assert plan.flight.amount_usd == 1200
    assert plan.hotel.amount_usd == 65
    assert sum(x.amount_usd for x in plan.budget.lines) == plan.budget.estimated_total_usd
    assert plan.budget.remaining_usd == plan.request.budget_usd - plan.budget.estimated_total_usd
    assert all(sum(item.estimated_cost_usd for item in day.items) == day.estimated_cost_usd
               for day in plan.days)
    assert "reserve" in " ".join(plan.caveats).lower()


@pytest.mark.asyncio
async def test_unaffordable_trip_is_flagged_not_disguised():
    with patch("app.planner.weather_for", new_callable=AsyncMock, return_value=[]), \
         patch("app.planner.Amadeus") as provider:
        provider.return_value.flight = AsyncMock(return_value=None)
        provider.return_value.hotel = AsyncMock(return_value=None)
        plan = await create_plan(request(budget_usd=200))
    assert not plan.budget.feasible
    assert plan.budget.remaining_usd < 0
    assert any("exceeds your budget" in x for x in plan.caveats)


@pytest.mark.asyncio
async def test_pace_changes_activity_count_without_changing_cost_invariants():
    with patch("app.planner.weather_for", new_callable=AsyncMock, return_value=[]), \
         patch("app.planner.Amadeus") as provider:
        provider.return_value.flight = AsyncMock(return_value=None)
        provider.return_value.hotel = AsyncMock(return_value=None)
        slow = await create_plan(request(pace="relaxed"))
        fast = await create_plan(request(pace="busy"))
    activities = lambda p: sum(item.category == "activity" for day in p.days for item in day.items)
    assert activities(slow) == 3
    assert activities(fast) == 7  # the catalogue has seven unique places
    assert fast.budget.estimated_total_usd > slow.budget.estimated_total_usd
    assert sum(line.amount_usd for line in fast.budget.lines) == fast.budget.estimated_total_usd


def test_invalid_trip_dates_and_inputs():
    with pytest.raises(ValidationError):
        request(end_date=datetime.now(UTC).date() + timedelta(days=28))
    with pytest.raises(ValidationError):
        request(interests=[])
    with pytest.raises(ValidationError):
        request(origin_iata="Karachi")


def test_api_persists_and_restores_a_plan(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app import db, main

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    db.Base.metadata.create_all(engine)
    monkeypatch.setattr(main, "Session", sessionmaker(bind=engine))
    with patch("app.planner.weather_for", new_callable=AsyncMock, return_value=[]), \
         patch("app.planner.Amadeus") as provider:
        provider.return_value.flight = AsyncMock(return_value=None)
        provider.return_value.hotel = AsyncMock(return_value=None)
        with TestClient(app) as client:
            response = client.post("/api/plans", json=request().model_dump(mode="json"))
            assert response.status_code == 201, response.text
            result = response.json()
            restored = client.get(f"/api/plans/{result['id']}")
            assert restored.status_code == 200
            assert restored.json() == result
            assert client.get("/api/destinations").status_code == 200
            assert client.get("/api/health").json() == {"status": "ok"}
            assert client.get("/api/plans/00000000-0000-0000-0000-000000000000").status_code == 404
