"""Bounded external integrations. Provider failures are explicit and do not abort a plan."""

import math
import os
import time
from datetime import UTC, timedelta

import httpx

from app.models import Activity, Evidence, Offer, PlanRequest, WeatherDay

_cache: dict[str, tuple[float, object]] = {}


async def _cached_json(url: str, params: dict, ttl: int = 3600) -> dict:
    key = url + repr(sorted(params.items()))
    if key in _cache and _cache[key][0] > time.monotonic():
        return _cache[key][1]  # type: ignore[return-value]
    async with httpx.AsyncClient(timeout=8, headers={
        "User-Agent": os.getenv("USER_AGENT", "WayfinderPortfolio/1.0 (portfolio project)"),
    }) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    _cache[key] = (time.monotonic() + ttl, data)
    return data


async def geocode(destination: str) -> tuple[float, float] | None:
    try:
        data = await _cached_json("https://geocoding-api.open-meteo.com/v1/search",
                                  {"name": destination, "count": 1, "language": "en"}, 86400)
        match = (data.get("results") or [None])[0]
        return (match["latitude"], match["longitude"]) if match else None
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


async def weather_for(destination: str, request: PlanRequest) -> list[WeatherDay]:
    # Forecasts outside the provider's horizon would create false precision.
    from datetime import datetime

    if (request.end_date - datetime.now(UTC).date()).days > 15:
        return []
    point = await geocode(destination)
    if not point:
        return []
    try:
        data = await _cached_json("https://api.open-meteo.com/v1/forecast", {
            "latitude": point[0], "longitude": point[1],
            "daily": "temperature_2m_max,precipitation_probability_max",
            "timezone": "auto", "start_date": str(request.start_date),
            "end_date": str(request.end_date),
        }, 1800)
        daily = data["daily"]
        return [WeatherDay(date=d, temperature_max_c=t, precipitation_probability=p)
                for d, t, p in zip(daily["time"], daily["temperature_2m_max"],
                                   daily["precipitation_probability_max"])]
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return []


async def osm_activities(destination: str) -> list[Activity]:
    """Best-effort discovery for other cities; no made-up tickets or prices."""
    point = await geocode(destination)
    if not point:
        return []
    query = (f'[out:json][timeout:12];(nwr(around:5000,{point[0]},{point[1]})'
             '[tourism~"^(museum|gallery|attraction|viewpoint)$"][name];);out center 30;')
    try:
        data = await _cached_json("https://overpass.kumi.systems/api/interpreter",
                                  {"data": query}, 86400)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return []
    found: list[Activity] = []
    seen: set[str] = set()
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name:en") or tags.get("name")
        if not name or name.casefold() in seen or len(name) > 100:
            continue
        seen.add(name.casefold())
        category = tags.get("tourism", "attraction")
        found.append(Activity(
            name=name, category=category + " culture history art sightseeing",
            duration_hours=2, estimated_cost_usd=0, indoor=category in ("museum", "gallery"),
            description="Explore this mapped place; check opening hours and entry fees before visiting.",
            map_url=f"https://www.openstreetmap.org/{element['type']}/{element['id']}",
            evidence=Evidence(source="OpenStreetMap via Overpass", kind="live",
                              url=f"https://www.openstreetmap.org/{element['type']}/{element['id']}",
                              note="Entry fees unknown and excluded from the estimate."),
        ))
        if len(found) == 12:
            break
    return found


class Amadeus:
    def __init__(self):
        self.client_id = os.getenv("AMADEUS_CLIENT_ID")
        self.client_secret = os.getenv("AMADEUS_CLIENT_SECRET")
        self.base = os.getenv("AMADEUS_BASE_URL", "https://test.api.amadeus.com").rstrip("/")
        self.is_production = self.base == "https://api.amadeus.com"

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def _token(self, client: httpx.AsyncClient) -> str:
        key = "amadeus:" + self.base
        if key in _cache and _cache[key][0] > time.monotonic():
            return str(_cache[key][1])
        response = await client.post(self.base + "/v1/security/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": self.client_id,
            "client_secret": self.client_secret,
        })
        response.raise_for_status()
        data = response.json()
        token = data["access_token"]
        _cache[key] = (time.monotonic() + max(60, data.get("expires_in", 1200) - 90), token)
        return token

    async def _get(self, path: str, params: dict) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            token = await self._token(client)
            response = await client.get(self.base + path, params=params,
                                        headers={"Authorization": "Bearer " + token})
            response.raise_for_status()
            return response.json()

    async def flight(self, request: PlanRequest, destination_iata: str) -> Offer | None:
        if not self.configured or not request.origin_iata:
            return None
        try:
            data = await self._get("/v2/shopping/flight-offers", {
                "originLocationCode": request.origin_iata,
                "destinationLocationCode": destination_iata,
                "departureDate": str(request.start_date),
                "returnDate": str(request.end_date + timedelta(days=1)),
                "adults": request.travelers, "currencyCode": "USD", "max": 10,
            })
            offers = [o for o in data.get("data", []) if o.get("price", {}).get("total")]
            if not offers:
                return None
            best = min(offers, key=lambda o: float(o["price"]["total"]))
            amount = math.ceil(float(best["price"]["total"]))
            return Offer(title=f"Round-trip flights · {request.origin_iata} to {destination_iata}",
                         amount_usd=amount,
                         status="live_offer" if self.is_production else "planning_allowance",
                         search_url="https://www.google.com/travel/flights",
                         evidence=Evidence(source="Amadeus Flight Offers Search", url=self.base,
                                           kind="live" if self.is_production else "estimate",
                                           note="Production offer; recheck before booking." if self.is_production
                                           else "Amadeus sandbox sample; not bookable."))
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None

    async def hotel(self, request: PlanRequest, destination_iata: str) -> Offer | None:
        if not self.configured:
            return None
        try:
            hotels = await self._get("/v1/reference-data/locations/hotels/by-city",
                                     {"cityCode": destination_iata})
            ids = [h["hotelId"] for h in hotels.get("data", [])[:10] if h.get("hotelId")]
            if not ids:
                return None
            data = await self._get("/v3/shopping/hotel-offers", {
                "hotelIds": ",".join(ids), "adults": request.travelers,
                "checkInDate": str(request.start_date),
                "checkOutDate": str(request.end_date + timedelta(days=1)),
                "currency": "USD", "bestRateOnly": "true",
            })
            options = [(h, offer) for h in data.get("data", [])
                       for offer in h.get("offers", [])
                       if offer.get("price", {}).get("total")]
            if not options:
                return None
            hotel, offer = min(options, key=lambda pair: float(pair[1]["price"]["total"]))
            nights = (request.end_date - request.start_date).days + 1
            return Offer(title=hotel.get("hotel", {}).get("name", "Hotel offer"),
                         amount_usd=math.ceil(float(offer["price"]["total"]) / nights),
                         status="live_offer" if self.is_production else "planning_allowance",
                         search_url="https://www.google.com/travel/hotels",
                         evidence=Evidence(source="Amadeus Hotel Offers", url=self.base,
                                           kind="live" if self.is_production else "estimate",
                                           note="Nightly share of quoted stay; verify taxes/room capacity."
                                           if self.is_production else "Amadeus sandbox sample; not bookable."))
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
