import datetime
import logging
import time
from dataclasses import dataclass
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from models.location import Location
from models.location_temperature import Temperature

logger = logging.getLogger(__name__)

_TIMEOUT = 10
# Weather changes slowly and every run asks for it; one lookup per quarter hour.
_CACHE_SECONDS = 15 * 60


@dataclass
class Conditions:
    location: Location
    weather: Temperature
    now: datetime.datetime  # local time at the location


class WeatherApiConnector:
    """OpenWeather lookups. `city` is where the listener is; without one the
    location is guessed from the public IP, which on the Pi is the home."""

    def __init__(self, api_key, city: Optional[str] = None):
        self.api_key = api_key
        self.city = city
        self._cached: Optional[tuple] = None  # (city, expires_at, Conditions)

    def get_location(self) -> Location:
        ip = requests.get("https://api.ipify.org", timeout=_TIMEOUT).text
        data = requests.get(f"http://ip-api.com/json/{ip}", timeout=_TIMEOUT).json()
        return Location(
            name=data["city"],
            country=data["countryCode"],
            lat=data["lat"],
            lon=data["lon"],
        )

    def encode_location(self, city_name) -> Location:
        response = requests.get(
            "http://api.openweathermap.org/geo/1.0/direct",
            params={"q": city_name, "appid": self.api_key},
            timeout=_TIMEOUT,
        )
        return Location(**response.json()[0])

    def get_current_location_weather(self, city) -> Temperature:
        return self._lookup(self.encode_location(city)).weather

    def conditions(self, city: Optional[str] = None) -> Optional[Conditions]:
        """Weather and local time for the listener, or None if either lookup
        fails: a playlist is still worth making without them."""
        city = city or self.city
        now = time.monotonic()
        if self._cached and self._cached[0] == city and self._cached[1] > now:
            return self._cached[2]
        try:
            location = self.encode_location(city) if city else self.get_location()
            found = self._lookup(location)
        except Exception as e:
            logger.warning("Weather unavailable (%s: %s)", type(e).__name__, e)
            return None
        self._cached = (city, now + _CACHE_SECONDS, found)
        return found

    def _lookup(self, location: Location) -> Conditions:
        response = requests.get(
            "https://api.openweathermap.org/data/3.0/onecall/timemachine",
            params={
                "lat": location.lat,
                "lon": location.lon,
                "dt": int(time.time()),
                "appid": self.api_key,
                "units": "metric",
            },
            timeout=_TIMEOUT,
        )
        body = response.json()
        return Conditions(
            location=location,
            weather=Temperature(**body["data"][0]),
            now=_local_now(body.get("timezone")),
        )


def _local_now(zone: Optional[str]) -> datetime.datetime:
    try:
        return datetime.datetime.now(ZoneInfo(zone))
    except Exception:  # unknown zone or no tz database: the machine's clock
        return datetime.datetime.now()
