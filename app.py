"""Safar: a travel-planning agent. FastAPI backend + Claude tool-use loop, streamed to the UI over SSE."""

import asyncio
import difflib
import functools
import gzip
import hashlib
import html
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

STATIC = Path(__file__).parent / "static"


def _load_env(path: Path = Path(__file__).parent / ".env") -> None:
    """Read NAME=value lines from .env. Variables already set in the shell win."""
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() and not name.strip().startswith("#"):
                os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


_load_env()  # before the client below reads ANTHROPIC_API_KEY

# One codebase, two markets. SAFAR_EDITION picks who the agent works for, which currencies it quotes in,
# and the landing page's photo and sample. Everything else (tools, verdicts, UI) is shared.
EDITIONS = {
    "addis": {
        "agency": "travel-agency staff in Addis Ababa",
        "currencies": ["ETB", "USD"],
        "guest_nationality": "ET",
        "example_item": "Return flights ET704/ET705 x2",
        "landing": {
            "HERO_1200": "/static/img/lalibela-1200.jpg", "HERO_2400": "/static/img/lalibela-2400.jpg", "HERO_POS": "50% 62%",
            "HERO_ALT": "Sunset over the highlands outside Lalibela, Ethiopia, with a road winding through the valley",
            "SAMPLE_TRIP": "ISTANBUL · 2 ADULTS · 5 NTS", "SAMPLE_ROUTE": "ADD ⇄ IST", "SAMPLE_DATES": "12NOV–17NOV",
            "SAMPLE_TOTAL": "$2,488", "SAMPLE_SECOND": "ETB 400,537", "SAMPLE_TAG": "SAMPLE · DEMO FARES · LIVE NBE RATE",
            "BRIEF_EXAMPLE": "\"2 adults, Istanbul next month, about $1,500 each, quote in birr.\"",
            "FX_LINE": "today's National Bank of Ethiopia rate", "FX_CODE": "USD→ETB",
            "FX_SOURCE": "Exchange rates from the National Bank of Ethiopia.",
            "PHOTO_CREDIT": "Lalibela highlands by Mulugeta Wolde", "PHOTO_URL": "https://unsplash.com/photos/hYjIYsJuyVQ",
        },
    },
    "internova": {
        "agency": "travel advisors at agencies in the US, Canada and the UK",
        "currencies": ["USD", "CAD", "GBP"],
        "guest_nationality": "US",
        "example_item": "Return flights AA10/IB3176 x2",
        "landing": {
            "HERO_1200": "/static/img/lisbon-1200.jpg", "HERO_2400": "/static/img/lisbon-2400.jpg", "HERO_POS": "50% 70%",
            "HERO_ALT": "Tram tracks running uphill between painted walls in Lisbon, toward a yellow building in the sun",
            "SAMPLE_TRIP": "LISBON · 2 ADULTS · 7 NTS", "SAMPLE_ROUTE": "JFK ⇄ LIS", "SAMPLE_DATES": "12MAY–19MAY",
            "SAMPLE_TOTAL": "$5,940", "SAMPLE_SECOND": "NET $5,400 · +10%", "SAMPLE_TAG": "SAMPLE · SANDBOX FARES",
            "BRIEF_EXAMPLE": "\"2 adults from Chicago, a week in Lisbon in May, about $6,000 all in.\"",
            "FX_LINE": "today's exchange rate for USD, CAD and GBP clients", "FX_CODE": "USD→CAD",
            "FX_SOURCE": "Live exchange rates for USD, CAD and GBP.",
            "PHOTO_CREDIT": "Lisbon tram tracks by Taton Moïse", "PHOTO_URL": "https://unsplash.com/photos/9gttcxe3cnM",
        },
    },
}
EDITION_NAME = os.environ.get("SAFAR_EDITION", "addis")
if EDITION_NAME not in EDITIONS:
    raise SystemExit(f"SAFAR_EDITION must be one of {', '.join(EDITIONS)}, not {EDITION_NAME!r}")
EDITION = EDITIONS[EDITION_NAME]

# Which model runs the agent, chosen per request in the UI (Settings), with .env as the default.
# Prices, markup and verdicts are computed in code whichever model writes the words.
PROVIDERS = {
    "anthropic": {"label": "Claude", "kind": "anthropic", "key_env": "ANTHROPIC_API_KEY",
                  "models": ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]},
    "openrouter": {"label": "OpenRouter", "kind": "openai", "key_env": "OPENROUTER_API_KEY", "base_url": "https://openrouter.ai/api/v1"},
    "ollama": {"label": "Ollama (this computer)", "kind": "openai", "base_url": "http://localhost:11434/v1", "local": "Ollama"},
    "lmstudio": {"label": "LM Studio (this computer)", "kind": "openai", "base_url": "http://localhost:1234/v1", "local": "LM Studio"},
    "azure": {"label": "Azure OpenAI", "kind": "openai", "key_env": "AZURE_OPENAI_API_KEY", "url_env": "AZURE_OPENAI_BASE_URL"},
    "custom": {"label": "Other OpenAI-compatible", "kind": "openai", "key_env": "OPENAI_API_KEY", "url_env": "OPENAI_BASE_URL"},
}
DEFAULT_PROVIDER = {"openai": "custom"}.get(os.environ.get("SAFAR_PROVIDER", ""), os.environ.get("SAFAR_PROVIDER") or "anthropic")
if DEFAULT_PROVIDER not in PROVIDERS:
    raise SystemExit(f"SAFAR_PROVIDER must be one of {', '.join(PROVIDERS)}, not {DEFAULT_PROVIDER!r}")
DEFAULT_MODEL = os.environ.get("SAFAR_MODEL") or ("claude-opus-5" if DEFAULT_PROVIDER == "anthropic" else "")
MODEL_NAME = re.compile(r"[\w.:/@+-]{1,120}")
_clients: dict = {}


def _base_url(pid: str) -> str | None:
    p = PROVIDERS[pid]
    return p.get("base_url") or os.environ.get(p.get("url_env", "")) or None


def _client_for(pid: str):
    """One SDK client per provider and credentials, rebuilt when a key is changed in Settings."""
    p = PROVIDERS[pid]
    key = os.environ.get(p.get("key_env", ""), "")
    cache_key = (pid, key, _base_url(pid))
    if cache_key not in _clients:
        if p["kind"] == "anthropic":
            _clients[cache_key] = anthropic.AsyncAnthropic(api_key=key or None)
        else:
            import openai
            _clients[cache_key] = openai.AsyncOpenAI(base_url=_base_url(pid), api_key=key or "not-needed")  # local servers ignore it
    return _clients[cache_key]


