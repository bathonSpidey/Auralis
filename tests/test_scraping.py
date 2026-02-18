from src.spotify_scraper import SpotifyChartsAPI, SpotifyScraper


class TestSpotifyScraper:
    scrapper = SpotifyScraper()

    def test_get_top_tracks(self):
        api = SpotifyChartsAPI()

        # Get Germany's top tracks
        de_tracks = api.get_top_tracks("de", limit=20)
        assert len(de_tracks) == 20
