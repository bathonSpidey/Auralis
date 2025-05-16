import requests
from models.top import Top


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
        response = requests.get(self.url, params=params)
        return [
            Top(name=item["name"], artist_name=item["artist"]["name"])
            for item in response.json()["tracks"]["track"]
        ][:15]
