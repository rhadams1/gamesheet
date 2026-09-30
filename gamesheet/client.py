"""GameSheet API client — REST API + Firestore endpoints."""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

import requests

from .config import (
    API_BASE,
    BROWSER_HEADERS,
    FIRESTORE_BASE,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    SEASON_GAMES_CACHE_TTL,
    SITE_BASE,
)
from .models import (
    Division,
    Game,
    GameEvent,
    GoalieStats,
    PlayerStats,
    Scoreboard,
    Team,
)

logger = logging.getLogger(__name__)


class GameSheetClient:
    """Unified client for GameSheet REST API and Firestore live data.

    REST API methods use ``https://gamesheetstats.com/api/...``
    Firestore methods use the Google Firestore REST endpoint for the
    ``gamesheet-production`` project.
    """

    def __init__(self, season_id: str):
        self.season_id = season_id
        self._session = requests.Session()
        self._session.headers.update(BROWSER_HEADERS)
        self._session.headers["Referer"] = f"{SITE_BASE}/seasons/{season_id}/games"
        self._divisions_cache: list[Division] | None = None
        # (games, expires_at) — shared by get_schedule/get_scores/get_divisions
        self._season_games_cache: tuple[list[Game], float] | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        """GET with timeout and retry on 5xx."""
        last_exc: Exception | None = None
        for attempt in range(1 + MAX_RETRIES):
            try:
                resp = self._session.get(
                    url, params=params, timeout=REQUEST_TIMEOUT
                )
                if resp.status_code >= 500 and attempt < MAX_RETRIES:
                    time.sleep(1 * (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    time.sleep(1 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _parse_firestore_value(val: dict):
        """Recursively convert Firestore typed values to plain Python."""
        if "stringValue" in val:
            return val["stringValue"]
        if "integerValue" in val:
            return int(val["integerValue"])
        if "doubleValue" in val:
            return val["doubleValue"]
        if "booleanValue" in val:
            return val["booleanValue"]
        if "nullValue" in val:
            return None
        if "mapValue" in val:
            fields = val["mapValue"].get("fields", {})
            return {k: GameSheetClient._parse_firestore_value(v) for k, v in fields.items()}
        if "arrayValue" in val:
            values = val["arrayValue"].get("values", [])
            return [GameSheetClient._parse_firestore_value(v) for v in values]
        if "timestampValue" in val:
            return val["timestampValue"]
        return val

    @staticmethod
    def _parse_record_string(record_str: str) -> dict[str, int]:
        """Parse 'W-L-T-OTL' or '(W - L - T)' style records into a dict."""
        nums = [int(x) for x in re.findall(r"\d+", record_str)]
        result = {"wins": 0, "losses": 0, "ties": 0, "otl": 0}
        if len(nums) >= 3:
            result["wins"] = nums[0]
            result["losses"] = nums[1]
            result["ties"] = nums[2]
        if len(nums) >= 4:
            result["otl"] = nums[3]
        return result

    # ------------------------------------------------------------------
    # REST API — Season games (unified-games: schedule + scores in one call)
    # ------------------------------------------------------------------

    def get_season_games(self, page_size: int = 500, use_cache: bool = True) -> list[Game]:
        """Fetch every game in the season (scheduled, live and final).

        Uses ``/api/unified-games/<season>``, which returns teams, logos,
        divisions, rink, status and per-period goals for all games. Pages
        through ``limit``/``offset`` until ``meta.total`` is reached.
        """
        if use_cache and self._season_games_cache is not None:
            games, expires_at = self._season_games_cache
            if time.time() < expires_at:
                return games

        url = f"{API_BASE}/unified-games/{self.season_id}"
        games: list[Game] = []
        offset = 0
        while True:
            payload = self._get(url, {
                "order": "asc",
                "limit": str(page_size),
                "offset": str(offset),
            }).json()
            page = payload.get("data", [])
            games.extend(self._parse_unified_game(item) for item in page)
            total = (payload.get("meta") or {}).get("total", len(games))
            offset += len(page)
            if not page or offset >= total:
                break

        self._season_games_cache = (games, time.time() + SEASON_GAMES_CACHE_TTL)
        return games

    def _parse_unified_game(self, item: dict) -> Game:
        """Parse one game from the unified-games endpoint."""
        home = item.get("home", {}) or {}
        visitor = item.get("visitor", {}) or {}
        status = item.get("status", "")

        periods: dict[str, dict[str, int]] = {}
        if status != "scheduled":
            h_periods = home.get("goalsByPeriod", {}) or {}
            v_periods = visitor.get("goalsByPeriod", {}) or {}
            for label in h_periods:
                if label == "final":
                    continue
                periods[label] = {
                    "home": int(h_periods.get(label) or 0),
                    "visitor": int(v_periods.get(label) or 0),
                }
            periods["total"] = {
                "home": int(home.get("goals") or 0),
                "visitor": int(visitor.get("goals") or 0),
            }

        return Game(
            id=str(item.get("gameId", "")),
            season_id=self.season_id,
            status=status,
            game_type=item.get("gameType", ""),
            game_number=str(item.get("number", "")),
            location=item.get("location", ""),
            scheduled_time=item.get("time", ""),
            date=item.get("date", ""),
            home=self._unified_team(home),
            visitor=self._unified_team(visitor),
            scoreboard=Scoreboard(periods=periods),
            has_overtime=any(k.startswith("ot") for k in periods),
            has_shootout=any(k.startswith("so") for k in periods),
        )

    def _unified_team(self, data: dict) -> Team:
        division = data.get("division", {}) or {}
        return Team(
            name=data.get("title", ""),
            id=str(data.get("id", "")),
            logo_url=data.get("logo", ""),
            division=division.get("title", ""),
            division_id=str(division.get("id", "")),
            **self._parse_record_string(data.get("overallRecord", "")),
        )

    @staticmethod
    def _in_division(game: Game, division_id: str) -> bool:
        return division_id in (game.home.division_id, game.visitor.division_id)

    # ------------------------------------------------------------------
    # Divisions / schedule / scores — thin views over get_season_games()
    # (the old useSeasonDivisions / useSchedule / useScoredGames endpoints
    # were removed by GameSheet and now return 404)
    # ------------------------------------------------------------------

    def get_divisions(self) -> list[Division]:
        """List all divisions that have games this season."""
        if self._divisions_cache is not None:
            return self._divisions_cache

        seen: dict[str, str] = {}
        for game in self.get_season_games():
            for team in (game.home, game.visitor):
                if team.division_id and team.division_id not in seen:
                    seen[team.division_id] = team.division
        divisions = [Division(id=i, title=t) for i, t in sorted(seen.items(), key=lambda kv: kv[1])]
        self._divisions_cache = divisions
        return divisions

    def get_division_id(self, name: str) -> str | None:
        """Look up a division ID by exact title match."""
        for div in self.get_divisions():
            if div.title == name:
                return div.id
        return None

    def get_scores(
        self,
        division_id: str,
        game_type: str = "overall",
        include_exhibition: bool = False,
    ) -> list[Game]:
        """Completed games for a division (regular season unless exhibition requested)."""
        return [
            g for g in self._filter_games(division_id, game_type, include_exhibition)
            if g.status in ("final", "unofficial")
        ]

    def get_schedule(
        self,
        division_id: str,
        game_type: str = "overall",
        include_exhibition: bool = False,
    ) -> list[Game]:
        """Full schedule (completed + upcoming) for a division."""
        return self._filter_games(division_id, game_type, include_exhibition)

    def _filter_games(self, division_id: str, game_type: str, include_exhibition: bool) -> list[Game]:
        games = [g for g in self.get_season_games() if self._in_division(g, str(division_id))]
        if game_type == "exhibition":
            return [g for g in games if g.game_type == "exhibition"]
        if include_exhibition:
            return games
        return [g for g in games if g.game_type != "exhibition"]

    # ------------------------------------------------------------------
    # REST API — Player stats (columnar tableData format)
    # ------------------------------------------------------------------

    def get_player_stats(
        self,
        division_id: str | None = None,
        sort: str = "-pts",
        limit: int = 100,
    ) -> list[PlayerStats]:
        """Fetch skater stat leaders."""
        url = f"{API_BASE}/usePlayers/getPlayerStandings/{self.season_id}"
        params: dict[str, str] = {
            "sort": sort,
            "filter[limit]": str(limit),
        }
        if division_id:
            params["filter[divisions]"] = division_id

        data = self._get(url, params).json()
        td = data.get("tableData", data)

        names = td.get("names", [])
        count = len(names)
        results: list[PlayerStats] = []

        for i in range(count):
            n = names[i]
            team_list = td.get("teamNames", {}).get("data", [[]])[i] if i < len(td.get("teamNames", {}).get("data", [])) else []
            team_name = team_list[0]["title"] if team_list else ""
            team_id = str(team_list[0]["id"]) if team_list else ""
            positions = td.get("positions", {}).get("data", [[]])[i] if i < len(td.get("positions", {}).get("data", [])) else []

            results.append(PlayerStats(
                id=str(n.get("id", "")),
                name=f"{n.get('firstName', '')} {n.get('lastName', '')}".strip(),
                team=team_name,
                team_id=team_id,
                jersey=str(td.get("jersey", {}).get("data", [""])[i]) if i < len(td.get("jersey", {}).get("data", [])) else "",
                position=positions[0] if positions else "",
                gp=self._col_int(td, "gp", i),
                g=self._col_int(td, "g", i),
                a=self._col_int(td, "a", i),
                pts=self._col_int(td, "pts", i),
                pim=self._col_int(td, "pim", i),
                ppg=self._col_int(td, "ppg", i),
                shg=self._col_int(td, "shg", i),
                gwg=self._col_int(td, "gwg", i),
            ))

        return results

    # ------------------------------------------------------------------
    # REST API — Goalie stats (columnar tableData format)
    # ------------------------------------------------------------------

    def get_goalie_stats(
        self,
        division_id: str | None = None,
        sort: str = "gaa",
        limit: int = 100,
    ) -> list[GoalieStats]:
        """Fetch goalie stat leaders."""
        url = f"{API_BASE}/useGoalies/getGoalieStandings/{self.season_id}"
        params: dict[str, str] = {
            "sort": sort,
            "filter[limit]": str(limit),
        }
        if division_id:
            params["filter[divisions]"] = division_id

        data = self._get(url, params).json()
        td = data.get("tableData", data)

        names = td.get("names", [])
        count = len(names)
        results: list[GoalieStats] = []

        for i in range(count):
            n = names[i]
            team_list = td.get("teamNames", {}).get("data", [[]])[i] if i < len(td.get("teamNames", {}).get("data", [])) else []
            team_name = team_list[0]["title"] if team_list else ""
            team_id = str(team_list[0]["id"]) if team_list else ""

            gaa_val = self._col_val(td, "gaa", i)
            svpct_val = self._col_val(td, "svpct", i)

            results.append(GoalieStats(
                id=str(n.get("id", "")),
                name=f"{n.get('firstName', '')} {n.get('lastName', '')}".strip(),
                team=team_name,
                team_id=team_id,
                jersey=str(td.get("jersey", {}).get("data", [""])[i]) if i < len(td.get("jersey", {}).get("data", [])) else "",
                gp=self._col_int(td, "gp", i),
                wins=self._col_int(td, "wins", i),
                losses=self._col_int(td, "losses", i),
                ties=self._col_int(td, "ties", i),
                otl=self._col_int(td, "otl", i),
                saves=self._col_int(td, "sa", i) - self._col_int(td, "ga", i),
                goals_against=self._col_int(td, "ga", i),
                shots_against=self._col_int(td, "sa", i),
                gaa=float(gaa_val) if gaa_val else 0.0,
                sv_pct=float(svpct_val) if svpct_val else 0.0,
                shutouts=self._col_int(td, "so", i),
            ))

        return results

    @staticmethod
    def _col_int(td: dict, key: str, idx: int) -> int:
        """Safely extract an int from a tableData column."""
        col = td.get(key, {})
        data = col.get("data", []) if isinstance(col, dict) else []
        if idx < len(data) and data[idx] is not None:
            return int(data[idx])
        return 0

    @staticmethod
    def _col_val(td: dict, key: str, idx: int):
        """Safely extract a raw value from a tableData column."""
        col = td.get(key, {})
        data = col.get("data", []) if isinstance(col, dict) else []
        if idx < len(data):
            return data[idx]
        return None

    # ------------------------------------------------------------------
    # REST API — Matchup & Box Score
    # ------------------------------------------------------------------

    def get_matchup(self, game_id: str) -> dict:
        """Fetch head-to-head matchup data (raw dict)."""
        url = f"{API_BASE}/useMatchup/{game_id}"
        return self._get(url).json()

    def get_box_score(self, game_id: str) -> dict | None:
        """Fetch post-game box score. Returns None if game is still live."""
        url = f"{API_BASE}/useBoxScore/getGameStats/{self.season_id}/games/{game_id}"
        try:
            return self._get(url).json()
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise

    # ------------------------------------------------------------------
    # Firestore — Game detail (teams, status, location)
    # ------------------------------------------------------------------

    def get_game(self, game_id: str) -> Game:
        """Fetch full game data from Firestore ``games/{gameId}``."""
        url = f"{FIRESTORE_BASE}/games/{game_id}"
        doc = self._get(url).json()
        fields = doc.get("fields", {})
        pv = self._parse_firestore_value

        status = pv(fields.get("status", {})) or ""
        game_type = pv(fields.get("gameType", {})) or ""
        location = pv(fields.get("location", {})) or ""
        number = pv(fields.get("number", {})) or ""
        scheduled = pv(fields.get("scheduledStartTime", {})) or ""
        has_ot = bool(pv(fields.get("hasOvertime", {})))
        has_so = bool(pv(fields.get("hasShootout", {})))

        home_map = pv(fields.get("home", {})) or {}
        visitor_map = pv(fields.get("visitor", {})) or {}
        season_map = pv(fields.get("season", {})) or {}
        league_map = pv(fields.get("league", {})) or {}
        assoc_map = pv(fields.get("association", {})) or {}

        return Game(
            id=game_id,
            season_id=str(season_map.get("id", self.season_id)),
            status=status,
            game_type=game_type,
            game_number=str(number),
            location=location,
            scheduled_time=scheduled,
            home=self._firestore_team(home_map),
            visitor=self._firestore_team(visitor_map),
            has_overtime=has_ot,
            has_shootout=has_so,
            league=league_map.get("title", ""),
            association=assoc_map.get("title", ""),
        )

    @staticmethod
    def _firestore_team(data: dict) -> Team:
        """Build a Team from parsed Firestore team map."""
        rec = data.get("record", {}) or {}
        div = data.get("division", {}) or {}
        return Team(
            name=data.get("title", ""),
            id=str(data.get("id", "")),
            logo_url=data.get("logo", ""),
            division=div.get("title", "") if isinstance(div, dict) else str(div),
            wins=int(rec.get("wins", 0)),
            losses=int(rec.get("losses", 0)),
            ties=int(rec.get("ties", 0)),
            otl=int(rec.get("overtimeShootoutLosses", 0)),
            goals_for=int(rec.get("goalsFor", 0)),
            goals_against=int(rec.get("goalsAgainst", 0)),
        )

    # ------------------------------------------------------------------
    # Firestore — Live scoreboard + events
    # ------------------------------------------------------------------

    def get_live_scoreboard(self, game_id: str, season_id: str | None = None) -> Scoreboard:
        """Fetch live scoreboard from ``seasons/{sid}/games/{gid}``."""
        sid = season_id or self.season_id
        url = f"{FIRESTORE_BASE}/seasons/{sid}/games/{game_id}"
        doc = self._get(url).json()
        fields = doc.get("fields", {})
        pv = self._parse_firestore_value

        computed = pv(fields.get("computed", {})) or {}
        return Scoreboard(
            periods=computed.get("scoreboard", {}),
            shots=computed.get("shots", {}),
        )

    def get_game_events(self, game_id: str, season_id: str | None = None) -> list[GameEvent]:
        """Fetch all events from ``seasons/{sid}/games/{gid}``."""
        sid = season_id or self.season_id
        url = f"{FIRESTORE_BASE}/seasons/{sid}/games/{game_id}"
        doc = self._get(url).json()
        fields = doc.get("fields", {})
        pv = self._parse_firestore_value

        events_map = pv(fields.get("events", {})) or {}
        result: list[GameEvent] = []

        for event_id, ev in events_map.items():
            if not isinstance(ev, dict):
                continue
            time_data = ev.get("time", {}) or {}
            for_data = ev.get("for", {}) or {}
            team_data = for_data.get("team", {}) or {}
            # Goals use "scorer", penalties use "player"
            player_data = for_data.get("scorer") or for_data.get("player") or {}

            # Extract period from clock string (format "PP:MM:SS")
            clock = time_data.get("clock", "")
            period = ""
            if clock and ":" in clock:
                parts = clock.split(":")
                if len(parts) == 3:
                    period = parts[0]

            result.append(GameEvent(
                id=ev.get("id", event_id),
                type=ev.get("type", ""),
                period=period,
                clock=clock,
                real_time=time_data.get("real", ""),
                team_side=team_data.get("vs", ""),
                player_name=f"{player_data.get('firstName', '')} {player_data.get('lastName', '')}".strip(),
                player_number=str(player_data.get("jersey", "")),
                raw=ev,
            ))

        return result

    def get_live_game_full(self, game_id: str, season_id: str | None = None) -> Game:
        """Fetch game detail + live scoreboard + events in two calls.

        Combines Firestore ``games/{gid}`` (teams/status) with
        ``seasons/{sid}/games/{gid}`` (scores/events).
        """
        game = self.get_game(game_id)
        sid = season_id or game.season_id or self.season_id

        url = f"{FIRESTORE_BASE}/seasons/{sid}/games/{game_id}"
        resp = self._session.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 404:
            # The live doc is created when scoring starts; before puck drop
            # the game only exists in games/{gid}.
            return game
        resp.raise_for_status()
        fields = resp.json().get("fields", {})
        pv = self._parse_firestore_value

        computed = pv(fields.get("computed", {})) or {}
        game.scoreboard = Scoreboard(
            periods=computed.get("scoreboard", {}),
            shots=computed.get("shots", {}),
        )
        game.has_overtime = bool(computed.get("hasOvertime", False))
        game.has_shootout = bool(computed.get("hasShootout", False))

        # Override status from computed if available (more current)
        live_status = computed.get("status", "")
        if live_status:
            game.status = live_status

        # Parse events
        events_map = pv(fields.get("events", {})) or {}
        events: list[GameEvent] = []
        for event_id, ev in events_map.items():
            if not isinstance(ev, dict):
                continue
            time_data = ev.get("time", {}) or {}
            for_data = ev.get("for", {}) or {}
            team_data = for_data.get("team", {}) or {}
            # Goals use "scorer", penalties use "player"
            player_data = for_data.get("scorer") or for_data.get("player") or {}

            clock = time_data.get("clock", "")
            period = ""
            if clock and ":" in clock:
                parts = clock.split(":")
                if len(parts) == 3:
                    period = parts[0]

            events.append(GameEvent(
                id=ev.get("id", event_id),
                type=ev.get("type", ""),
                period=period,
                clock=clock,
                real_time=time_data.get("real", ""),
                team_side=team_data.get("vs", ""),
                player_name=f"{player_data.get('firstName', '')} {player_data.get('lastName', '')}".strip(),
                player_number=str(player_data.get("jersey", "")),
                raw=ev,
            ))

        game.events = events
        return game
