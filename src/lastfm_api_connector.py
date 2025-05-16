import requests
from models.top import Top
from requests.exceptions import RequestException, Timeout


class LastFmConnector:
    def __init__(self, api_key):
        self.api_key = api_key
        self.url = "https://ws.audioscrobbler.com/2.0/"

    def get_top_songs(self):
        params = {
            "method": "chart.gettoptracks",
            "api_key": self.api_key,
            "format": "json",
        }
        try:
            response = requests.get(self.url, params=params, timeout=5)
            response.raise_for_status()
            return [
                Top(name=item["name"], artist_name=item["artist"]["name"])
                for item in response.json()["tracks"]["track"]
            ][:15]
        except (RequestException, Timeout):
            return [
                Top(
                    name="Could not be found",
                    artist_name="Nothing is trending at the moment",
                )
            ]