@functools.lru_cache(maxsize=4)
def _openrouter_models(hour: int) -> tuple[tuple, tuple]:
    """OpenRouter's public model list, only models that can call tools, plus which of them cost nothing
    (free models may log prompts and are rate-limited, so the UI warns about them). Refreshed hourly."""
    req = urllib.request.Request("https://openrouter.ai/api/v1/models", headers={"User-Agent": "safar-demo"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.load(resp)["data"]
    tools = [m for m in data if "tools" in (m.get("supported_parameters") or [])]
    free = [m["id"] for m in tools if m["id"].endswith(":free")
            or all(float((m.get("pricing") or {}).get(k) or 0) == 0 for k in ("prompt", "completion"))]
    return tuple(sorted(m["id"] for m in tools)), tuple(sorted(free))


@functools.lru_cache(maxsize=256)
def _openrouter_tool_endpoints(model: str, hour: int) -> int:
    """How many of the model's live OpenRouter providers accept tool calls (-1: OpenRouter doesn't know the model).
    The agent can't search without tools, and a model can list tool support while none of its live providers offer it."""
    url = f"https://openrouter.ai/api/v1/models/{urllib.parse.quote(model, safe='/:._-')}/endpoints"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "safar-demo"}), timeout=8) as resp:
            endpoints = json.load(resp)["data"]["endpoints"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return -1
        raise
    return sum("tools" in (e.get("supported_parameters") or []) for e in endpoints)


def model_problem(provider: str, model: str) -> str | None:
    """Why this model can't run the agent, or None if it can (or we couldn't tell: then let the request decide)."""
    if provider != "openrouter":
        return None
    try:
        count = _openrouter_tool_endpoints(model, int(time.time() // 3600))
    except Exception:
        return None
    if count == -1:
        return f"OpenRouter doesn't have a model called {model}. Pick one from the list."
    if count == 0:
        return (f"{model} has no provider on OpenRouter that supports tool calling right now, and Safar's agent "
                "needs tools to search. Pick another model.")
    return None


def _local_models(base_url: str) -> list[str] | None:
    """Models a local server (Ollama, LM Studio) has loaded, or None if it isn't running."""
    try:
        with urllib.request.urlopen(f"{base_url}/models", timeout=1) as resp:
            return sorted(m["id"] for m in json.load(resp).get("data", []))
    except Exception:
        return None


def provider_state(pid: str) -> dict:
    p = PROVIDERS[pid]
    state = {"id": pid, "label": p["label"], "kind": p["kind"], "models": p.get("models"),
             "needs_key": bool(p.get("key_env")), "needs_url": bool(p.get("url_env")),
             "has_key": bool(os.environ.get(p.get("key_env", ""))), "has_url": bool(_base_url(pid)), "ready": False, "hint": ""}
    if p.get("local"):
        models = _local_models(p["base_url"])
        state.update(ready=bool(models), models=models or [],
                     hint="" if models else f"Not running. Start {p['local']} and load a model that supports tool calling.")
    elif pid == "openrouter":
        try:
            models, free = _openrouter_models(int(time.time() // 3600))
            state.update(models=list(models), free_models=list(free))
        except Exception:
            state.update(models=[], free_models=[])
        state["ready"] = state["has_key"]
    else:
        state["ready"] = (state["has_key"] or not state["needs_key"]) and (state["has_url"] or not state["needs_url"])
    if not state["ready"] and not state["hint"]:
        missing = [w for w, ok in (("an API key", state["has_key"] or not state["needs_key"]),
                                   ("a base URL", state["has_url"] or not state["needs_url"])) if not ok]
        state["hint"] = "Needs " + " and ".join(missing) + "." if missing else ""
    return state


app = FastAPI(title="Safar Travel Agent")

# ponytail: in-memory sessions, lost on restart and single-process only; move to Redis/Postgres for real deploys.
SESSIONS: dict[str, dict] = {}  # id -> {"kind": "anthropic" | "openai", "history": [...]}

SYSTEM = """You are Safar, a copilot for {agency}. The user is an agent
turning a client's brief into a priced trip proposal they will send to the client.

Use the tools before recommending anything; never invent flights, hotels or prices.
Call independent tools in parallel (outbound flight, return flight and hotel together).
If the brief is missing something (dates, origin), assume sensibly and say so in one line.

Unless the brief says otherwise, also price a round-trip airport transfer (search_transfers, using the hotel's coordinates) and
search activities for the stay; include the chosen transfer and activities in price_quote.
Search results are NET prices. After choosing, call price_quote once with every bookable item at its net USD total
for the whole party (e.g. "{example_item}"). It applies the agency's markup and converts to the client's currency.
Quote the client ONLY price_quote's client prices; never show net fares, search prices or the markup anywhere in the proposal.
Each tool result starts with a coupon number like "CPN 05". Cite it in parentheses right after every price, e.g. "$1,480 (CPN 05)",
so the agent can check the source. Don't add a source column to tables.

Write the proposal in Markdown, client-ready and concise:
1. a heading with destination, dates and travellers;
2. the chosen flights and hotel, one line each;
3. a short day-by-day plan, one line per day (arrival with the airport transfer, one or two bookable activities from search_activities on free days, departure);
4. a price table from price_quote: each item and the total in {currency}{usd_note};
5. one or two alternatives (cheaper or better), described by trade-off and relative cost (e.g. "3★, about 20% cheaper"), never with net prices.
No preamble, no sign-off.

If the agent pastes a plan the client made elsewhere (often ChatGPT), audit it first: call check_flight, check_hotel and
check_activity, in parallel, for every flight, hotel and activity it names. Start the reply with "## Plan check" and a table:
item | the plan says | the supplier says | verdict (CPN). Copy each verdict and reason exactly as the tool returns them; never
upgrade a verdict. "not_found" means not found at that supplier, never that it does not exist. Then write the corrected
proposal in the usual format, replacing anything not verified with searched alternatives, and price it with price_quote.
Quote in {currency} unless the brief clearly says the client pays in another currency.
Today's date is {today}. {inventory}"""


# ---------- Tools (deterministic demo data: same query, same results) ----------

AIRLINES = {"ET": "Ethiopian Airlines", "EK": "Emirates", "TK": "Turkish Airlines", "QR": "Qatar Airways", "KQ": "Kenya Airways"}
HOTEL_NAMES = ["Grand", "Skyline", "Garden", "Harbor", "Old Town", "Meridian", "Palm", "Summit"]
HOTEL_KINDS = ["Hotel", "Suites", "Inn", "Residence"]
# Fallback rates, used only when the live rate service can't be reached.
USD_RATES = {"USD": 1.0, "ETB": 155.0, "CAD": 1.40, "EUR": 0.92, "GBP": 0.79, "AED": 3.67, "KES": 129.0, "TRY": 41.0}


def _rng(*parts) -> random.Random:
    return random.Random("|".join(str(p).lower().strip() for p in parts))


def _demo_flights(origin: str, destination: str, day) -> list[dict]:
    rng = _rng("flight", origin, destination, day)
    base = rng.randint(180, 900)
    flights = []
    for code in rng.sample(list(AIRLINES), 4):
        stops = 0 if code == "ET" else rng.choice([0, 1, 1])
        depart = datetime.combine(day, datetime.min.time()) + timedelta(hours=rng.randint(1, 22), minutes=rng.choice([0, 15, 30, 45]))
        duration = timedelta(minutes=rng.randint(150, 420) + stops * rng.randint(90, 240))
        flights.append({
            "flight": f"{code}{rng.randint(100, 999)}",
            "airline": AIRLINES[code],
            "from": origin.upper(), "to": destination.upper(),
            "depart": depart.isoformat(timespec="minutes"),
            "arrive": (depart + duration).isoformat(timespec="minutes"),
            "duration_h": round(duration.total_seconds() / 3600, 1),
            "stops": stops,
            "price_usd": round(base * rng.uniform(0.8, 1.5) - stops * 40),
            "source": "demo",
        })
    return sorted(flights, key=lambda f: f["price_usd"])


def _demo_hotels(city: str, check_in: str, nights: int) -> list[dict]:
    rng = _rng("hotel", city, check_in)
    hotels = []
    for name in rng.sample(HOTEL_NAMES, 5):
        stars = rng.randint(3, 5)
        nightly = round(rng.uniform(25, 60) * stars)
        hotels.append({
            "name": f"{name} {rng.choice(HOTEL_KINDS)} {city.title()}",
            "stars": stars,
            "guest_rating": round(rng.uniform(7.2, 9.6), 1),
            "price_per_night_usd": nightly,
            "total_usd": nightly * nights,
            "free_cancellation": rng.random() > 0.4,
            "source": "demo",
        })
    return hotels


# ---------- Live suppliers (used when their keys are in .env; demo data otherwise) ----------

LIVE_SUPPLIERS = os.environ.get("SAFAR_LIVE_SUPPLIERS", "1") != "0"


def _supplier(name: str) -> str | None:
    return os.environ.get(name) if LIVE_SUPPLIERS else None


def _request_json(url: str, body: dict | None, headers: dict, timeout: float = 30) -> dict:
    """POST `body` as JSON, or GET when body is None."""
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 method="GET" if body is None else "POST", headers={
        "Content-Type": "application/json", "Accept": "application/json", "Accept-Encoding": "gzip", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(gzip.decompress(raw) if resp.headers.get("Content-Encoding") == "gzip" else raw)
    except urllib.error.HTTPError as e:  # surface the supplier's reason, never our credentials
        raise RuntimeError(f"supplier returned HTTP {e.code}") from None


def _iso_hours(duration: str) -> float:
    """ISO 8601 duration like PT5H32M or P1DT2H5M -> hours."""
    d, h, m = (int(x or 0) for x in re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", duration).groups())
    return round(d * 24 + h + m / 60, 1)


@functools.lru_cache(maxsize=64)
def _duffel_offers(origin: str, destination: str, day_iso: str, token: str) -> tuple:
    """Every bookable offer for a route and day, cheapest per flight. Cached: the search and the plan check share it."""
    data = _request_json(
        "https://api.duffel.com/air/offer_requests?return_offers=true&supplier_timeout=15000",
        {"data": {"slices": [{"origin": origin, "destination": destination, "departure_date": day_iso}],
                  "passengers": [{"type": "adult"}], "cabin_class": "economy"}},
        {"Duffel-Version": "v2", "Authorization": f"Bearer {token}"}, timeout=40)["data"]
    source = "duffel-test" if token.startswith("duffel_test_") else "duffel"
    best = {}
    for offer in data["offers"]:
        if offer["owner"]["iata_code"] == "ZZ":  # Duffel Airways: the sandbox's fictional airline
            continue
        segs = offer["slices"][0]["segments"]
        first = segs[0]
        flight = first["marketing_carrier"]["iata_code"] + first["marketing_carrier_flight_number"]
        price = float(offer["total_amount"])
        if offer["total_currency"] != "USD":
            price = convert_currency(price, offer["total_currency"], "USD")["amount"]
        key = (flight, first["departing_at"])
        if key not in best or price < best[key]["price_usd"]:
            best[key] = {
                "flight": flight + (f" +{len(segs) - 1}" if len(segs) > 1 else ""),
                "airline": offer["owner"]["name"],
                "from": first["origin"]["iata_code"], "to": segs[-1]["destination"]["iata_code"],
                "depart": first["departing_at"][:16],
                "arrive": segs[-1]["arriving_at"][:16],
                "duration_h": _iso_hours(offer["slices"][0]["duration"]),
                "stops": len(segs) - 1,
                "price_usd": round(price),
                "segments": [_flight_no(s["marketing_carrier"]["iata_code"] + s["marketing_carrier_flight_number"]) for s in segs],
                "source": source,
            }
    return tuple(best.values())


def _duffel_flights(origin: str, destination: str, day, token: str) -> list[dict]:
    ranked = sorted(_duffel_offers(origin, destination, day.isoformat(), token), key=lambda f: f["price_usd"])
    # Agents quote nonstops even when connections are cheaper: keep the two cheapest nonstops in the shortlist.
    nonstops = [f for f in ranked if f["stops"] == 0][:2]
    shortlist = [f for f in ranked if f not in nonstops][:6 - len(nonstops)] + nonstops
    return sorted(shortlist, key=lambda f: f["price_usd"])


def _liteapi_hotels(city: str, country_code: str, check_in: str, nights: int, adults: int, key: str) -> list[dict]:
    check_out = (datetime.fromisoformat(check_in) + timedelta(days=nights)).date().isoformat()
    resp = _request_json("https://api.liteapi.travel/v3.0/hotels/rates", {
        "cityName": city, "countryCode": country_code.upper(), "occupancies": [{"adults": adults}],
        "currency": "USD", "guestNationality": EDITION["guest_nationality"],  # ponytail: per edition, not per client
        "checkin": check_in, "checkout": check_out, "limit": 15, "timeout": 15,
    }, {"X-API-Key": key}, timeout=40)
    info = {h["id"]: h for h in resp.get("hotels", [])}
    source = "liteapi-sandbox" if resp.get("sandbox") else "liteapi"
    hotels = []
    for item in resp.get("data", []):
        cheapest = min(item["roomTypes"], key=lambda rt: rt["offerRetailRate"]["amount"])
        rate = cheapest["rates"][0]
        total = cheapest["offerRetailRate"]["amount"]
        if cheapest["offerRetailRate"]["currency"] != "USD":
            total = convert_currency(total, cheapest["offerRetailRate"]["currency"], "USD")["amount"]
        h = info.get(item["hotelId"], {})
        hotels.append({
            "name": h.get("name", item["hotelId"]),
            "stars": h.get("stars") or None,  # LiteAPI uses 0 for "unknown"
            "guest_rating": h.get("rating") or None,
            "room": f"{rate.get('name', '')}, {rate.get('boardName', '')}".strip(", "),
            "price_per_night_usd": round(total / nights),
            "total_usd": round(total),
            "free_cancellation": rate.get("cancellationPolicies", {}).get("refundableTag") == "RFN",
            "photo": h.get("main_photo"),
            "latitude": h.get("latitude"), "longitude": h.get("longitude"),
            "source": source,
        })
    return hotels


def _hotelbeds(suite: str, url: str, body: dict | None = None) -> dict:
    """Hotelbeds signs every request: X-Signature = sha256(api key + secret + unix seconds)."""
    key, secret = os.environ[f"HOTELBEDS_{suite}_ACCESS_TOKEN"], os.environ[f"HOTELBEDS_{suite}_SECRET"]
    signature = hashlib.sha256(f"{key}{secret}{int(time.time())}".encode()).hexdigest()
    return _request_json(url, body, {"Api-key": key, "X-Signature": signature}, timeout=40)


def _usd(amount: float, currency: str) -> int:
    return round(amount if currency == "USD" else convert_currency(amount, currency, "USD")["amount"])


# ponytail: per-day cache because the Hotelbeds evaluation keys allow 50 requests a day; drop it on production keys.
@functools.lru_cache(maxsize=128)
def _hotelbeds_transfers(airport: str, lat: float, lng: float, when: str, adults: int, day: str) -> tuple:
    data = _hotelbeds("TRANSFERS", f"https://api.test.hotelbeds.com/transfer-api/1.0/availability/en/from/IATA/{airport}"
                                   f"/to/GPS/{lat:.5f},{lng:.5f}/{when}/{adults}/0/0")
    best = {}
    for svc in data.get("services", []):
        price = _usd(svc["price"]["totalAmount"], svc["price"]["currencyId"])
        key = (svc["transferType"], svc["vehicle"]["name"], svc["category"]["name"])
        if key not in best or price < best[key]["price_usd"]:
            fees = sorted(svc.get("cancellationPolicies", []), key=lambda c: c["from"])
            best[key] = {
                "type": svc["transferType"].lower(),  # shared or private
                "vehicle": svc["vehicle"]["name"], "category": svc["category"]["name"],
                "max_passengers": svc.get("maxPaxCapacity"),
                "price_usd": price,  # whole party, one way
                "free_cancellation_until": fees[0]["from"][:16] if fees else None,
                "source": "hotelbeds-test",
            }
    return tuple(sorted(best.values(), key=lambda t: t["price_usd"]))


@functools.lru_cache(maxsize=128)
def _hotelbeds_activities(destination: str, start: str, end: str, adults: int, day: str) -> tuple:
    data = _hotelbeds("ACTIVITIES", "https://api.test.hotelbeds.com/activity-api/3.0/activities/availability", {
        "filters": [{"searchFilterItems": [{"type": "destination", "value": destination}]}],
        "from": start, "to": end, "language": "en", "paxes": [{"age": 30}] * adults,
        "pagination": {"itemsPerPage": 20, "page": 1}, "order": "DEFAULT"})
    out = []
    for act in data.get("activities", []):
        adult = next((a["amount"] for a in act.get("amountsFrom", []) if a.get("paxType") == "ADULT"), None)
        if not adult:
            continue
        content = act.get("content") or {}
        duration = (content.get("scheduling") or {}).get("duration") or {}
        images = (content.get("media") or {}).get("images") or []
        urls = images[0].get("urls", []) if images else []
        photo = next((u["resource"] for u in urls if "MEDIUM" in str(u.get("sizeType", "")).upper()), urls[0]["resource"] if urls else None)
        out.append({
            "name": act["name"], "code": act["code"],
            "price_per_adult_usd": _usd(adult, act.get("currency", "EUR")),
            "duration_h": duration.get("value") if duration.get("metric") == "HOURS" else None,
            "photo": photo,
            "source": "hotelbeds-test",
        })
    return tuple(sorted(out, key=lambda a: a["price_per_adult_usd"]))


def _demo_transfers(airport: str, adults: int) -> list[dict]:
    rng = _rng("transfer", airport)
    base = rng.randint(18, 40)
    options = [("shared", "Shuttle", "Standard", 99, 1.0), ("private", "Car", "Standard", 4, 1.6),
               ("private", "Minibus", "Standard", 8, 2.1), ("private", "Car", "Premium", 4, 2.8)]
    return [{"type": t, "vehicle": v, "category": c, "max_passengers": cap,
             "price_usd": round(base * k * (adults if t == "shared" else 1)), "free_cancellation_until": None, "source": "demo"}
            for t, v, c, cap, k in options if cap >= adults]


def _demo_activities(destination: str) -> list[dict]:
    rng = _rng("activity", destination)
    names = ["Old town walking tour", "Food and market tour", "Full-day highlights tour", "Sunset boat cruise", "Museum pass", "Day trip to the countryside"]
    return sorted(({"name": n, "code": f"DEMO-{i}", "price_per_adult_usd": rng.randint(25, 160),
                    "duration_h": rng.choice([3, 4, 8]), "photo": None, "source": "demo"} for i, n in enumerate(names)),
                  key=lambda a: a["price_per_adult_usd"])


def search_transfers(airport: str, latitude: float, longitude: float, pickup_datetime: str, adults: int = 2) -> list[dict]:
    """Airport -> hotel transfer options, one way, priced for the whole party."""
    when = datetime.fromisoformat(pickup_datetime).strftime("%Y-%m-%dT%H:%M:%S")
    lat, lng, adults, airport = float(latitude), float(longitude), int(adults), airport.strip().upper()
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("latitude/longitude out of range")
    if not 1 <= adults <= 20:
        raise ValueError("adults must be between 1 and 20")
    if _supplier("HOTELBEDS_TRANSFERS_SECRET"):
        try:
            if live := list(_hotelbeds_transfers(airport, round(lat, 5), round(lng, 5), when, adults, date.today().isoformat())):
                return [t for t in live if (t["max_passengers"] or 99) >= adults][:6]
        except Exception as e:
            print(f"[hotelbeds transfers] falling back to demo: {type(e).__name__}: {e}")
    return _demo_transfers(airport, adults)


def search_activities(destination_code: str, from_date: str, to_date: str, adults: int = 2) -> list[dict]:
    """Bookable tours and tickets at a destination between two dates."""
    start, end = datetime.fromisoformat(from_date).date(), datetime.fromisoformat(to_date).date()
    if not 0 <= (end - start).days <= 30:
        raise ValueError("to_date must be 0-30 days after from_date")
    code, adults = destination_code.strip().upper(), int(adults)
    if _supplier("HOTELBEDS_ACTIVITIES_SECRET"):
        try:
            if live := list(_hotelbeds_activities(code, start.isoformat(), end.isoformat(), adults, date.today().isoformat())):
                return live[:8]
        except Exception as e:
            print(f"[hotelbeds activities] falling back to demo: {type(e).__name__}: {e}")
    return _demo_activities(code)


# ---------- Plan audit: check a client's own (often AI-made) plan against suppliers ----------
# The model extracts items and writes the report; matching and verdicts are decided here, in code.

PRICE_TOLERANCE = 0.15  # within ±15% of the supplier price counts as verified
STOPWORDS = {"the", "a", "an", "and", "with", "of", "in", "at", "to", "tour", "visit", "hotel", "&", "-"}


def _flight_no(code: str) -> str:
    """'ET 704', 'et0704' -> 'ET704'."""
    code = re.sub(r"\s+", "", code.upper())
    m = re.fullmatch(r"([A-Z0-9]{2})0*(\d{1,4})[A-Z]?", code)
    if not m:
        raise ValueError(f"not a flight number: {code}")
    return m.group(1) + m.group(2)


def _words(name: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in STOPWORDS}


def _name_score(claimed: str, candidate: str) -> float:
    """0-1 similarity, used only to pick the closest candidate: the better of character similarity and word overlap."""
    wa, wb = _words(claimed), _words(candidate)
    overlap = len(wa & wb) / len(wa) if wa else 0.0
    return max(difflib.SequenceMatcher(None, claimed.lower(), candidate.lower()).ratio(), overlap)


def _same_name(claimed: str, candidate: str) -> bool:
    """Exact enough to call it the same place: every distinctive word the plan uses appears in the supplier's name.
    ('Bosphorus Sky Palace' vs 'Bosphorus Palace' is 92% similar but not the same hotel.)"""
    wa = _words(claimed)
    return bool(wa) and wa <= _words(candidate)


SUPPLIER_NAMES = {"duffel-test": "Duffel (test)", "duffel": "Duffel", "liteapi-sandbox": "LiteAPI (sandbox)",
                  "liteapi": "LiteAPI", "hotelbeds-test": "Hotelbeds (test)"}


def _verdict(item: str, claimed: float | None, actual: float | None, match: dict | None, source: str, what: str,
             exact: bool = True) -> dict:
    """The one place a verdict is decided. Returns the verdict plus a plain-language reason the model must quote."""
    result = {"item": item, "claimed_usd": claimed, "supplier_usd": actual, "diff_pct": None, "match": match, "source": source}
    source = SUPPLIER_NAMES.get(source, source)  # readable name for the reason text only
    if source == "unchecked":
        return {**result, "verdict": "unchecked", "reason": f"No {what} supplier is connected, so this was not checked."}
    if match is None:
        return {**result, "verdict": "not_found", "reason": f"Not found at {source}. It may not exist, or this supplier may not sell it."}
    if not exact:
        price = f" at ${actual:,}" if actual is not None else ""
        return {**result, "verdict": "name_mismatch",
                "reason": f"No exact match at {source}; the closest is {match['name']}{price}. Confirm it is the same place."}
    if actual is None:
        return {**result, "verdict": "unavailable", "reason": f"{match['name']} exists at {source} but has no availability for these dates."}
    if claimed is None:
        return {**result, "verdict": "verified", "reason": f"Found at {source} at ${actual:,}; the plan gave no price."}
    diff = round((actual - claimed) / claimed * 100)
    result["diff_pct"] = diff
    if abs(diff) <= PRICE_TOLERANCE * 100:
        return {**result, "verdict": "verified", "reason": f"Found at {source}; ${actual:,} is within 15% of the plan's ${claimed:,}."}
    direction = "higher" if diff > 0 else "lower"
    return {**result, "verdict": "price_off", "reason": f"Found at {source}, but the price is ${actual:,}, {abs(diff)}% {direction} than the plan's ${claimed:,}."}


def check_hotel(name: str, city: str, country_code: str, check_in: str, nights: int,
                claimed_price_per_night_usd: float | None = None, adults: int = 2) -> dict:
    """Does this hotel exist at the supplier, is it available on these dates, and is the plan's nightly price right?"""
    nights, adults = int(nights), int(adults)
    if not 1 <= nights <= 60:
        raise ValueError("nights must be between 1 and 60")
    claimed = round(float(claimed_price_per_night_usd)) if claimed_price_per_night_usd is not None else None
    key = _supplier("LITEAPI_ACCESS_TOKEN")
    if not key:
        return _verdict(name, claimed, None, None, "unchecked", "hotel")
    query = urllib.parse.urlencode({"countryCode": country_code.upper(), "cityName": city, "hotelName": name, "limit": 10})
    candidates = _request_json(f"https://api.liteapi.travel/v3.0/data/hotels?{query}", None, {"X-API-Key": key}).get("data", [])
    best = max(candidates, key=lambda h: _name_score(name, h["name"]), default=None)
    if not best or _name_score(name, best["name"]) < 0.6:
        return _verdict(name, claimed, None, None, "liteapi", "hotel")
    exact = _same_name(name, best["name"])
    match = {"name": best["name"], "stars": best.get("stars") or None, "guest_rating": best.get("rating") or None,
             "address": best.get("address"), "latitude": best.get("latitude"), "longitude": best.get("longitude"), "photo": best.get("main_photo")}
    check_out = (datetime.fromisoformat(check_in) + timedelta(days=nights)).date().isoformat()
    rates = _request_json("https://api.liteapi.travel/v3.0/hotels/rates", {
        "hotelIds": [best["id"]], "occupancies": [{"adults": adults}], "currency": "USD", "guestNationality": EDITION["guest_nationality"],
        "checkin": check_in, "checkout": check_out, "timeout": 15}, {"X-API-Key": key}, timeout=40)
    source = "liteapi-sandbox" if rates.get("sandbox") else "liteapi"
    room_types = [rt for item in rates.get("data", []) for rt in item["roomTypes"]]
    if not room_types:
        return _verdict(name, claimed, None, match, source, "hotel", exact)
    cheapest = min(room_types, key=lambda rt: rt["offerRetailRate"]["amount"])["offerRetailRate"]
    per_night = round(_usd(cheapest["amount"], cheapest["currency"]) / nights)
    return _verdict(name, claimed, per_night, match, source, "hotel", exact)


def check_flight(flight_number: str, origin: str, destination: str, date: str, claimed_price_usd: float | None = None) -> dict:
    """Does this flight operate on this date at the supplier, and is the plan's per-person fare right?"""
    wanted = _flight_no(flight_number)
    day = datetime.fromisoformat(date).date()
    claimed = round(float(claimed_price_usd)) if claimed_price_usd is not None else None
    token = _supplier("DUFFEL_ACCESS_TOKEN")
    if not token:
        return _verdict(flight_number, claimed, None, None, "unchecked", "flight")
    offers = _duffel_offers(origin.strip().upper(), destination.strip().upper(), day.isoformat(), token)
    source = offers[0]["source"] if offers else ("duffel-test" if token.startswith("duffel_test_") else "duffel")
    matching = [o for o in offers if wanted in o["segments"]]
    if not matching:
        result = _verdict(flight_number, claimed, None, None, source, "flight")
        cheapest = min(offers, key=lambda o: o["price_usd"], default=None)
        result["reason"] = (f"No {wanted} {origin.upper()}→{destination.upper()} on {day} at {SUPPLIER_NAMES.get(source, source)}"
                            + (f"; {len(offers)} other flights found, cheapest {cheapest['flight']} at ${cheapest['price_usd']:,}." if cheapest else "."))
        return result
    best = min(matching, key=lambda o: o["price_usd"])
    match = {"name": f"{best['flight']} {best['airline']}", "depart": best["depart"], "arrive": best["arrive"], "stops": best["stops"]}
    return _verdict(flight_number, claimed, best["price_usd"], match, source, "flight")


def check_activity(name: str, destination_code: str, date: str, claimed_price_per_adult_usd: float | None = None) -> dict:
    """Is this activity sold at the supplier on this date, and is the plan's per-adult price right?"""
    day = datetime.fromisoformat(date).date()
    claimed = round(float(claimed_price_per_adult_usd)) if claimed_price_per_adult_usd is not None else None
    if not _supplier("HOTELBEDS_ACTIVITIES_SECRET"):
        return _verdict(name, claimed, None, None, "unchecked", "activity")
    acts = _hotelbeds_activities(destination_code.strip().upper(), day.isoformat(), day.isoformat(), 2, date_today())
    best = max(acts, key=lambda a: _name_score(name, a["name"]), default=None)
    if not best or _name_score(name, best["name"]) < 0.6:
        return _verdict(name, claimed, None, None, "hotelbeds-test", "activity")
    match = {"name": best["name"], "duration_h": best["duration_h"], "photo": best["photo"]}
    return _verdict(name, claimed, best["price_per_adult_usd"], match, "hotelbeds-test", "activity", _same_name(name, best["name"]))


def date_today() -> str:
    return date.today().isoformat()


def search_flights(origin: str, destination: str, date: str) -> list[dict]:
    day = datetime.fromisoformat(date).date()  # raises ValueError on bad dates -> tool error
    origin, destination = origin.strip().upper(), destination.strip().upper()
    if origin == destination:
        raise ValueError("origin and destination are the same")
    if token := _supplier("DUFFEL_ACCESS_TOKEN"):
        try:
            if live := _duffel_flights(origin, destination, day, token):
                return live
        except Exception as e:  # supplier down or slow: keep the agent working, but say so in the data
            print(f"[duffel] falling back to demo: {type(e).__name__}: {e}")
    return _demo_flights(origin, destination, day)


def search_hotels(city: str, check_in: str, nights: int, max_price_per_night: float | None = None,
                  country_code: str | None = None, adults: int = 2) -> list[dict]:
    datetime.fromisoformat(check_in)
    nights, adults = int(nights), int(adults)
    if not 1 <= nights <= 60:
        raise ValueError("nights must be between 1 and 60")
    if not 1 <= adults <= 9:
        raise ValueError("adults must be between 1 and 9")
    hotels = []
    if (key := _supplier("LITEAPI_ACCESS_TOKEN")) and country_code:
        try:
            hotels = _liteapi_hotels(city, country_code, check_in, nights, adults, key)
        except Exception as e:
            print(f"[liteapi] falling back to demo: {type(e).__name__}: {e}")
    hotels = hotels or _demo_hotels(city, check_in, nights)
    if max_price_per_night is not None:
        hotels = [h for h in hotels if h["price_per_night_usd"] <= float(max_price_per_night)]
    return sorted(hotels, key=lambda h: h["price_per_night_usd"])[:6]


def inventory_note() -> str:
    flights = "Duffel" if _supplier("DUFFEL_ACCESS_TOKEN") else "demo inventory"
    hotels = "LiteAPI" if _supplier("LITEAPI_ACCESS_TOKEN") else "demo inventory"
    extras = "Hotelbeds" if _supplier("HOTELBEDS_TRANSFERS_SECRET") else "demo inventory"
    return (f"Flights come from {flights}, hotels from {hotels}, transfers and activities from {extras}; each result's 'source' says which. "
            "Sandbox and demo prices are not bookable fares. Exchange rates are live.")


LIVE_FX = os.environ.get("SAFAR_LIVE_FX", "1") != "0"


@functools.lru_cache(maxsize=256)
def _live_rate(src: str, dst: str, day: str) -> tuple[float, str, str]:
    """Today's rate from Frankfurter (free, no key). ETB uses the National Bank of Ethiopia's official rate.
    `day` is only the cache key, so rates refresh daily."""
    provider = "&providers=NBE" if "ETB" in (src, dst) else ""
    url = f"https://api.frankfurter.dev/v2/rate/{src}/{dst}?{provider.lstrip('&')}"
    req = urllib.request.Request(url, headers={"User-Agent": "safar-demo"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.load(resp)
    return float(data["rate"]), data["date"], "National Bank of Ethiopia" if provider else "Frankfurter"


def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    src, dst = from_currency.upper().strip(), to_currency.upper().strip()
    if len(src) != 3 or len(dst) != 3 or not (src + dst).isalpha():
        raise ValueError("currencies must be 3-letter ISO codes, e.g. USD, CAD, GBP")
    if src == dst:
        return {"amount": round(float(amount), 2), "currency": dst, "note": "same currency"}
    if LIVE_FX:
        try:
            rate, as_of, source = _live_rate(src, dst, date.today().isoformat())
            return {"amount": round(float(amount) * rate, 2), "currency": dst, "rate": rate, "note": f"live rate, {source}, {as_of}"}
        except Exception:  # network down or unknown pair -> fall back to the fixed table below
            pass
    if src not in USD_RATES or dst not in USD_RATES:
        raise ValueError(f"live rates unavailable; fallback supports {', '.join(USD_RATES)}")
    return {"amount": round(float(amount) / USD_RATES[src] * USD_RATES[dst], 2), "currency": dst, "note": "fallback demo rates"}


def price_quote(items: list[dict], currency: str = "USD", markup_pct: float = 0) -> dict:
    """Net USD items -> client prices. markup_pct is the agency's setting, injected by the server, never by the model."""
    if not items:
        raise ValueError("items must not be empty")
    lines = []
    for item in items:
        net = float(item["net_usd"])
        if net < 0:
            raise ValueError("net_usd must be >= 0")
        # Whole dollars per line, and the total is the sum of the lines, so the quote always adds up.
        lines.append({"label": str(item["label"]), "net_usd": round(net, 2), "client_usd": round(net * (1 + markup_pct / 100))})
    client_total = sum(line["client_usd"] for line in lines)
    fx = convert_currency(client_total, "USD", currency)
    rate = fx["amount"] / client_total if client_total else 0
    for line in lines:  # each line in the client's currency, so the table and the total always agree
        line["client_local"] = round(line["client_usd"] * rate)
    return {
        "lines": lines,
        "markup_pct": markup_pct,
        "net_total_usd": round(sum(line["net_usd"] for line in lines), 2),
        "client_total_usd": client_total,
        "client_total_local": {**fx, "amount": float(sum(line["client_local"] for line in lines))},
    }


TOOL_FNS = {f.__name__: f for f in (search_flights, search_hotels, search_transfers, search_activities,
                                     check_flight, check_hotel, check_activity, convert_currency, price_quote)}

TOOLS = [
    {
        "name": "search_flights",
        "description": "Search one-way flights for a single date. For a round trip, call it twice (outbound and return). "
                       "Returns up to 6 options sorted by price, per adult in USD, each with its data source.",
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "IATA airport/city code, e.g. ADD"},
                "destination": {"type": "string", "description": "IATA airport/city code, e.g. IST"},
                "date": {"type": "string", "description": "Departure date, YYYY-MM-DD"},
            },
            "required": ["origin", "destination", "date"],
        },
    },
    {
        "name": "search_hotels",
        "description": "Search hotels in a city for one room. Returns up to 6 options sorted by nightly price (USD, whole room), each with its data source.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name, e.g. Istanbul"},
                "country_code": {"type": "string", "description": "ISO 3166-1 alpha-2 code of the city's country, e.g. TR"},
                "adults": {"type": "integer", "minimum": 1, "description": "Guests sharing one room, default 2"},
                "check_in": {"type": "string", "description": "YYYY-MM-DD"},
                "nights": {"type": "integer", "minimum": 1},
                "max_price_per_night": {"type": "number", "description": "Optional USD cap per night"},
            },
            "required": ["city", "country_code", "check_in", "nights"],
        },
    },
    {
        "name": "search_transfers",
        "description": "Airport-to-hotel transfer options (shared shuttle, private car, minibus), one way, priced in USD for the whole party. "
                       "Use the chosen hotel's latitude/longitude from search_hotels; for the return trip, quote the same option again.",
        "input_schema": {
            "type": "object",
            "properties": {
                "airport": {"type": "string", "description": "Arrival airport IATA code, e.g. IST"},
                "latitude": {"type": "number"}, "longitude": {"type": "number"},
                "pickup_datetime": {"type": "string", "description": "Flight arrival, YYYY-MM-DDTHH:MM"},
                "adults": {"type": "integer", "minimum": 1},
            },
            "required": ["airport", "latitude", "longitude", "pickup_datetime"],
        },
    },
    {
        "name": "search_activities",
        "description": "Bookable tours, tickets and day trips at a destination between two dates, with price per adult in USD.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination_code": {"type": "string", "description": "Destination code, usually the city's IATA code, e.g. IST, BCN, DXB"},
                "from_date": {"type": "string", "description": "YYYY-MM-DD"},
                "to_date": {"type": "string", "description": "YYYY-MM-DD, within 30 days of from_date"},
                "adults": {"type": "integer", "minimum": 1},
            },
            "required": ["destination_code", "from_date", "to_date"],
        },
    },
    {
        "name": "check_hotel",
        "description": "Audit a hotel named in a client's own plan: does it exist at the supplier, is it available, is the plan's nightly price right? "
                       "Returns a verdict decided in code (verified / price_off / name_mismatch / unavailable / not_found / unchecked) and a reason to quote.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Hotel name exactly as the plan gives it"},
                "city": {"type": "string"}, "country_code": {"type": "string", "description": "ISO 3166-1 alpha-2, e.g. TR"},
                "check_in": {"type": "string", "description": "YYYY-MM-DD"}, "nights": {"type": "integer", "minimum": 1},
                "claimed_price_per_night_usd": {"type": "number", "description": "The plan's nightly price, if it gives one"},
                "adults": {"type": "integer", "minimum": 1},
            },
            "required": ["name", "city", "country_code", "check_in", "nights"],
        },
    },
    {
        "name": "check_flight",
        "description": "Audit a flight named in a client's own plan: does that flight number operate on that date, and is the plan's per-person fare right?",
        "input_schema": {
            "type": "object",
            "properties": {
                "flight_number": {"type": "string", "description": "e.g. TK 677"},
                "origin": {"type": "string"}, "destination": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "claimed_price_usd": {"type": "number", "description": "The plan's per-person fare, if it gives one"},
            },
            "required": ["flight_number", "origin", "destination", "date"],
        },
    },
    {
        "name": "check_activity",
        "description": "Audit a tour or activity named in a client's own plan: is it sold at the supplier on that date, and is the plan's per-adult price right?",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"}, "destination_code": {"type": "string", "description": "City IATA code, e.g. IST"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "claimed_price_per_adult_usd": {"type": "number"},
            },
            "required": ["name", "destination_code", "date"],
        },
    },
    {
        "name": "convert_currency",
        "description": "Convert an amount between currencies (3-letter ISO codes) at today's live rate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "from_currency": {"type": "string"},
                "to_currency": {"type": "string"},
            },
            "required": ["amount", "from_currency", "to_currency"],
        },
    },
    {
        "name": "price_quote",
        "description": "Turn the chosen items' net USD prices into client prices: applies the agency markup and converts the total. "
                       "Call once per proposal, after searching, with every bookable item priced for the whole party.",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "e.g. 'Hotel: Garden Suites, 5 nights'"},
                            "net_usd": {"type": "number", "description": "Net total in USD for this item"},
                        },
                        "required": ["label", "net_usd"],
                    },
                },
                "currency": {"type": "string", "description": "Client's currency as a 3-letter ISO code; defaults to the agency's quoting currency."},
            },
            "required": ["items"],
        },
    },
]


