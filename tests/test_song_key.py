import pytest

from models.song_key import normalize, song_key


@pytest.mark.parametrize(
    "variant",
    [
        "Opalite",
        "opalite",
        "Opalite - Single Version",
        "Opalite (Taylor's Version)",
        "Opalite - Remastered 2011",
        "Opalite [Live]",
        "Opalite - 2024 Remaster",
    ],
)
def test_releases_of_a_song_share_a_key(variant):
    assert song_key(variant, "Taylor Swift") == song_key("Opalite", "Taylor Swift")


def test_different_songs_and_artists_differ():
    assert song_key("Opalite", "Taylor Swift") != song_key("Opalite", "Cover Band")
    assert song_key("Opalite", "Taylor Swift") != song_key(
        "Lavender Haze", "Taylor Swift"
    )


def test_accents_and_punctuation_are_ignored():
    assert song_key("Despacito!", "Luis Fonsi") == song_key("despacito", "Luis Fonsí")
    assert normalize("  Beyoncé -- Halo ") == "beyonce halo"


def test_a_dash_that_is_part_of_the_title_is_kept():
    assert song_key("Hit - Me Baby", "X") != song_key("Hit", "X")
