
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
        
    def test_geoencode_location(self):
        connector = WeatherApiConnector(os.getenv('WEATHER'))
        location = connector.encode_location("Hanover")
        assert location.country == "DE"
        
    def test_timeencode(self):
        connector = WeatherApiConnector(os.getenv('WEATHER'))
        location = connector.encode_location("Hanover")
        time = connector.encode_time(location)
        assert time.month > 0
    
    