"""Data classes for GameSheet API responses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Division:
    id: str
    title: str


@dataclass
class Team:
    name: str
    id: str = ""
    logo_url: str = ""
    division: str = ""
    division_id: str = ""
    wins: int = 0
    losses: int = 0
    ties: int = 0
    otl: int = 0
    goals_for: int = 0
    goals_against: int = 0

    @property
    def record(self) -> str:
        """Format as W-L-T-OTL."""
        parts = [str(self.wins), str(self.losses), str(self.ties)]
        if self.otl:
            parts.append(str(self.otl))
        return "-".join(parts)


@dataclass
class Scoreboard:
    """Period-by-period and total scores + shots."""

    # Keyed by period label ("01", "02", "03", "ot", "so", "total")
    # Each value is {"home": int, "visitor": int}
    periods: dict[str, dict[str, int]] = field(default_factory=dict)
    shots: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def total(self) -> dict[str, int]:
        return self.periods.get("total", {"home": 0, "visitor": 0})

    @property
    def total_shots(self) -> dict[str, int]:
        return self.shots.get("total", {"home": 0, "visitor": 0})


@dataclass
class GameEvent:
    """A single game event (goal, penalty, goalie change, etc.)."""

    id: str = ""
    type: str = ""
    period: str = ""
    clock: str = ""
    real_time: str = ""
    team_side: str = ""  # "home" or "visitor"
    player_name: str = ""
    player_number: str = ""
    description: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class Game:
    """A single game, from either REST API or Firestore."""

    id: str = ""
    season_id: str = ""
    status: str = ""  # "final", "in progress", "upcoming", etc.
    game_type: str = ""  # "overall", "exhibition", "tournament"
    game_number: str = ""
    location: str = ""
    scheduled_time: str = ""
    date: str = ""
    home: Team = field(default_factory=Team)
    visitor: Team = field(default_factory=Team)
    scoreboard: Scoreboard = field(default_factory=Scoreboard)
    events: list[GameEvent] = field(default_factory=list)
    has_overtime: bool = False
    has_shootout: bool = False
    league: str = ""
    association: str = ""


@dataclass
class PlayerStats:
    id: str = ""
    name: str = ""
    team: str = ""
    team_id: str = ""
    jersey: str = ""
    position: str = ""
    gp: int = 0
    g: int = 0
    a: int = 0
    pts: int = 0
    pim: int = 0
    ppg: int = 0
    shg: int = 0
    gwg: int = 0


@dataclass
class GoalieStats:
    id: str = ""
    name: str = ""
    team: str = ""
    team_id: str = ""
    jersey: str = ""
    gp: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    otl: int = 0
    saves: int = 0
    goals_against: int = 0
    shots_against: int = 0
    gaa: float = 0.0
    sv_pct: float = 0.0
    shutouts: int = 0
