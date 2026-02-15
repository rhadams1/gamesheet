"""Live game poller with event-driven callbacks."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from .client import GameSheetClient
from .models import Game, GameEvent

logger = logging.getLogger(__name__)


class LiveGamePoller:
    """Poll one or more live games and fire callbacks on changes.

    Usage::

        client = GameSheetClient(season_id="10450")
        poller = LiveGamePoller(client, game_ids=["2765429"], interval=30)

        @poller.on_update
        def handle_update(game: Game):
            print(f"{game.home.name} {game.scoreboard.total['home']} - "
                  f"{game.scoreboard.total['visitor']} {game.visitor.name}")

        @poller.on_goal
        def handle_goal(game: Game, event: GameEvent):
            print(f"GOAL! {event.player_name} ({event.team_side})")

        poller.start()  # Blocking — run in a thread for non-blocking
    """

    def __init__(
        self,
        client: GameSheetClient,
        game_ids: list[str],
        interval: int = 30,
        season_id: str | None = None,
    ):
        self.client = client
        self.game_ids = game_ids
        self.interval = interval
        self.season_id = season_id

        self._update_callbacks: list[Callable[[Game], None]] = []
        self._goal_callbacks: list[Callable[[Game, GameEvent], None]] = []
        self._status_callbacks: list[Callable[[Game, str, str], None]] = []

        self._running = False
        self._thread: threading.Thread | None = None

        # Track previous state per game for diff detection
        self._prev_scores: dict[str, dict[str, int]] = {}
        self._prev_statuses: dict[str, str] = {}
        self._prev_event_ids: dict[str, set[str]] = {}

    def on_update(self, callback: Callable[[Game], None]) -> Callable[[Game], None]:
        """Register (or use as decorator) a callback fired on any game data change."""
        self._update_callbacks.append(callback)
        return callback

    def on_goal(self, callback: Callable[[Game, GameEvent], None]) -> Callable[[Game, GameEvent], None]:
        """Register (or use as decorator) a callback fired on new goal events."""
        self._goal_callbacks.append(callback)
        return callback

    def on_status_change(self, callback: Callable[[Game, str, str], None]) -> Callable[[Game, str, str], None]:
        """Register (or use as decorator) a callback fired when game status changes."""
        self._status_callbacks.append(callback)
        return callback

    def start(self):
        """Start polling loop (blocking). Call in a thread for non-blocking."""
        self._running = True
        logger.info(
            "Starting live poller for %d game(s), interval=%ds",
            len(self.game_ids), self.interval,
        )

        while self._running:
            for game_id in self.game_ids:
                if not self._running:
                    break
                try:
                    self._poll_game(game_id)
                except Exception:
                    logger.exception("Error polling game %s", game_id)

            if self._running:
                time.sleep(self.interval)

    def start_background(self) -> threading.Thread:
        """Start polling in a background daemon thread. Returns the thread."""
        self._thread = threading.Thread(target=self.start, daemon=True)
        self._thread.start()
        return self._thread

    def stop(self):
        """Stop polling."""
        self._running = False
        logger.info("Poller stopped")

    def _poll_game(self, game_id: str):
        """Fetch latest data for a single game and fire callbacks."""
        game = self.client.get_live_game_full(game_id, season_id=self.season_id)

        # Detect score change
        current_total = game.scoreboard.total
        prev_total = self._prev_scores.get(game_id, {})
        score_changed = current_total != prev_total

        # Detect status change
        current_status = game.status
        prev_status = self._prev_statuses.get(game_id, "")
        status_changed = prev_status != "" and current_status != prev_status

        # Detect new goal events
        goal_types = {"GameEvent.TeamShooterGoalOnProtectedNet"}
        current_event_ids = {e.id for e in game.events}
        prev_ids = self._prev_event_ids.get(game_id, set())
        new_event_ids = current_event_ids - prev_ids

        new_goals = [
            e for e in game.events
            if e.id in new_event_ids and e.type in goal_types
        ]

        # Update state
        self._prev_scores[game_id] = current_total
        self._prev_statuses[game_id] = current_status
        self._prev_event_ids[game_id] = current_event_ids

        # Fire callbacks
        if score_changed or status_changed or new_goals:
            for cb in self._update_callbacks:
                try:
                    cb(game)
                except Exception:
                    logger.exception("Error in update callback")

        for goal_event in new_goals:
            for cb in self._goal_callbacks:
                try:
                    cb(game, goal_event)
                except Exception:
                    logger.exception("Error in goal callback")

        if status_changed:
            for cb in self._status_callbacks:
                try:
                    cb(game, prev_status, current_status)
                except Exception:
                    logger.exception("Error in status callback")
