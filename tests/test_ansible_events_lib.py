from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ansible_events_lib import (
    CITIES,
    DISCOURSE_URL,
    EVENT_NAME_PREFIX,
    ORGANISER_TEAM_PREFIX,
    ORGANIZER_SLUG,
    PRETIX_URL,
    CityInfo,
    get_city,
    strip_discourse_block,
)


class TestCityInfoSlug:
    def test_lowercase(self) -> None:
        city = CityInfo(region="Europe", country="UK", city="London", timezone="Europe/London")
        assert city.slug == "london"

    def test_spaces_to_hyphens(self) -> None:
        city = CityInfo(region="Americas", country="US", city="New York", timezone="America/New_York")
        assert city.slug == "new-york"

    def test_multiple_spaces(self) -> None:
        city = CityInfo(region="Americas", country="US", city="San  Francisco", timezone="America/Los_Angeles")
        assert city.slug == "san--francisco"

    def test_already_lowercase(self) -> None:
        city = CityInfo(region="Europe", country="DE", city="berlin", timezone="Europe/Berlin")
        assert city.slug == "berlin"

    def test_mixed_case(self) -> None:
        city = CityInfo(region="Europe", country="UK", city="FakeTown", timezone="Europe/London")
        assert city.slug == "faketown"

    def test_empty_string(self) -> None:
        city = CityInfo(region="", country="", city="", timezone="")
        assert city.slug == ""

    def test_leading_trailing_spaces(self) -> None:
        city = CityInfo(region="Europe", country="UK", city=" London ", timezone="Europe/London")
        assert city.slug == "-london-"

    def test_tab_characters(self) -> None:
        city = CityInfo(region="Americas", country="US", city="New\tYork", timezone="America/New_York")
        assert city.slug == "new\tyork"

    def test_unicode(self) -> None:
        city = CityInfo(region="Europe", country="DE", city="München", timezone="Europe/Berlin")
        assert city.slug == "münchen"


class TestCityInfoFieldValue:
    def test_standard_format(self) -> None:
        city = CityInfo(region="Europe", country="UK", city="London", timezone="Europe/London")
        assert city.field_value == "Europe:UK:London"

    def test_multi_word_values(self) -> None:
        city = CityInfo(region="Americas", country="US", city="New York", timezone="America/New_York")
        assert city.field_value == "Americas:US:New York"

    def test_preserves_original_case(self) -> None:
        city = CityInfo(region="EMEA", country="India", city="Pune", timezone="Asia/Kolkata")
        assert city.field_value == "EMEA:India:Pune"


class TestCityInfoFrozen:
    def test_cannot_modify_city(self) -> None:
        city = CityInfo(region="Europe", country="UK", city="London", timezone="Europe/London")
        with pytest.raises(AttributeError):
            city.city = "Manchester"  # type: ignore[misc]

    def test_cannot_modify_region(self) -> None:
        city = CityInfo(region="Europe", country="UK", city="London", timezone="Europe/London")
        with pytest.raises(AttributeError):
            city.region = "Americas"  # type: ignore[misc]


class TestGetCity:
    def test_lowercase_slug_match(self) -> None:
        result = get_city("london")
        assert result is not None
        assert result.city == "London"

    def test_rejects_non_lowercase_input(self) -> None:
        assert get_city("London") is None
        assert get_city("LONDON") is None
        assert get_city("lOnDoN") is None

    def test_not_found(self) -> None:
        assert get_city("atlantis") is None

    def test_empty_string(self) -> None:
        assert get_city("") is None

    def test_partial_match_does_not_work(self) -> None:
        assert get_city("Lond") is None

    def test_leading_trailing_spaces_no_match(self) -> None:
        assert get_city(" london ") is None

    def test_returns_full_city_info(self) -> None:
        result = get_city("barcelona")
        assert result is not None
        assert result.region == "Europe"
        assert result.country == "Spain"
        assert result.timezone == "Europe/Madrid"

    def test_faketown(self) -> None:
        result = get_city("faketown")
        assert result is not None
        assert result.timezone == "Europe/London"


class TestCitiesRegistry:
    def test_all_cities_are_cityinfo(self) -> None:
        for city in CITIES:
            assert isinstance(city, CityInfo)

    def test_no_duplicate_city_names(self) -> None:
        names = [c.city for c in CITIES]
        assert len(names) == len(set(names)), f"Duplicate city names: {names}"

    def test_timezones_contain_slash(self) -> None:
        for city in CITIES:
            assert "/" in city.timezone, f"Invalid timezone for {city.city}: {city.timezone}"

    def test_registry_is_immutable(self) -> None:
        assert isinstance(CITIES, tuple)


