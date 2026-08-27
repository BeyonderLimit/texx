import urllib.parse

from services.search import OnlineError, _fetch


def _single(values):
    """wttr.in nests single-valued fields as [{'value': 'Sunny'}]."""
    if isinstance(values, list) and values:
        return values[0].get("value") or ""
    return ""


class WeatherProvider:
    """wttr.in JSON endpoint — no API key required."""

    name = "weather"

    def current(self, location: str | None = None) -> dict:
        base = "https://wttr.in/"
        if location:
            url = base + urllib.parse.quote(location.strip()) + "?format=j1"
        else:
            url = base + "?format=j1"  # no location -> wttr.in geolocates by IP
        raw = _fetch(url)
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> dict:
        import json

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise OnlineError("weather endpoint returned garbage") from e
        if not isinstance(data, dict):
            raise OnlineError("unexpected weather payload")

        conditions = data.get("current_condition") or []
        days = data.get("weather") or []
        if not conditions or not days:
            raise OnlineError("no weather data parsed (endpoint may have changed)")

        try:
            cc = conditions[0]
            current = {
                "temp_c": int(cc["temp_C"]),
                "temp_f": int(cc["temp_F"]),
                "feels_c": int(cc["FeelsLikeC"]),
                "feels_f": int(cc["FeelsLikeF"]),
                "desc": _single(cc.get("weatherDesc")),
            }
            forecasts = [WeatherProvider._day_summary(d) for d in days[:3]]
        except (KeyError, TypeError, ValueError) as e:
            raise OnlineError(f"malformed weather payload ({e.__class__.__name__})") from e

        areas = data.get("nearest_area") or []
        parts = [
            _single(areas[0].get(key)) for key in ("areaName", "region", "country")
        ] if areas else []
        parts = [p for p in parts if p]
        return {
            "place": ", ".join(parts[:2]),
            "current": current,
            "forecasts": forecasts,
        }

    @staticmethod
    def _day_summary(day: dict) -> dict:
        hourlies = day.get("hourly") or []
        # Description nearest midday reads best as "the day's weather";
        # rain chance is the day maximum over the hourly buckets.
        def distance(bucket):
            try:
                return abs(int(bucket.get("time", 0)) - 1200)
            except (TypeError, ValueError):
                return 9999

        noon = min(hourlies, key=distance) if hourlies else {}
        rains = [int(h.get("chanceofrain") or 0) for h in hourlies
                 if str(h.get("chanceofrain") or "").isdigit()]
        return {
            "date": day.get("date") or "",
            "max_c": int(day["maxtempC"]),
            "min_c": int(day["mintempC"]),
            "max_f": int(day["maxtempF"]),
            "min_f": int(day["mintempF"]),
            "desc": _single(noon.get("weatherDesc")) or _single((day.get("hourly") or [{}])[0].get("weatherDesc")),
            "rain_pct": max(rains) if rains else None,
        }
