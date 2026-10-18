# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""City profile loading, validation and the SMARTROUTE_DATA_DIR override."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import city_profile
import config
from conftest import FIXTURE_DATA_DIR, SRC_DIR

REPO_ROOT = SRC_DIR.parent.parent
BUNDLED_PROFILE = SRC_DIR / "data" / "city_profile.json"


def _minimal(**overrides):
    raw = {
        "locations": [
            {"name": "A", "lat": 1.0, "lon": 2.0},
            {"name": "B", "desc": "B City", "lat": 3.0, "lon": 4.0},
        ]
    }
    raw.update(overrides)
    return raw


# ---- the override -----------------------------------------------------------
def test_data_dir_override_feeds_every_path():
    assert config.DATA_DIR == FIXTURE_DATA_DIR
    assert config.GPX_DIR == FIXTURE_DATA_DIR / "routes"
    assert config.ROUTE_STATUS_DIR == FIXTURE_DATA_DIR / "csv"
    assert config.CONFIG_FILE == FIXTURE_DATA_DIR / "config.json"
    assert config.CITY_PROFILE_FILE == FIXTURE_DATA_DIR / "city_profile.json"


def test_fixture_profile_populates_config():
    assert config.DEFAULT_TRIP == ("Alpha Town", "Beta Town")
    assert config.DEFAULT_LOCATIONS == ["Alpha Town", "Beta Town", "Gamma"]
    assert config.DEFAULT_LOCATION_COORDINATES["Beta Town"] == [10.0, 20.1]
    assert config.IGNORED_ROUTES == ["twotown-closed.gpx"]
    assert config.MAP_CENTRE == (10.01, 20.05)
    assert config.MAP_ZOOM == 12
    assert config.INTERSECTIONS == {"intxn_main": ("Main St & Middle Rd", 10.002, 20.05)}
    assert config.AVG_SPEED_KMH == 40
    assert config.route_label("twotown-detour.gpx") == "Northern detour"
    assert config.route_label("unlabelled.gpx") == "unlabelled.gpx"
    assert config.find_location("Alpha") == "Alpha Town"  # by <name>
    assert config.find_location("Alpha Town") == "Alpha Town"  # by <desc>
    assert config.find_location("alpha town") is None  # exact, case-sensitive


def test_map_fallbacks_and_speed_come_from_the_profile():
    from utils.gpx_parser import MapDataParser
    from utils.map_creator import MapCreator

    assert MapDataParser().calculate_center_and_zoom() == (10.01, 20.05, 12)
    assert MapCreator().calculate_map_center_and_zoom([]) == (10.01, 20.05, 12)
    # ~89 km of track at the profile's 40 km/h -> "~2 hours"
    pts = [[10.0, 20.0], [10.0, 20.81]]
    html = MapCreator().create_route_info_box("Alpha Town", "Beta Town", pts, "test")
    assert "~2 hours" in html
    assert "Synthetic test data." in html


def test_bundled_bay_area_profile_is_the_default():
    """With SMARTROUTE_DATA_DIR unset, config is exactly what the code used to hard-wire."""
    env = {k: v for k, v in os.environ.items() if k != "SMARTROUTE_DATA_DIR"}
    probe = (
        "import json, config; print(json.dumps({"
        "'data_dir': str(config.DATA_DIR), 'trip': config.DEFAULT_TRIP,"
        "'locations': config.DEFAULT_LOCATIONS, 'coords': config.DEFAULT_LOCATION_COORDINATES,"
        "'ignored': config.IGNORED_ROUTES, 'centre': config.MAP_CENTRE, 'zoom': config.MAP_ZOOM,"
        "'intersections': config.INTERSECTIONS, 'speed': config.AVG_SPEED_KMH}))"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], cwd=SRC_DIR, env=env,
        capture_output=True, text=True, check=True,
    ).stdout
    got = json.loads(out)
    assert Path(got["data_dir"]) == (SRC_DIR / "data").resolve()
    assert got["trip"] == ["Berkeley, California", "Santa Clara, California"]
    assert got["locations"] == ["Berkeley, California", "Santa Clara, California"]
    assert got["coords"] == {
        "Berkeley, California": [37.8715, -122.273],
        "Santa Clara, California": [37.3541, -121.9552],
    }
    assert got["ignored"] == ["berkeley-eastpaloalto.gpx", "berkeley-sanbruno-sunnyvale.gpx"]
    assert got["centre"] == [37.7, -122.2] and got["zoom"] == 9
    assert got["intersections"] == {
        "intxn_market_st": ["Market St & 1st", 37.7946, -122.3999],
        "intxn_5th_ave": ["5th Ave & Mission", 37.7825, -122.4079],
        "intxn_broadway": ["Broadway & Columbus", 37.798, -122.407],
    }
    assert got["speed"] == 80