def run_tool(name: str, args: dict, markup_pct: float = 0, currency: str = "USD") -> tuple[str, bool]:
    if name == "price_quote":
        # The agency's markup wins over anything the model sends; its quoting currency is only the default.
        args = {"currency": currency, **args, "markup_pct": markup_pct}
    if name not in TOOL_FNS:
        return f"unknown tool {name}", True
    try:
        return json.dumps(TOOL_FNS[name](**args)), False
    except (TypeError, ValueError, KeyError) as e:  # bad/missing args from the model -> let it correct itself
        return f"invalid input: {e}", True
    except Exception as e:  # supplier down mid-check: report it to the model rather than ending the turn
        return f"tool failed: {type(e).__name__}: {e}", True


# ---------- Agent loop ----------

def sse(kind: str, data=None) -> str:
    return f"data: {json.dumps({'type': kind, 'data': data})}\n\n"


def system_prompt(currency: str) -> str:
    return SYSTEM.format(today=date.today().isoformat(), inventory=inventory_note(), currency=currency,
                         agency=EDITION["agency"], example_item=EDITION["example_item"],
                         usd_note="" if currency == "USD" else ", with USD alongside")


async def agent_turn(history: list, user_message: str, markup_pct: float = 0, currency: str | None = None,
                     provider: str | None = None, model: str | None = None):
    """Run one user turn on the configured provider. If the turn doesn't finish (error, refusal, client disconnect),
    it is rolled back so the session history stays valid for the next request."""
    currency = currency if currency in EDITION["currencies"] else EDITION["currencies"][0]
    start = len(history)
    history.append({"role": "user", "content": user_message})
    finished = False
    provider = provider or DEFAULT_PROVIDER
    model = model or DEFAULT_MODEL
    turn = _claude_turn if PROVIDERS[provider]["kind"] == "anthropic" else _openai_turn
    try:
        async for chunk in turn(history, markup_pct, currency, provider, model):
            finished = chunk.startswith('data: {"type": "done"')
            yield chunk
    finally:
        if not finished:
            del history[start:]


