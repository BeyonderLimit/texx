import asyncio
import json
from types import SimpleNamespace

import pytest

from core.events import EventBus
from core.executor import Executor
from core.router import IntentRouter
from core.state import StateManager
from services.search import OnlineError
from services.settings import Settings
from services.weather import WeatherProvider
from storage.database import Database


def make(tmp_path):
    db = Database(tmp_path / "w.db")
    settings = Settings(db, EventBus())
    states = StateManager(EventBus())
    system = SimpleNamespace(open_map=lambda: {}, close_map=lambda: {})
    executor = Executor(EventBus(), states, settings, system)
    router = IntentRouter(settings)
    ctx = SimpleNamespace(settings=settings, states=states, system=system,
                          reminders=executor.ctx.reminders, time=executor.ctx.time,
                          memory=executor.ctx.memory, tasks=executor.ctx.tasks,
                          cache=executor.ctx.cache, web=executor.ctx.web,
                          wiki=executor.ctx.wiki, files=executor.ctx.files,
                          weather=executor.ctx.weather)
    return ctx, router, executor


async def ask(ctx, router, executor, text):
    command = router.route(text)
    return command, await executor.execute(command)


def _day(date, maxc, minc, desc="Sunny", rain="9"):
    to_f = lambda c: str(c * 9 // 5 + 32)
    return {
        "date": date,
        "maxtempC": str(maxc), "mintempC": str(minc),
        "maxtempF": to_f(maxc), "mintempF": to_f(minc),
        "hourly": [
            {"time": "900", "chanceofrain": rain, "weatherDesc": [{"value": desc}]},
            {"time": "1500", "chanceofrain": rain, "weatherDesc": [{"value": desc}]},
            {"time": "2100", "chanceofrain": "5", "weatherDesc": [{"value": desc}]},
        ],
    }


SAMPLE_J1 = json.dumps({
    "current_condition": [{
        "temp_C": "25", "temp_F": "77", "FeelsLikeC": "26", "FeelsLikeF": "78",
        "weatherDesc": [{"value": "Sunny"}], "humidity": "63",
    }],
    "nearest_area": [{
        "areaName": [{"value": "New Haven"}],
        "region": [{"value": "Connecticut"}],
        "country": [{"value": "United States of America"}],
    }],
    "weather": [
        _day("2026-08-26", 25, 16),
        _day("2026-08-27", 27, 18, desc="Light rain shower", rain="65"),
        _day("2026-08-28", 29, 19, desc="Partly cloudy", rain="20"),
    ],
})


class FakeWeather:
    """Returns parsed-shaped data; records the location it was asked for."""

    def __init__(self, data=None):
        self.calls = []
        self.data = data or json.loads(SAMPLE_J1)

    def current(self, location=None):
        self.calls.append(location)
        return WeatherProvider._parse(json.dumps(self.data))


def test_parser_extracts_current_place_and_forecasts():
    data = WeatherProvider._parse(SAMPLE_J1)
    assert data["place"] == "New Haven, Connecticut"
    cur = data["current"]
    assert cur["temp_c"] == 25 and cur["temp_f"] == 77 and cur["desc"] == "Sunny"
    assert len(data["forecasts"]) == 3
    day0 = data["forecasts"][0]
    assert day0["max_c"] == 25 and day0["min_c"] == 16
    assert day0["rain_pct"] == 9


@pytest.mark.parametrize("raw", ["not json at all", "{}"])
def test_parser_rejects_garbage(raw):
    try:
        WeatherProvider._parse(raw)
        raise AssertionError("should have raised")
    except OnlineError:
        pass


def test_weather_routing(tmp_path):
    ctx, router, _ = make(tmp_path)
    assert router.route("weather").intent == "weather.query"
    assert router.route("what's the weather like tomorrow?").slots == {
        "day": "tomorrow", "condition": ""}
    command = router.route("will it rain today?")
    assert command.intent == "weather.query" and command.slots["condition"] == "rain"
    # no collateral damage on neighbouring intents
    assert router.route("status").intent == "system.status"
    assert router.route("what's my battery level?").intent == "info.query"


def test_set_location_persists_and_is_used(tmp_path):
    ctx, router, executor = make(tmp_path)
    fake = FakeWeather()
    executor.ctx.weather = fake

    _, response = asyncio.run(ask(ctx, router, executor, "set my location to new haven"))
    assert response == "Location set to new haven."
    assert ctx.settings.get("location") == "new haven"

    _, response = asyncio.run(ask(ctx, router, executor, "weather"))
    assert fake.calls == ["new haven"]
    assert "rough guess from your IP" not in response


def test_auto_location_hint_when_unset(tmp_path):
    ctx, router, executor = make(tmp_path)
    fake = FakeWeather()
    executor.ctx.weather = fake
    _, response = asyncio.run(ask(ctx, router, executor, "weather"))
    assert fake.calls == [None]
    assert "set location to" in response


def test_weather_offline_message(tmp_path):
    ctx, router, executor = make(tmp_path)

    class Down:
        def current(self, location=None):
            raise OnlineError("network unavailable (URLError)")

    executor.ctx.weather = Down()
    _, response = asyncio.run(ask(ctx, router, executor, "weather forecast"))
    assert "unavailable" in response


def test_weather_cache_second_call(tmp_path):
    ctx, router, executor = make(tmp_path)
    calls = {"n": 0}

    class Counting:
        def current(self, location=None):
            calls["n"] += 1
            return WeatherProvider._parse(SAMPLE_J1)

    executor.ctx.weather = Counting()
    r1 = asyncio.run(ask(ctx, router, executor, "weather"))[1]
    r2 = asyncio.run(ask(ctx, router, executor, "what is the weather like?"))[1]
    assert calls["n"] == 1
    assert "(cached)" not in r1
    assert "(cached)" in r2


def test_tomorrow_forecast_selection(tmp_path):
    ctx, router, executor = make(tmp_path)
    executor.ctx.weather = FakeWeather()
    _, response = asyncio.run(ask(ctx, router, executor, "weather tomorrow"))
    assert "Tomorrow" in response
    assert "27°C" in response and "rain chance up to 65%" in response


def test_condition_question_answers_from_data(tmp_path):
    ctx, router, executor = make(tmp_path)
    executor.ctx.weather = FakeWeather()

    rainy_day = asyncio.run(ask(ctx, router, executor, "will it rain tomorrow"))[1]
    assert "Yes" in rainy_day

    dry = asyncio.run(ask(ctx, router, executor, "will it rain today"))[1]
    assert "Probably not" in dry

    sunny_ask = asyncio.run(ask(ctx, router, executor, "will it be sunny tomorrow"))[1]
    assert "Probably not" in sunny_ask  # that day forecasts a rain shower


def test_brief_includes_and_omits_weather(tmp_path):
    ctx, router, executor = make(tmp_path)
    executor.ctx.weather = FakeWeather()
    asyncio.run(ask(ctx, router, executor, "weather"))  # warm the 30-min cache
    with_wx = asyncio.run(ask(ctx, router, executor, "brief"))[1]
    assert "Weather in New Haven" in with_wx

    class Down:
        def current(self, location=None):
            raise OnlineError("network unavailable")

    # stale/expired cache entry -> no section at all; brief never goes online
    executor.ctx.weather = Down()
    executor.ctx.cache.set(_wx_cache_key(executor.ctx), {"stale": True}, ttl_seconds=-1)
    without_wx = asyncio.run(ask(ctx, router, executor, "brief"))[1]
    assert "TODAY" in without_wx and "Weather" not in without_wx


def _wx_cache_key(ctx):
    from core.executor import _weather_key
    return _weather_key(ctx)


def test_full_suite_fixture_shape_still_live(tmp_path):
    # Guard against drift from wttr.in's real j1: parser must handle a payload
    # whose hourly buckets carry string times like "900"/"1500".
    weird = json.dumps({
        "current_condition": [{"temp_C": "3", "temp_F": "37",
                               "FeelsLikeC": "0", "FeelsLikeF": "32",
                               "weatherDesc": [{"value": "Light snow"}]}],
        "nearest_area": [{"areaName": [{"value": "Reykjavik"}]}],
        "weather": [_day("2026-12-01", -1, -6, desc="Light snow", rain="10")],
    })
    data = WeatherProvider._parse(weird)
    assert data["place"] == "Reykjavik"
    assert data["forecasts"][0]["min_c"] == -6
