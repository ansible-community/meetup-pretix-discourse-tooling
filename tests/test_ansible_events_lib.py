from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import Mock, patch

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
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        assert city.slug == "london"

    def test_mixed_case(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="faketown", city="FakeTown", timezone="Europe/London")
        assert city.slug == "faketown"

    def test_invalid_slug_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            CityInfo(region="Europe", country="UK", slug="new-york", city="New York", timezone="Europe/London")


class TestCityInfoFieldValue:
    def test_standard_format(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        assert city.field_value == "Europe:UK:London"

    def test_multi_word_values(self) -> None:
        city = CityInfo(region="Americas", country="US", slug="newyork", city="New York", timezone="America/New_York")
        assert city.field_value == "Americas:US:New York"

    def test_preserves_original_case(self) -> None:
        city = CityInfo(region="EMEA", country="India", slug="pune", city="Pune", timezone="Asia/Kolkata")
        assert city.field_value == "EMEA:India:Pune"


class TestCityInfoFrozen:
    def test_cannot_modify_city(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        with pytest.raises(AttributeError):
            city.city = "Manchester"  # type: ignore[misc]

    def test_cannot_modify_region(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
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
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        assert city.event_name == f"{EVENT_NAME_PREFIX} London"

    def test_team_name(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        assert city.team_name == f"{ORGANISER_TEAM_PREFIX} - London"

    def test_organiser_group(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        assert city.organiser_group == "meetup-organisers-london"

    def test_attendee_group(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London")
        assert city.attendee_group == "meetup-attendee-london"

    def test_organiser_group_with_spaces(self) -> None:
        city = CityInfo(region="Americas", country="US", slug="newyork", city="New York", timezone="America/New_York")
        assert city.organiser_group == "meetup-organisers-newyork"

    def test_team_name_preserves_case(self) -> None:
        city = CityInfo(region="Europe", country="UK", slug="faketown", city="FakeTown", timezone="Europe/London")
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


class TestPretixApiContract:
    def test_discourse_request_uses_explicit_run_as_identity(self, monkeypatch):
        import ansible_events_lib

        monkeypatch.setattr(ansible_events_lib, "DISCOURSE_API_KEY", "test-api-key")
        response = Mock(status_code=200, text='{"ok":true}')
        response.json.return_value = {"ok": True}
        request = Mock(return_value=response)
        monkeypatch.setattr(ansible_events_lib.httpx, "request", request)

        assert ansible_events_lib.discourse_req("POST", "posts.json", {"raw": "event"}, run_as="organiser") == {
            "ok": True
        }
        assert request.call_args.kwargs["headers"]["Api-Key"] == "test-api-key"
        assert request.call_args.kwargs["headers"]["Api-Username"] == "organiser"

    def test_category_lookup_requires_unique_events_subcategory(self, monkeypatch):
        import ansible_events_lib

        monkeypatch.setattr(
            ansible_events_lib,
            "discourse_req",
            lambda *_args: {
                "category_list": {
                    "categories": [
                        {
                            "id": 8,
                            "name": "Events",
                            "subcategory_list": [
                                {"id": 11, "name": "London", "parent_category_id": 8},
                                {"id": 12, "name": "London", "parent_category_id": 8},
                            ],
                        }
                    ]
                }
            },
        )

        with pytest.raises(ansible_events_lib.ApiError, match="found 2"):
            ansible_events_lib.discourse_city_category_id("London")

    def test_check_event_exists_distinguishes_confirmed_404_from_api_failure(self, monkeypatch):
        import ansible_events_lib

        response = Mock(status_code=404, text="Not found")
        monkeypatch.setattr(ansible_events_lib.httpx, "get", Mock(return_value=response))
        assert ansible_events_lib.check_event_exists("london-oct-2026") is False
        response.status_code = 503
        with pytest.raises(ansible_events_lib.ApiError):
            ansible_events_lib.check_event_exists("london-oct-2026")

    def test_pretix_request_rejects_non_object_json(self, monkeypatch):
        import ansible_events_lib

        response = Mock(status_code=200, text="[]")
        response.json.return_value = []
        monkeypatch.setattr(ansible_events_lib.httpx, "request", Mock(return_value=response))
        with pytest.raises(ansible_events_lib.ApiError, match="non-object JSON"):
            ansible_events_lib.pretix_req("GET", "events")

    def test_pagination_rejects_external_host_before_sending_token(self, monkeypatch):
        import ansible_events_lib

        monkeypatch.setattr(ansible_events_lib, "PRETIX_URL", "https://tickets.example")
        monkeypatch.setattr(
            ansible_events_lib,
            "pretix_req",
            lambda *_args: {
                "results": [{"slug": "london-oct-2026"}],
                "next": "https://attacker.example/steal?token=1",
            },
        )
        next_request = Mock()
        monkeypatch.setattr(ansible_events_lib.httpx, "get", next_request)
        with pytest.raises(ansible_events_lib.ApiError, match="outside the configured organizer API"):
            ansible_events_lib.pretix_list_all("events")
        next_request.assert_not_called()

    def test_pagination_collects_all_pages_inside_organizer(self, monkeypatch):
        import ansible_events_lib

        monkeypatch.setattr(ansible_events_lib, "PRETIX_URL", "https://tickets.example")
        monkeypatch.setattr(ansible_events_lib, "ORGANIZER_SLUG", "meetups")
        monkeypatch.setattr(ansible_events_lib, "PRETIX_API_TOKEN", "secret-token")
        monkeypatch.setattr(
            ansible_events_lib,
            "pretix_req",
            lambda *_args: {
                "results": [{"slug": "london-oct-2026"}],
                "next": "/api/v1/organizers/meetups/events/?page=2",
            },
        )
        response = MockResponse(200, {"results": [{"slug": "barcelona-nov-2026"}], "next": None})
        next_request = Mock(return_value=response)
        monkeypatch.setattr(ansible_events_lib.httpx, "get", next_request)
        result = ansible_events_lib.pretix_list_all("events")
        assert [event["slug"] for event in result] == ["london-oct-2026", "barcelona-nov-2026"]
        assert next_request.call_args.args[0] == ("https://tickets.example/api/v1/organizers/meetups/events/?page=2")
        assert next_request.call_args.kwargs["headers"]["Authorization"] == "Token secret-token"


class MockResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self.text = "{}"
        self._payload = payload

    def json(self):
        return self._payload


class TestProvisioningPermissions:
    def test_organizer_access_is_removed_everywhere_except_own_subcategory(self, monkeypatch):
        import provision_environment

        categories = [
            {"id": 11, "subcategory_list": []},
            {"id": 12, "subcategory_list": []},
        ]
        current = {
            11: {
                "moderating_group_ids": [9, 10],
                "permissions": {"everyone": 1, "meetup-organisers-london": 1},
            },
            12: {
                "moderating_group_ids": [10, 15],
                "permissions": {"everyone": 1, "meetup-organisers-london": 1},
            },
        }

        def request(method, endpoint, payload=None):
            if method == "GET" and endpoint == "categories.json":
                return {"category_list": {"categories": categories}}
            if method == "GET" and endpoint.startswith("categories/"):
                category_id = int(endpoint.split("/")[1].split(".")[0])
                return {"category": current[category_id]}
            if method == "PUT" and endpoint.startswith("categories/"):
                category_id = int(endpoint.split("/")[1].split(".")[0])
                current[category_id].update(payload)
                return {}
            raise AssertionError(f"Unexpected Discourse request: {method} {endpoint}")

        monkeypatch.setattr(provision_environment, "discourse_req", request)
        monkeypatch.setattr(
            provision_environment,
            "list_discourse_groups",
            lambda: [
                {"id": 9, "name": "meetup-organisers-london"},
                {"id": 10, "name": "meetup-organisers-barcelona"},
            ],
        )

        provision_environment.reconcile_organiser_category_access({11: ("meetup-organisers-london", 9)})

        assert current[11]["moderating_group_ids"] == [9]
        assert current[11]["permissions"] == {"everyone": 1, "meetup-organisers-london": 1}
        assert current[12]["moderating_group_ids"] == [15]
        assert current[12]["permissions"] == {"everyone": 1}