async def _run_tools(calls: list, first_coupon: int, markup_pct: float, currency: str, results: dict):
    """Run one model step's tool calls concurrently, streaming each result as it lands.
    calls: [(call_id, name, args or None if the model sent unparseable JSON)]. Fills results[call_id] = (coupon, output, is_error)."""
    numbers = {cid: first_coupon + i for i, (cid, _, _) in enumerate(calls)}  # numbered per turn so the proposal can cite them
    for cid, name, args in calls:
        yield sse("tool_call", {"id": cid, "coupon": numbers[cid], "name": name, "input": args or {}})

    async def run(cid, name, args):
        if args is None:
            return cid, ("invalid input: the tool arguments were not valid JSON", True)
        # Supplier calls block, so each tool runs in a thread: a 20 s hotel search no longer holds up the flights.
        return cid, await asyncio.to_thread(run_tool, name, args, markup_pct, currency)

    tasks = [asyncio.create_task(run(*call)) for call in calls]
    try:
        for next_done in asyncio.as_completed(tasks):
            cid, (output, is_error) = await next_done
            yield sse("tool_result", {"id": cid, "output": output, "is_error": is_error})
            results[cid] = (numbers[cid], output, is_error)
    finally:
        for task in tasks:
            task.cancel()


FALLBACK_MODELS = {"claude-opus-5", "claude-fable-5-1"}  # models documented for server-side refusal fallbacks


