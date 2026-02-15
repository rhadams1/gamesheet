#!/usr/bin/env python3
"""Fetch completed game results for a season/division.

Usage:
    python examples/get_season_scores.py --season 10450 --division Central
    python examples/get_season_scores.py --season 10450  # all divisions
"""

import argparse
import sys
import os

# Allow running from the repo root without installing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gamesheet import GameSheetClient


def main():
    parser = argparse.ArgumentParser(description="Fetch GameSheet season scores")
    parser.add_argument("--season", required=True, help="Season ID (e.g. 10450)")
    parser.add_argument("--division", default=None, help="Division name (e.g. Central)")
    parser.add_argument("--include-exhibition", action="store_true", help="Include exhibition games")
    args = parser.parse_args()

    client = GameSheetClient(season_id=args.season)

    # List divisions
    divisions = client.get_divisions()
    print(f"Season {args.season} — {len(divisions)} divisions:")
    for div in divisions:
        print(f"  {div.id}: {div.title}")
    print()

    # Filter to requested division or use all
    if args.division:
        div_id = client.get_division_id(args.division)
        if not div_id:
            print(f"Division '{args.division}' not found.")
            sys.exit(1)
        target_divisions = [(div_id, args.division)]
    else:
        target_divisions = [(div.id, div.title) for div in divisions]

    for div_id, div_name in target_divisions:
        games = client.get_scores(
            division_id=div_id,
            include_exhibition=args.include_exhibition,
        )
        print(f"--- {div_name} ({len(games)} games) ---")
        for game in games:
            home_score = game.scoreboard.total.get("home", 0)
            visitor_score = game.scoreboard.total.get("visitor", 0)
            ot = " (OT)" if game.has_overtime else ""
            so = " (SO)" if game.has_shootout else ""
            print(
                f"  {game.date:>20s}  "
                f"{game.visitor.name:>25s} {visitor_score} @ "
                f"{game.home.name:<25s} {home_score}{ot}{so}"
            )
        print()


if __name__ == "__main__":
    main()