def test_app_assets_mirror_the_bundled_profile():
    """The Flutter apps and the Dart CLI ship a copy of the profile; it must not drift."""
    bundled = json.loads(BUNDLED_PROFILE.read_text(encoding="utf-8"))
    for copy in [
        REPO_ROOT / "commuter_app" / "assets" / "city_profile.json",
        REPO_ROOT / "intersection_app" / "assets" / "city_profile.json",
    ]:
        mirrored = json.loads(copy.read_text(encoding="utf-8"))
        mirrored.pop("$schema", None)
        assert mirrored == {k: v for k, v in bundled.items() if k != "$schema"}, copy


def test_dart_profile_readers_are_identical_copies():
    copies = [
        REPO_ROOT / app / "lib" / "city_profile.dart"
        for app in ("commuter_app", "intersection_app", "dart_client")
    ]
    texts = {p: p.read_text(encoding="utf-8") for p in copies}
    assert len(set(texts.values())) == 1, "keep the three city_profile.dart files identical"


def test_bundled_profile_validates_against_its_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((SRC_DIR / "data" / "city_profile.schema.json").read_text(encoding="utf-8"))
    for path in [BUNDLED_PROFILE, FIXTURE_DATA_DIR / "city_profile.json"]:
        jsonschema.validate(json.loads(path.read_text(encoding="utf-8")), schema)


# ---- validation --------------------------------------------------------------
def test_optional_fields_get_neutral_defaults():
    p = city_profile.normalise(_minimal())
    assert p["default_trip"] == {"source": "A", "destination": "B City"}
    assert p["map"] == {"centre": {"lat": 2.0, "lon": 3.0}, "zoom": city_profile.DEFAULT_ZOOM}
    assert p["ignored_routes"] == [] and p["route_labels"] == {}
    assert p["intersections"] == {} and p["report_points"] == []
    assert p["avg_speed_kmh"] == 80.0 and p["attribution"] == ""


def test_default_trip_may_name_a_location_by_name_or_desc():
    p = city_profile.normalise(_minimal(default_trip={"source": "B", "destination": "A"}))
    assert p["default_trip"] == {"source": "B City", "destination": "A"}


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"locations": [{"name": "A", "lat": 1, "lon": 2}]}, "at least two"),
        ({"default_trip": {"source": "Nowhere", "destination": "A"}}, "not one of the locations"),
        ({"map": {"zoom": 0}}, "map.zoom"),
        ({"map": {"centre": {"lat": 91, "lon": 0}}}, "not a valid coordinate"),
        ({"intersections": {"intxn_x": {"name": "X", "lat": "1", "lon": 2}}}, "must be a number"),
        ({"report_points": [{"lat": 1, "lon": 2}]}, "name must be"),
        ({"avg_speed_kmh": 0}, "positive"),
        ({"schema_version": 2}, "schema_version"),
        ({"ignored_routes": "x.gpx"}, "ignored_routes"),
    ],
)
def test_invalid_profiles_are_rejected_with_a_reason(overrides, message):
    with pytest.raises(city_profile.CityProfileError, match=message):
        city_profile.normalise(_minimal(**overrides))


def test_duplicate_location_labels_are_rejected():
    raw = _minimal(locations=[{"name": "A", "lat": 1, "lon": 2}, {"name": "A", "lat": 3, "lon": 4}])
    with pytest.raises(city_profile.CityProfileError, match="unique"):
        city_profile.normalise(raw)


def test_a_data_dir_without_a_profile_fails_loudly(tmp_path):
    with pytest.raises(city_profile.CityProfileError, match="no city profile"):
        city_profile.load(tmp_path / "city_profile.json")
    env = dict(os.environ, SMARTROUTE_DATA_DIR=str(tmp_path))
    proc = subprocess.run(
        [sys.executable, "-c", "import config"], cwd=SRC_DIR, env=env,
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "no city profile" in proc.stderr