def _claude_params(model: str) -> dict:
    params = {}
    if not model.startswith("claude-haiku"):  # Haiku 4.5 has no adaptive thinking
        params["thinking"] = {"type": "adaptive", "display": "summarized"}
    if model in FALLBACK_MODELS:  # on a safety decline, the API retries on a recommended fallback model
        params.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    return params


async def _claude_turn(history: list, markup_pct: float, currency: str, provider: str, model: str):
    coupon = 1
    client = _client_for(provider)
    try:
        while True:
            async with client.beta.messages.stream(
                model=model, max_tokens=64000, system=system_prompt(currency), tools=TOOLS, messages=history,
                cache_control={"type": "ephemeral"}, **_claude_params(model),
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield sse("text", event.delta.text)
                        elif event.delta.type == "thinking_delta":
                            yield sse("thinking", event.delta.thinking)
                msg = await stream.get_final_message()

            history.append({"role": "assistant", "content": msg.content})
            if msg.stop_reason == "refusal":
                yield sse("error", "The model declined this request.")
                return
            tool_uses = [b for b in msg.content if b.type == "tool_use"]
            if not tool_uses:
                yield sse("done", {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens})
                return
            if msg.stop_reason == "max_tokens":
                yield sse("error", "Response was cut off mid tool call.")
                return
            results = {}
            async for chunk in _run_tools([(b.id, b.name, b.input) for b in tool_uses], coupon, markup_pct, currency, results):
                yield chunk
            coupon += len(tool_uses)
            # All results in one message, in call order: keeps the model making parallel calls.
            history.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": b.id, "content": f"CPN {results[b.id][0]:02d}\n{results[b.id][1]}",
                 "is_error": results[b.id][2]} for b in tool_uses]})
    except anthropic.RateLimitError:
        yield sse("error", "Rate limited, try again in a moment.")
    except anthropic.APIStatusError as e:
        yield sse("error", f"API error {e.status_code}")
    except anthropic.APIConnectionError:
        yield sse("error", "Could not reach the model API.")
    except TypeError as e:
        if "authentication" not in str(e):
            raise
        yield sse("error", "No Anthropic API key. Add one in Settings (the Model button), or choose another provider.")


