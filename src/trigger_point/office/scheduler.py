"""Runs while the Office runs. When a scheduled message comes due it asks the Director to send it,
and Gmail's send is still held in the Office for a click. Nothing here can send by itself."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from typing import Protocol

from trigger_point.workflow.feedback import FeedbackService

TICK_SECONDS = 30.0


class Sender(Protocol):
    def send(self, mission_id: str, text: str) -> None: ...


def tick(
    feedback: FeedbackService, runner: Sender, driver: Callable[[], list[str]] | None = None
) -> list[str]:
    if driver is not None:
        with contextlib.suppress(Exception):  # the send loop below must still run
            driver()
    started = []
    for mission in feedback.engine.missions(limit=50):
        for outreach_id in feedback.due_sends(mission.id):
            runner.send(mission.id, f"Send a test email for outreach_id {outreach_id}.")
            started.append(outreach_id)
    return started


def start(
    feedback: FeedbackService, runner: Sender, driver: Callable[[], list[str]] | None = None
) -> threading.Event:
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(TICK_SECONDS):
            tick(feedback, runner, driver)

    threading.Thread(target=loop, daemon=True, name="trigger_point-scheduler").start()
    return stop
