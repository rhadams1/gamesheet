#!/usr/bin/env python3
"""Poll a live game and print score updates.

Usage:
    python examples/poll_live_game.py --game 2765429 --season 13920
    python examples/poll_live_game.py --game 2765429 --season 13920 --interval 15
"""

import argparse
import sys
import os

# Allow running from the repo root without installing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gamesheet import GameSheetClient, LiveGamePoller, Game, GameEvent


def main():
    parser = argparse.ArgumentParser(description="Poll a live GameSheet game")
    parser.add_argument("--game", required=True, help="Game ID")
    parser.add_argument("--season", required=True, help="Season ID (for live scoring endpoint)")
    parser.add_argument("--interval", type=int, default=30, help="Poll interval in seconds (default: 30)")
    args = parser.parse_args()

    client = GameSheetClient(season_id=args.season)

    # Fetch initial game info
    game = client.get_game(args.game)
    print(f"Game #{game.game_number}: {game.home.name} vs {game.visitor.name}")
    print(f"Status: {game.status}")
    print(f"Location: {game.location}")
    print(f"Scheduled: {game.scheduled_time}")
    print()

    poller = LiveGamePoller(
        client,
        game_ids=[args.game],
        interval=args.interval,
        season_id=args.season,
    )

    @poller.on_update
    def on_update(g: Game):
        home_score = g.scoreboard.total.get("home", 0)
        visitor_score = g.scoreboard.total.get("visitor", 0)
        home_sog = g.scoreboard.total_shots.get("home", 0)
        visitor_sog = g.scoreboard.total_shots.get("visitor", 0)
        print(
            f"[{g.status}] "
            f"{g.home.name} {home_score} - {visitor_score} {g.visitor.name}  "
            f"(SOG: {home_sog}-{visitor_sog})"
        )

    @poller.on_goal
    def on_goal(g: Game, event: GameEvent):
        side = "HOME" if event.team_side == "home" else "AWAY"
        print(f"  GOAL! ({side}) #{event.player_number} {event.player_name}")

    @poller.on_status_change
    def on_status(g: Game, old: str, new: str):
        print(f"  Status: {old} -> {new}")

    print(f"Polling every {args.interval}s... (Ctrl+C to stop)")
    print()

    try:
        poller.start()
    except KeyboardInterrupt:
        poller.stop()
        print("\nStopped.")


if __name__ == "__main__":
    main()
