import json

from app.modules.tools import get_tool_registry
from app.modules.tools.implementations.datetime_now import DateTimeNowTool
from app.modules.tools.implementations.weather import WeatherTool
from app.modules.tools.implementations.web_search import WebSearchTool


class _DummyResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False


def test_registry_registers_expected_core_tools() -> None:
    registry = get_tool_registry()
    openai_tools = registry.get_tools_for_openai()
    names = {item["function"]["name"] for item in openai_tools}

    assert "weather" in names
    assert "web_search" in names
    assert "datetime_now" in names


def test_datetime_tool_returns_utc() -> None:
    tool = DateTimeNowTool()
    output = tool.run({})

    assert output.startswith("UTC time:")


def test_web_search_tool_parses_response(monkeypatch) -> None:
    payload = {
        "Heading": "Python",
        "AbstractText": "Python is a programming language.",
        "RelatedTopics": [
            {
                "Text": "Python official site",
                "FirstURL": "https://www.python.org",
            }
        ],
    }

    def fake_urlopen(_url: str, timeout: int):
        assert timeout == 8
        return _DummyResponse(payload)

    monkeypatch.setattr("app.modules.tools.implementations.web_search.urlopen", fake_urlopen)

    tool = WebSearchTool()
    output = tool.run({"query": "python"})

    assert "Top result: Python" in output
    assert "Summary: Python is a programming language." in output
    assert "https://www.python.org" in output


def test_weather_tool_parses_response(monkeypatch) -> None:
    geo_payload = {
        "results": [
            {"name": "Paris", "country": "France", "latitude": 48.85, "longitude": 2.35}
        ]
    }
    weather_payload = {
        "current": {
            "temperature_2m": 21.1,
            "apparent_temperature": 20.4,
            "weather_code": 1,
            "wind_speed_10m": 8.2,
        }
    }

    def fake_urlopen(url: str, timeout: int):
        assert timeout == 8
        if "geocoding-api.open-meteo.com" in url:
            return _DummyResponse(geo_payload)
        return _DummyResponse(weather_payload)

    monkeypatch.setattr("app.modules.tools.implementations.weather.urlopen", fake_urlopen)

    tool = WeatherTool()
    output = tool.run({"city": "Paris"})

    assert "Current weather in Paris, France" in output
    assert "Temperature: 21.1" in output


def test_weather_tool_requires_city() -> None:
    tool = WeatherTool()
    output = tool.run({})

    assert output == "No city provided."

