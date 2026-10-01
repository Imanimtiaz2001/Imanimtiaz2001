from datetime import UTC, datetime, timedelta
from itertools import pairwise, product
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.catalogue import get_destination
from app.main import app
from app.models import PlanRequest, WeatherDay
from app.planner import create_plan
from app.providers import Amadeus, osm_activities, weather_for


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
        slow = await create_plan(request(pace="relaxed", budget_usd=3000))
        fast = await create_plan(request(pace="busy", budget_usd=3000))
    activities = lambda p: sum(item.category == "activity" for day in p.days for item in day.items)
    assert activities(slow) == 3
    assert activities(fast) == 7  # the catalogue has seven unique places
    assert fast.budget.estimated_total_usd > slow.budget.estimated_total_usd
    assert sum(line.amount_usd for line in fast.budget.lines) == fast.budget.estimated_total_usd
    for day in fast.days:
        intervals = [(item.time, item.end_time) for item in day.items]
        assert all(end is not None and start < end for start, end in intervals)
        assert all(first[1] <= second[0] for first, second in pairwise(intervals))


@pytest.mark.asyncio
async def test_budget_reserves_an_anchor_for_each_day():
    with patch("app.planner.weather_for", new_callable=AsyncMock, return_value=[]), \
         patch("app.planner.Amadeus") as provider:
        provider.return_value.flight = AsyncMock(return_value=None)
        provider.return_value.hotel = AsyncMock(return_value=None)
        plan = await create_plan(request(pace="busy", budget_usd=1800))
    assert plan.budget.feasible
    assert all(day.theme != "Open day" for day in plan.days)
    assert len({item.title for day in plan.days for item in day.items
                if item.category == "activity"}) == sum(
                    item.category == "activity" for day in plan.days for item in day.items)


@pytest.mark.asyncio
async def test_rain_prefers_indoor_place_without_changing_provider_data():
    req = request(pace="relaxed", budget_usd=3000)
    rainy = WeatherDay(date=req.start_date, temperature_max_c=18,
                       precipitation_probability=85)
    with patch("app.planner.weather_for", new_callable=AsyncMock, return_value=[rainy]), \
         patch("app.planner.Amadeus") as provider:
        provider.return_value.flight = AsyncMock(return_value=None)
        provider.return_value.hotel = AsyncMock(return_value=None)
        plan = await create_plan(req)
    assert plan.days[0].theme in {"Grand Bazaar", "Hagia Sophia", "Topkapı Palace",
                                  "Istanbul Archaeological Museums", "Süleymaniye Mosque"}
    assert plan.days[0].weather.precipitation_probability == 85


def test_invalid_trip_dates_and_inputs():
    with pytest.raises(ValidationError):
        request(end_date=datetime.now(UTC).date() + timedelta(days=28))
    with pytest.raises(ValidationError):
        request(interests=[])
    with pytest.raises(ValidationError):
        request(origin_iata="Karachi")
    with pytest.raises(ValidationError):
        request(destination="  ")


def test_ambiguous_city_is_not_mapped_to_wrong_country():
    assert get_destination("Paris") is not None
    assert get_destination("Paris, France") is not None
    assert get_destination("Paris, Texas") is None


@pytest.mark.asyncio
async def test_same_city_departure_excludes_flights():
    with patch("app.planner.weather_for", new_callable=AsyncMock, return_value=[]), \
         patch("app.planner.Amadeus") as provider:
        provider.return_value.hotel = AsyncMock(return_value=None)
        plan = await create_plan(request(origin_iata="IST"))
        provider.return_value.flight.assert_not_called()
    assert plan.flight is None
    assert plan.budget.lines[0].amount_usd == 0
    assert "match" in " ".join(plan.caveats)


@pytest.mark.asyncio
async def test_malformed_weather_and_map_results_degrade_gracefully():
    req = request(start_date=datetime.now(UTC).date() + timedelta(days=2),
                  end_date=datetime.now(UTC).date() + timedelta(days=4))
    with patch("app.providers.geocode", new_callable=AsyncMock, return_value=(1.0, 2.0)), \
         patch("app.providers._cached_json", new_callable=AsyncMock,
               return_value={"daily": {"time": ["invalid"],
                                       "temperature_2m_max": [12],
                                       "precipitation_probability_max": [70]}}):
        assert await weather_for("Istanbul", req) == []
    with patch("app.providers.geocode", new_callable=AsyncMock, return_value=(1.0, 2.0)), \
         patch("app.providers._cached_json", new_callable=AsyncMock,
               return_value={"elements": [{"tags": {"name": "Missing ID"}},
                                          {"type": "node", "id": 1,
                                           "tags": {"name": "Museum", "tourism": "museum"}}]}):
        found = await osm_activities("Elsewhere")
    assert len(found) == 1 and found[0].estimated_cost_usd == 0


@pytest.mark.asyncio
async def test_forecast_uses_available_horizon_for_part_of_trip():
    today = datetime.now(UTC).date()
    req = request(start_date=today + timedelta(days=13),
                  end_date=today + timedelta(days=18))
    payload = {"daily": {"time": [str(today + timedelta(days=i)) for i in range(13, 16)],
                         "temperature_2m_max": [20, 21, 22],
                         "precipitation_probability_max": [0, 30, 80]}}
    with patch("app.providers.geocode", new_callable=AsyncMock, return_value=(1.0, 2.0)), \
         patch("app.providers._cached_json", new_callable=AsyncMock,
               return_value=payload) as fetch:
        result = await weather_for("Istanbul", req)
    assert len(result) == 3
    assert fetch.call_args.args[1]["end_date"] == str(today + timedelta(days=15))


@pytest.mark.asyncio
async def test_hotel_quote_requests_enough_rooms_and_rejects_wrong_currency(monkeypatch):
    monkeypatch.setenv("AMADEUS_CLIENT_ID", "test")
    monkeypatch.setenv("AMADEUS_CLIENT_SECRET", "test")
    provider = Amadeus()
    calls = []

    async def fake_get(path, params):
        calls.append((path, params))
        if "by-city" in path:
            return {"data": [{"hotelId": "X"}]}
        return {"data": [{"hotel": {"name": "Sample"},
                          "offers": [{"roomQuantity": 2,
                                      "price": {"currency": "EUR", "total": "50"}}]}]}

    monkeypatch.setattr(provider, "_get", fake_get)
    assert await provider.hotel(request(travelers=4), "IST") is None
    assert calls[1][1]["roomQuantity"] == 2


@pytest.mark.asyncio
async def test_cost_and_timeline_invariants_across_trip_shapes():
    today = datetime.now(UTC).date()
    with patch("app.planner.weather_for", new_callable=AsyncMock, return_value=[]), \
         patch("app.planner.Amadeus") as provider:
        provider.return_value.flight = AsyncMock(return_value=None)
        provider.return_value.hotel = AsyncMock(return_value=None)
        for days, travelers, budget, pace in product((1, 3, 7), (1, 4),
                                                    (100, 1800, 10000),
                                                    ("relaxed", "balanced", "busy")):
            plan = await create_plan(request(start_date=today + timedelta(days=20),
                                             end_date=today + timedelta(days=19 + days),
                                             travelers=travelers, budget_usd=budget, pace=pace))
            assert len(plan.days) == days
            assert plan.budget.estimated_total_usd == sum(x.amount_usd for x in plan.budget.lines)
            assert plan.budget.feasible == (plan.budget.estimated_total_usd <= budget)
            for day in plan.days:
                assert day.estimated_cost_usd == sum(i.estimated_cost_usd for i in day.items)
                assert all(a.end_time <= b.time for a, b in pairwise(day.items))


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
