"""Tool and tool-dispatch checks. Run: python test_app.py (or pytest). No API key needed."""

import json

import app
from app import convert_currency, run_tool, search_flights, search_hotels

app.LIVE_FX = False  # tests use the fixed fallback rates, never the network
app.LIVE_SUPPLIERS = False  # and demo inventory, never Duffel or LiteAPI


def test_tools():
    # Deterministic demo inventory: same query, same answer, sorted cheapest first.
    a = search_flights("ADD", "IST", "2026-11-12")
    assert a == search_flights("add", "ist", "2026-11-12")
    assert [f["price_usd"] for f in a] == sorted(f["price_usd"] for f in a)

    hotels = search_hotels("Istanbul", "2026-11-12", 5, max_price_per_night=150)
    assert all(h["price_per_night_usd"] <= 150 for h in hotels)
    assert all(h["total_usd"] == h["price_per_night_usd"] * 5 for h in hotels)

    assert convert_currency(100, "USD", "ETB")["amount"] == 15500.0

    # Bad model input becomes an error result the model can correct, never an exception.
    for name, args in [
        ("search_flights", {"origin": "ADD", "destination": "ADD", "date": "2026-11-12"}),
        ("search_flights", {"origin": "ADD", "destination": "IST", "date": "next friday"}),
        ("search_hotels", {"city": "Nairobi"}),
        ("search_hotels", {"city": "Nairobi", "check_in": "2026-11-12", "nights": 0}),
        ("convert_currency", {"amount": 1, "from_currency": "USD", "to_currency": "XYZ"}),
        ("book_flight", {}),
    ]:
        out, is_error = run_tool(name, args)
        assert is_error, (name, args, out)

    out, is_error = run_tool("search_hotels", {"city": "Dubai", "check_in": "2026-12-01", "nights": "3"})
    assert not is_error and json.loads(out)[0]["total_usd"] > 0



def test_transfers_and_activities():
    t = json.loads(run_tool("search_transfers", {"airport": "IST", "latitude": 41.0086, "longitude": 28.9802,
                                                 "pickup_datetime": "2026-11-20T14:00", "adults": 5})[0])
    assert t and all(x["max_passengers"] >= 5 for x in t) and all(x["source"] == "demo" for x in t)
    acts = json.loads(run_tool("search_activities", {"destination_code": "ist", "from_date": "2026-11-20", "to_date": "2026-11-24"})[0])
    assert [x["price_per_adult_usd"] for x in acts] == sorted(x["price_per_adult_usd"] for x in acts)
    for name, args in [
        ("search_transfers", {"airport": "IST", "latitude": 141, "longitude": 28, "pickup_datetime": "2026-11-20T14:00"}),
        ("search_transfers", {"airport": "IST", "latitude": 41, "longitude": 28, "pickup_datetime": "tomorrow"}),
        ("search_activities", {"destination_code": "IST", "from_date": "2026-11-24", "to_date": "2026-11-20"}),
    ]:
        assert run_tool(name, args)[1], (name, args)



def test_plan_audit_verdicts():
    from app import _flight_no, _same_name, _verdict
    assert _flight_no("TK 677") == _flight_no("tk0677") == "TK677"
    assert _same_name("Hagia Sophia audioguide", "Visit Hagia Sophia with Audioguide")
    assert not _same_name("Bosphorus Sky Palace Hotel", "Bosphorus Palace Hotel")  # 92% similar, different hotel
    m = {"name": "X"}
    assert _verdict("x", 100, 110, m, "s", "hotel")["verdict"] == "verified"      # +10% is within tolerance
    v = _verdict("x", 100, 140, m, "s", "hotel")
    assert v["verdict"] == "price_off" and v["diff_pct"] == 40
    assert _verdict("x", 100, None, None, "s", "hotel")["verdict"] == "not_found"
    assert _verdict("x", 100, None, m, "s", "hotel")["verdict"] == "unavailable"
    assert _verdict("x", 100, 100, m, "s", "hotel", exact=False)["verdict"] == "name_mismatch"
    # With no supplier connected, nothing is claimed as verified.
    out = json.loads(run_tool("check_hotel", {"name": "Conrad", "city": "Istanbul", "country_code": "TR", "check_in": "2026-11-20", "nights": 2})[0])
    assert out["verdict"] == "unchecked"


def test_price_quote():
    items = [{"label": "Flights x2", "net_usd": 1356}, {"label": "Hotel 5 nights", "net_usd": 905.5}]
    # Markup comes from the agency setting; a markup the model sneaks into the args is overridden.
    out, is_error = run_tool("price_quote", {"items": items, "markup_pct": 0}, markup_pct=10, currency="ETB")
    q = json.loads(out)
    assert not is_error and q["markup_pct"] == 10
    assert [line["client_usd"] for line in q["lines"]] == [1492, 996]
    assert q["client_total_usd"] == 2488 == sum(line["client_usd"] for line in q["lines"])
    assert q["client_total_local"] == {"amount": 385640.0, "currency": "ETB", "note": "fallback demo rates"}
    assert sum(line["client_local"] for line in q["lines"]) == q["client_total_local"]["amount"]  # table adds up

    # The agency's currency is the default; a currency the model chooses for this client wins.
    assert json.loads(run_tool("price_quote", {"items": items}, 10, "CAD")[0])["client_total_local"]["currency"] == "CAD"
    assert json.loads(run_tool("price_quote", {"items": items, "currency": "GBP"}, 10, "CAD")[0])["client_total_local"]["currency"] == "GBP"

    for bad in ([], [{"label": "x"}], [{"label": "x", "net_usd": -5}], ["flights"]):
        assert run_tool("price_quote", {"items": bad}, markup_pct=10)[1], bad


if __name__ == "__main__":
    test_tools()
    test_transfers_and_activities()
    test_plan_audit_verdicts()
    test_price_quote()
    print("ok")
