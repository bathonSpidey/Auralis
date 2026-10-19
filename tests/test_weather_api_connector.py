import os
import sys

import pytest

from src import weather_api_connector as weather
from src.weather_api_connector import WeatherApiConnector

ONECALL = {
    "timezone": "Europe/Berlin",
    "data": [
        {
            "temp": 11.7,
            "feels_like": 10.4,
            "pressure": 1030,
            "humidity": 59,
            "dew_point": 3.9,
            "uvi": 0.6,
            "clouds": 0,
            "visibility": 10000,
            "wind_speed": 2.2,
            "wind_deg": 8,
            "weather": [{"main": "Clear", "description": "clear sky"}],
        }
    ],
}
GEO = [{"name": "Rastatt", "country": "DE", "lat": 48.8, "lon": 8.2}]


class Reply:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_get(url, **kwargs):
        seen.append(url)
        return Reply(GEO if "geo" in url else ONECALL)

    monkeypatch.setattr(weather.requests, "get", fake_get)
    return seen


def test_conditions_carry_weather_place_and_local_time(calls):
    found = WeatherApiConnector("key", city="Rastatt").conditions()
    assert found.location.city == "Rastatt"
    assert found.weather.temperature == 11.7
    assert found.now.tzname() in ("CET", "CEST")


def test_conditions_are_cached_for_a_while(calls):
    connector = WeatherApiConnector("key", city="Rastatt")
    connector.conditions()
    connector.conditions()
    assert len(calls) == 2  # one geocode + one weather call, not four


def test_a_different_city_is_not_served_from_the_cache(calls):
    connector = WeatherApiConnector("key", city="Rastatt")
    connector.conditions()
    connector.conditions("Hanover")
    assert len(calls) == 4


def test_failure_gives_none_instead_of_raising(monkeypatch):
    def broken(url, **kwargs):
        raise ConnectionError("offline")

    monkeypatch.setattr(weather.requests, "get", broken)
    assert WeatherApiConnector("key", city="Rastatt").conditions() is None


def test_unknown_timezone_falls_back_to_the_machine_clock():
    assert weather._local_now("Not/AZone") is not None
    assert weather._local_now(None) is not None


@pytest.mark.skipif(sys.platform == "unix", reason="windows only")
@pytest.mark.skipif(not os.getenv("WEATHER"), reason="WEATHER not set")
@pytest.mark.integration
class TestWeatherApiConnector:
    def test_live_conditions(self):
        found = WeatherApiConnector(os.getenv("WEATHER")).conditions("Hanover")
        assert found.location.country == "DE"
        assert found.weather.temperature > -50