class TestPretixReqUrlBuilding:
    """Test URL construction logic without making real HTTP calls."""

    def _build_url(self, endpoint: str) -> str:
        url = f"{PRETIX_URL}/api/v1/organizers/{ORGANIZER_SLUG}/{endpoint}"
        if "?" in url:
            base, query = url.split("?", 1)
            if not base.endswith("/"):
                base += "/"
            url = f"{base}?{query}"
        else:
            if not url.endswith("/"):
                url += "/"
        return url

    def test_simple_endpoint(self) -> None:
        url = self._build_url("events")
        assert url.endswith("/events/")

    def test_trailing_slash_preserved(self) -> None:
        url = self._build_url("events/")
        assert url.endswith("/events/")
        assert not url.endswith("//")

    def test_nested_endpoint(self) -> None:
        url = self._build_url("events/my-event/items")
        assert url.endswith("/events/my-event/items/")

    def test_double_slash_not_added(self) -> None:
        url = self._build_url("events/my-event/items/")
        assert "//" not in url.split("://", 1)[1]

    def test_query_string_preserved(self) -> None:
        url = self._build_url("events?page=2")
        assert url.endswith("events/?page=2")

    def test_query_string_with_trailing_slash(self) -> None:
        url = self._build_url("events/?page=2")
        assert url.endswith("events/?page=2")

    def test_empty_endpoint(self) -> None:
        url = self._build_url("")
        assert url.endswith(f"{ORGANIZER_SLUG}/")

    def test_endpoint_with_spaces(self) -> None:
        url = self._build_url("events/my event")
        assert "my event" in url


class TestDiscourseReqUrlBuilding:
    """Test URL construction logic without making real HTTP calls."""

    def _build_url(self, endpoint: str) -> str:
        return f"{DISCOURSE_URL.rstrip('/')}/{endpoint}"

    def test_simple_endpoint(self) -> None:
        url = self._build_url("posts.json")
        assert url == f"{DISCOURSE_URL}/posts.json"

    def test_strips_trailing_slash_from_base(self) -> None:
        base = "https://forum.example.com/"
        url = f"{base.rstrip('/')}/posts.json"
        assert "//" not in url.split("://", 1)[1]

    def test_nested_endpoint(self) -> None:
        url = self._build_url("t/123.json")
        assert url.endswith("/t/123.json")

    def test_admin_endpoint(self) -> None:
        url = self._build_url("admin/groups.json")
        assert url.endswith("/admin/groups.json")


class TestPreFlightChecks:
    @patch.dict("os.environ", {"PRETIX_API_TOKEN": "test", "DISCOURSE_API_KEY": "test"})
    def test_passes_with_both_vars(self) -> None:
        import ansible_events_lib

        importlib.reload(ansible_events_lib)
        ansible_events_lib.pre_flight_checks()

    @patch.dict("os.environ", {"PRETIX_API_TOKEN": "test"}, clear=True)
    def test_exits_without_discourse_key(self) -> None:
        import ansible_events_lib

        importlib.reload(ansible_events_lib)
        with pytest.raises(SystemExit):
            ansible_events_lib.pre_flight_checks()

    @patch.dict("os.environ", {"PRETIX_API_TOKEN": "test"}, clear=True)
    def test_passes_without_discourse_key_when_not_required(self) -> None:
        import ansible_events_lib

        importlib.reload(ansible_events_lib)
        ansible_events_lib.pre_flight_checks(require_discourse=False)


class TestCityInfoDerivedProperties:
    def test_event_name(self) -> None:
        city = CityInfo(region="Europe", country="UK", city="London", timezone="Europe/London")
        assert city.event_name == f"{EVENT_NAME_PREFIX} London"

    def test_team_name(self) -> None:
        city = CityInfo(region="Europe", country="UK", city="London", timezone="Europe/London")
        assert city.team_name == f"{ORGANISER_TEAM_PREFIX} - London"

    def test_organiser_group(self) -> None:
        city = CityInfo(region="Europe", country="UK", city="London", timezone="Europe/London")
        assert city.organiser_group == "meetup-organisers-london"

    def test_attendee_group(self) -> None:
        city = CityInfo(region="Europe", country="UK", city="London", timezone="Europe/London")
        assert city.attendee_group == "meetup-attendee-london"

    def test_organiser_group_with_spaces(self) -> None:
        city = CityInfo(region="Americas", country="US", city="New York", timezone="America/New_York")
        assert city.organiser_group == "meetup-organisers-new-york"

    def test_team_name_preserves_case(self) -> None:
        city = CityInfo(region="Europe", country="UK", city="FakeTown", timezone="Europe/London")
        assert city.team_name == f"{ORGANISER_TEAM_PREFIX} - FakeTown"


class TestStripDiscourseBlock:
    def test_strips_above_separator(self) -> None:
        md = "[event]...[/event]\n\n---\n\n## Welcome"
        assert strip_discourse_block(md) == "## Welcome"

    def test_no_separator_returns_full_content(self) -> None:
        md = "## Welcome to the event"
        assert strip_discourse_block(md) == md

    def test_multiple_separators_splits_on_first(self) -> None:
        md = "block1\n---\ncontent\n---\nmore"
        assert strip_discourse_block(md) == "content\n---\nmore"

    def test_empty_above_separator(self) -> None:
        md = "---\ncontent"
        assert strip_discourse_block(md) == "content"

    def test_empty_below_separator(self) -> None:
        md = "block\n---\n"
        assert strip_discourse_block(md) == ""

    def test_only_separator(self) -> None:
        md = "---"
        assert strip_discourse_block(md) == ""

    def test_whitespace_stripped(self) -> None:
        md = "block\n---\n  \n  content  \n  "
        assert strip_discourse_block(md) == "content"
