import os
import pytest
import sys


from src.weather_api_connector import WeatherApiConnector


@pytest.mark.skipif(sys.platform == "unix", reason="windows only")
@pytest.mark.skipif(not os.getenv("WEATHER"), reason="WEATHER not set")
@pytest.mark.integration
class TestWeatherApiConnector:
    def test_get_weather(self):
        connector = WeatherApiConnector(os.getenv("WEATHER"))
        weather = connector.get_current_location_weather("Hanover")
        assert weather.temperature > 0.0

    def test_geoencode_location(self):
        connector = WeatherApiConnector(os.getenv("WEATHER"))
        location = connector.encode_location("Hanover")
        assert location.country == "DE"

    def test_timeencode(self):
        connector = WeatherApiConnector(os.getenv("WEATHER"))
        location = connector.encode_location("Hanover")
        time = connector.encode_time(location)
        assert time.month > 0
