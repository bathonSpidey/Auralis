
import os


from src.weather_api_connector import WeatherApiConnector

class TestWeatherApiConnector:
    def test_get_location(self):
        api_key = 'your_api_key'
        connector = WeatherApiConnector(api_key)
        location = connector.get_location()
        assert location.city != ""
    
    def test_get_weather(self):
        connector = WeatherApiConnector(os.getenv('WEATHER'))
        weather = connector.get_current_location_weather()
        assert weather.temperature > 0.0
    
    