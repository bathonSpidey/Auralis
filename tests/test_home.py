import pytest

from agent.home import MAX_KEYS, MAX_TEXT, HomeError, HomeState, clean
from store.history import Store


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def home(tmp_path):
    clock = Clock()
    state = HomeState(Store(tmp_path / "home.db"), wall=clock)
    state.clock = clock
    return state


class TestClean:
    def test_keys_become_plain_snake_case(self):
        out = clean({"Room Temperature (C)": 22.456, "LUX": 40})
        assert out == {"room_temperature_c": 22.46, "lux": 40}

    def test_booleans_numbers_and_text_are_kept(self):
        out = clean({"anyone_home": True, "mode": "  working   at  desk "})
        assert out == {"anyone_home": True, "mode": "working at desk"}

    def test_text_is_one_short_line(self):
        out = clean({"note": "line one\n\nline two " + "x" * 300})
        assert "\n" not in out["note"] and len(out["note"]) <= MAX_TEXT

    def test_null_and_empty_text_mean_forget(self):
        assert clean({"a": None, "b": "   "}) == {"a": None, "b": None}

    def test_nested_values_are_refused(self):
        with pytest.raises(HomeError):
            clean({"rooms": {"office": 21}})
        with pytest.raises(HomeError):
            clean({"list": [1, 2]})

    def test_an_unusable_key_is_refused(self):
        with pytest.raises(HomeError):
            clean({"!!!": 1})

    def test_not_an_object_is_refused(self):
        with pytest.raises(HomeError):
            clean([("a", 1)])


class TestState:
    def test_nothing_reported_is_none(self, home):
        assert home.current() is None

    def test_updates_merge_and_null_forgets(self, home):
        home.update({"room_temperature_c": 22.5, "lux": 40})
        home.update({"lux": 10, "anyone_home": True})
        assert home.current() == {
            "room_temperature_c": 22.5,
            "lux": 10,
            "anyone_home": True,
        }
        assert "lux" not in home.update({"lux": None})

    def test_a_silent_sensor_drops_out_but_others_stay(self, home):
        home.update({"room_temperature_c": 22.5})
        home.clock.now += 2 * 3600
        home.update({"lux": 40})
        home.clock.now += 2 * 3600  # temperature is now 4 h old, lux 2 h
        assert home.current() == {"lux": 40}
        home.clock.now += 2 * 3600
        assert home.current() is None

    def test_it_is_remembered_across_restarts(self, home, tmp_path):
        home.update({"room_temperature_c": 22.5})
        again = HomeState(Store(tmp_path / "home.db"), wall=home.clock)
        assert again.current() == {"room_temperature_c": 22.5}

    def test_too_many_different_keys_are_refused(self, home):
        with pytest.raises(HomeError):
            home.update({f"sensor_{n}": n for n in range(MAX_KEYS + 1)})
        assert home.current() is None
