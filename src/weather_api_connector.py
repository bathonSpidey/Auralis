from models.location import Location
import datetime
import pytz, timezonefinder

import requests

from models.location_temperature import Temperature


class WeatherApiConnector:
    def __init__(self, api_key):
        self.api_key = api_key

    def get_location(self):
        ip = requests.get("https://api.ipify.org").text
        response = requests.get(f"http://ip-api.com/json/{ip}")
        data = response.json()
        return Location(**data)
    
    def encode_location(self, city_name):
        response = requests.get(f"http://api.openweathermap.org/geo/1.0/direct?q={city_name}&appid={self.api_key}")
        data = response.json()[0]
        return Location(**data)
    
    def encode_time(self, location):
        tf = timezonefinder.TimezoneFinder()
        timezone_str = tf.certain_timezone_at(lat=location.lat, lng=location.lon)
        timezone_str
        timezone = pytz.timezone(timezone_str)
        dt = datetime.datetime.now(timezone)
        return dt

    def get_current_location_weather(self, city):
        location = self.encode_location(city)
        time = int(self.encode_time(location).timestamp())
        response = requests.get(
            f"https://api.openweathermap.org/data/3.0/onecall/timemachine?lat={location.lat}&lon={location.lon}&dt={time}&appid={self.api_key}&units=metric"
        )
        data = response.json()["data"][0]
        return Temperature(**data)