OPENAI_TOOLS = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
                for t in TOOLS]


async def _openai_turn(history: list, markup_pct: float, currency: str, provider: str, model: str):
    """Same loop for any OpenAI-compatible chat-completions endpoint. Tool calls arrive as streamed fragments
    (id and name first, arguments in pieces), so they are assembled by index before running."""
    import openai
    coupon = 1
    oai = _client_for(provider)
    try:
        while True:
            stream = await oai.chat.completions.create(
                model=model, messages=[{"role": "system", "content": system_prompt(currency)}, *history],
                tools=OPENAI_TOOLS, stream=True, stream_options={"include_usage": True})
            text, calls, usage = "", {}, None
            async for chunk in stream:
                usage = chunk.usage or usage
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                # Reasoning models on OpenRouter (and DeepSeek-style servers) stream their thinking in an extra field.
                if thought := getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None):
                    yield sse("thinking", thought)
                if delta.content:
                    text += delta.content
                    yield sse("text", delta.content)
                for part in delta.tool_calls or []:
                    call = calls.setdefault(part.index, {"id": "", "name": "", "args": ""})
                    call["id"] = part.id or call["id"]
                    if part.function:
                        call["name"] += part.function.name or ""
                        call["args"] += part.function.arguments or ""

            parsed = []
            for i, call in sorted(calls.items()):
                call["id"] = call["id"] or f"call_{uuid.uuid4().hex[:12]}"  # some local servers omit ids
                try:
                    args = json.loads(call["args"] or "{}")
                    args = args if isinstance(args, dict) else None
                except json.JSONDecodeError:
                    args = None
                parsed.append((call["id"], call["name"], args))
            history.append({"role": "assistant", "content": text or None, **({"tool_calls": [
                {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["args"] or "{}"}}
                for _, c in sorted(calls.items())]} if calls else {})})
            if not calls:
                yield sse("done", {"input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                                   "output_tokens": getattr(usage, "completion_tokens", 0) or 0})
                return
            results = {}
            async for chunk in _run_tools(parsed, coupon, markup_pct, currency, results):
                yield chunk
            coupon += len(parsed)
            for cid, _, _ in parsed:
                n, output, _ = results[cid]
                history.append({"role": "tool", "tool_call_id": cid, "content": f"CPN {n:02d}\n{output}"})
    except openai.RateLimitError:
        yield sse("error", "Rate limited, try again in a moment.")
    except openai.AuthenticationError:
        yield sse("error", f"{PROVIDERS[provider]['label']} rejected the API key. Update it in Settings.")
    except openai.APIStatusError as e:
        if "support tool use" in str(e.message):
            yield sse("error", f"{model} can't call tools on {PROVIDERS[provider]['label']} right now, and Safar's agent "
                               "needs tools to search. Choose another model in Settings.")
        else:
            yield sse("error", f"Model API error {e.status_code}: {str(e.message)[:200]}")
    except openai.APIConnectionError:
        yield sse("error", f"Could not reach {PROVIDERS[provider]['label']} at {oai.base_url}. Is it running?")


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=4000)
    markup_pct: float = Field(default=10, ge=0, le=100)
    currency: str | None = Field(default=None, max_length=3)
    provider: str | None = Field(default=None, max_length=20)
    model: str | None = Field(default=None, max_length=120)


@app.post("/api/chat")
async def chat(req: ChatRequest):
    provider = req.provider or DEFAULT_PROVIDER
    if provider not in PROVIDERS:
        raise HTTPException(400, f"Unknown provider {provider!r}.")
    model = (req.model or (DEFAULT_MODEL if provider == DEFAULT_PROVIDER else "")).strip()
    allowed = PROVIDERS[provider].get("models")
    if not model or not MODEL_NAME.fullmatch(model) or (PROVIDERS[provider]["kind"] == "anthropic" and model not in allowed):
        raise HTTPException(400, f"Choose a model for {PROVIDERS[provider]['label']} in Settings.")
    if problem := await asyncio.to_thread(model_problem, provider, model):
        raise HTTPException(400, problem)
    kind = PROVIDERS[provider]["kind"]
    session = SESSIONS.get(req.session_id or "")
    if not session or session["kind"] != kind:  # a trip's history belongs to one message format
        req.session_id = str(uuid.uuid4())
        session = SESSIONS[req.session_id] = {"kind": kind, "history": []}
    session_id, history = req.session_id, session["history"]

    async def events():
        yield sse("session", session_id)
        async for chunk in agent_turn(history, req.message, req.markup_pct, req.currency, provider, model):
            yield chunk

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ---------- Settings: pick models and store keys, only from the machine running Safar ----------

def _settings_allowed(request: Request) -> bool:
    """Local requests only, and only from this page: the custom header can't be sent cross-site without a CORS
    preflight (which this server never grants), so another website open in the browser can't change keys."""
    host = request.client.host if request.client else ""
    origin = request.headers.get("origin")
    return (host in ("127.0.0.1", "::1") and "x-forwarded-for" not in request.headers
            and request.headers.get("x-safar-settings") == "1"
            and (origin is None or origin == f"http://{request.headers.get('host')}"))


def _write_env(name: str, value: str) -> None:
    """Set NAME=value in .env (or remove it when value is empty), keeping every other line as it was."""
    path = Path(__file__).parent / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = [line for line in lines if line.partition("=")[0].strip() != name]
    if value:
        lines.append(f"{name}={value}")
        os.environ[name] = value
    else:
        os.environ.pop(name, None)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class SettingsRequest(BaseModel):
    provider: str = Field(max_length=20)
    api_key: str | None = Field(default=None, max_length=400)
    base_url: str | None = Field(default=None, max_length=300)


@app.get("/api/providers")
async def providers(request: Request):
    states = await asyncio.gather(*(asyncio.to_thread(provider_state, pid) for pid in PROVIDERS))
    return {"providers": states, "default": {"provider": DEFAULT_PROVIDER, "model": DEFAULT_MODEL},
            "editable": request.client is not None and request.client.host in ("127.0.0.1", "::1")
                        and "x-forwarded-for" not in request.headers}


@app.get("/api/model-check")
async def model_check(provider: str, model: str):
    if provider not in PROVIDERS or not MODEL_NAME.fullmatch(model):
        raise HTTPException(400, "Unknown provider or model.")
    problem = await asyncio.to_thread(model_problem, provider, model)
    return {"ok": problem is None, "reason": problem}


@app.post("/api/settings")
async def save_settings(body: SettingsRequest, request: Request):
    if not _settings_allowed(request):
        raise HTTPException(403, "Settings can only be changed on the computer running Safar.")
    p = PROVIDERS.get(body.provider)
    if not p:
        raise HTTPException(400, "Unknown provider.")
    if body.api_key is not None:
        if not p.get("key_env"):
            raise HTTPException(400, f"{p['label']} doesn't use an API key.")
        if body.api_key and not re.fullmatch(r"[\x21-\x7e]{8,400}", body.api_key):
            raise HTTPException(400, "That doesn't look like an API key (no spaces, at least 8 characters).")
        _write_env(p["key_env"], body.api_key)
    if body.base_url is not None:
        if not p.get("url_env"):
            raise HTTPException(400, f"{p['label']} has a fixed address.")
        if body.base_url and not re.fullmatch(r"https?://[^\s]+", body.base_url):
            raise HTTPException(400, "The base URL must start with http:// or https://.")
        _write_env(p["url_env"], body.base_url.rstrip("/"))
    return await asyncio.to_thread(provider_state, body.provider)


@app.get("/api/status")
async def status():
    """Which data sources are live, so the UI labels prices honestly."""
    duffel = _supplier("DUFFEL_ACCESS_TOKEN") or ""
    return {
        "flights": ("duffel-test" if duffel.startswith("duffel_test_") else "duffel") if duffel else "demo",
        "hotels": "liteapi" if _supplier("LITEAPI_ACCESS_TOKEN") else "demo",
        "transfers": "hotelbeds-test" if _supplier("HOTELBEDS_TRANSFERS_SECRET") else "demo",
        "activities": "hotelbeds-test" if _supplier("HOTELBEDS_ACTIVITIES_SECRET") else "demo",
        "fx": "live" if LIVE_FX else "demo",
        "edition": EDITION_NAME,
        "provider": DEFAULT_PROVIDER,
        "model": DEFAULT_MODEL,
        "currencies": EDITION["currencies"],
    }


@app.get("/")
async def landing():
    page = (STATIC / "landing.html").read_text(encoding="utf-8")
    for key, value in EDITION["landing"].items():
        page = page.replace(f"%%{key}%%", html.escape(value))
    return HTMLResponse(page)


@app.get("/app")
async def trip_desk():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
