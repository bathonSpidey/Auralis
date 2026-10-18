import json
import requests
from models.chart_data import ChartData


class SpotifyScraper:
    def __init__(self, bearer_token):
        """`bearer_token` is a token string or a callable returning a fresh one."""
        self.top_charts_base_url = "https://charts-spotify-com-service.spotify.com/auth/v0/charts/regional-{country}-weekly/latest"
        self.bearer_token = bearer_token

    def get_trending_songs(self, country: str = "de"):
        url = self.top_charts_base_url.format(country=country)
        headers = {
            "authority": "api-partner.spotify.com",
            "accept": "application/json",
            "app-platform": "Browser",
            "authorization": f"Bearer {self._token()}",
            "spotify-app-version": "0.0.0.production",
        }
        # Unofficial endpoint: any failure just means "no chart", never an error.
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return self.process_response(response.json(), country=country)
        except (requests.RequestException, ValueError):
            pass
        return None

    def _token(self):
        return self.bearer_token() if callable(self.bearer_token) else self.bearer_token

    def process_response(self, data: dict, country, category="trending"):
        data = ChartData.model_validate(data)
        top_5 = data.get_top_5_tracks()
        highlights = data.highlights
        payload = {f"top_5_{category}_in_{country}": top_5, "highlights": highlights}
        return json.dumps(
            payload,
            default=lambda x: x.model_dump() if hasattr(x, "model_dump") else str(x),
        )
