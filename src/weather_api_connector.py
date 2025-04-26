from src.models.location import Location
import datetime

import requests

from src.models.location_temperature import Temperature


class WeatherApiConnector:
    def __init__(self, api_key):
        self.api_key = api_key

    def get_location(self):
       ip = requests.get('https://api.ipify.org').text
       response = requests.get(f'http://ip-api.com/json/{ip}')
       data = response.json()
       return Location(**data)
   
    def get_weather(self, location):
        location = self.get_location()
        time = int(datetime.datetime.now().timestamp())
        response = requests.get(f'https://api.openweathermap.org/data/3.0/onecall/timemachine?lat={location.lat}&lon={location.lon}&dt={time}&appid={self.api_key}&units=metric')
        data = response.json()["data"][0]
        return Temperature(**data)