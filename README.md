# GameSheet Python Client

Reusable Python package for the GameSheet API — both the REST API (completed games, standings, player stats) and Firestore endpoints (live scores, period-by-period, shots on goal, play-by-play events).

Built for Flyers Cup, FC RAMS, and other GameSheet-powered hockey projects.

## Install

```bash
# From another project — editable install
pip install -e /Users/badams/Projects/hockey-rankings/gamesheet

# Or just add to sys.path
import sys
sys.path.insert(0, '/Users/badams/Projects/hockey-rankings/gamesheet')
```

Only dependency: `requests`

## Quick Start

```python
from gamesheet import GameSheetClient

# ICSHL 2025-26 season
client = GameSheetClient(season_id="10450")

# List divisions
for div in client.get_divisions():
    print(f"{div.id}: {div.title}")

# Get completed games
games = client.get_scores(division_id="57742")
for game in games:
    h = game.scoreboard.total["home"]
    v = game.scoreboard.total["visitor"]
    print(f"{game.visitor.name} {v} @ {game.home.name} {h}")

# Get player stat leaders
leaders = client.get_player_stats(division_id="57742", sort="-pts", limit=10)
for p in leaders:
    print(f"{p.name} ({p.team}) — {p.g}G {p.a}A {p.pts}PTS")
```

## Live Game Polling

```python
from gamesheet import GameSheetClient, LiveGamePoller

client = GameSheetClient(season_id="13920")
poller = LiveGamePoller(client, game_ids=["2765429"], interval=15)

@poller.on_update
def on_update(game):
    h = game.scoreboard.total["home"]
    v = game.scoreboard.total["visitor"]
    print(f"{game.home.name} {h} - {v} {game.visitor.name}")

@poller.on_goal
def on_goal(game, event):
    print(f"GOAL! {event.player_name} ({event.team_side})")

poller.start()  # Blocking — or use poller.start_background()
```

## API Methods

### REST API (gamesheetstats.com)

| Method | Description |
|--------|-------------|
| `get_divisions()` | List all divisions for the season |
| `get_division_id(name)` | Look up division ID by name |
| `get_scores(division_id)` | Completed game results |
| `get_schedule(division_id)` | Full schedule (completed + upcoming) |
| `get_player_stats(division_id)` | Skater stat leaders |
| `get_goalie_stats(division_id)` | Goalie stat leaders |
| `get_matchup(game_id)` | Head-to-head matchup data |
| `get_box_score(game_id)` | Post-game box score (None if live) |

### Firestore (live data)

| Method | Description |
|--------|-------------|
| `get_game(game_id)` | Game detail (teams, status, location) |
| `get_live_scoreboard(game_id)` | Period-by-period scores + SOG |
| `get_game_events(game_id)` | All game events (goals, penalties, etc.) |
| `get_live_game_full(game_id)` | Combined: game detail + scores + events |

## Known Season IDs (2025-26)

| League | Season ID |
|--------|-----------|
| ICSHL  | 10450     |
| SHSHL  | 11546     |
| SJHSHL | 11761     |
| APAC   | 11581     |
| CPIHL  | 10841     |

## Examples

```bash
# Fetch scores for ICSHL Central division
python examples/get_season_scores.py --season 10450 --division Central

# Poll a live game every 15 seconds
python examples/poll_live_game.py --game 2765429 --season 13920 --interval 15
```

## Package Structure

```
gamesheet/
├── gamesheet/
│   ├── __init__.py   # Exports: GameSheetClient, LiveGamePoller, models
│   ├── client.py     # Main API client (REST + Firestore)
│   ├── live.py       # Live game poller with callbacks
│   ├── models.py     # Dataclasses: Game, Team, Scoreboard, etc.
│   └── config.py     # Constants, known seasons, base URLs
├── examples/
│   ├── get_season_scores.py
│   └── poll_live_game.py
├── requirements.txt
└── README.md
```
