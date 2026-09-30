"""Tests for the /api/unified-games parser and endpoint wiring.

Fixtures are real responses captured from gamesheetstats.com (ICSHL 2025-26
final/OT games and a 2026-27 scheduled game).
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

from gamesheet import GameSheetClient
from gamesheet.config import BROWSER_HEADERS

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "unified_games.json").read_text())


def make_client(season="10450"):
    return GameSheetClient(season_id=season)


def test_session_sends_browser_headers():
    client = make_client("15154")
    h = client._session.headers
    assert h["User-Agent"] == BROWSER_HEADERS["User-Agent"]
    assert h["Origin"] == "https://gamesheetstats.com"
    assert h["Referer"] == "https://gamesheetstats.com/seasons/15154/games"


def test_parse_final_game():
    raw = FIXTURES["final"]
    game = make_client()._parse_unified_game(raw)

    assert game.id == str(raw["gameId"])
    assert game.status == "final"
    assert game.date == raw["date"]
    assert game.scheduled_time == raw["time"]
    assert game.location == raw["location"]
    assert game.game_number == raw["number"]
    assert game.home.name == raw["home"]["title"]
    assert game.visitor.name == raw["visitor"]["title"]
    assert game.home.division == raw["home"]["division"]["title"]
    assert game.home.logo_url == raw["home"]["logo"]
    assert game.scoreboard.total == {
        "home": raw["home"]["goals"],
        "visitor": raw["visitor"]["goals"],
    }
    assert game.scoreboard.periods["1"] == {
        "home": raw["home"]["goalsByPeriod"]["1"],
        "visitor": raw["visitor"]["goalsByPeriod"]["1"],
    }


def test_parse_record_string_dashes():
    raw = FIXTURES["final"]
    game = make_client()._parse_unified_game(raw)
    w, l, t, otl = (int(x) for x in raw["home"]["overallRecord"].split("-"))
    assert (game.home.wins, game.home.losses, game.home.ties, game.home.otl) == (w, l, t, otl)


def test_parse_overtime_flag():
    game = make_client()._parse_unified_game(FIXTURES["overtime"])
    assert game.has_overtime is True
    assert "ot_1" in game.scoreboard.periods


def test_parse_scheduled_game_has_no_score_periods():
    game = make_client("15154")._parse_unified_game(FIXTURES["scheduled"])
    assert game.status == "scheduled"
    assert game.scoreboard.periods == {}
    assert game.has_overtime is False


def test_get_season_games_pages_until_total():
    client = make_client()
    page1 = [FIXTURES["final"]] * 2
    page2 = [FIXTURES["overtime"]]
    responses = [
        {"data": page1, "meta": {"total": 3}},
        {"data": page2, "meta": {"total": 3}},
    ]
    calls = []

    def fake_get(url, params=None):
        calls.append(params)
        resp = MagicMock()
        resp.json.return_value = responses[len(calls) - 1]
        return resp

    client._get = fake_get
    games = client.get_season_games(page_size=2)
    assert len(games) == 3
    assert [c["offset"] for c in calls] == ["0", "2"]


def test_schedule_and_scores_filter_by_division():
    client = make_client()
    final = client._parse_unified_game(FIXTURES["final"])
    sched = client._parse_unified_game(FIXTURES["scheduled"])
    client._season_games_cache = ([final, sched], float("inf"))

    div = FIXTURES["final"]["home"]["division"]["id"]
    assert all(g.status == "final" for g in client.get_scores(str(div)))
    assert final in client.get_schedule(str(div))
