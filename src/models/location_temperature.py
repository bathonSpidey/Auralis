from pydantic import BaseModel, Field, field_serializer
from src.models.location_weather import Weather
from typing import List

class Temperature(BaseModel):
    temperature: float = Field(..., alias="temp")
    feels_like: float
    pressure: int
    humidity: int
    dew_point: float
    uvi: float
    clouds: int
    visibility: int
    wind_speed: float
    wind_deg: int
    weather: List[Weather]
    
    @field_serializer('weather')
    def serialize_weather(self, weather):
        return weather[0]