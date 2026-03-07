"""Narrator announcement text helpers."""

from __future__ import annotations

import random
from datetime import datetime


def build_welcome_text(name: str, current_time: datetime) -> str:
    time_phrase = _time_of_day_phrase(current_time)
    options = [
        f"{time_phrase}, {name}" if time_phrase else f"Hello {name}",
        f"Hello {name}",
        f"Hey {name}",
        f"Good to see you, {name}",
        f"{name} has joined",
    ]
    return random.choice(options)


def build_farewell_text(name: str) -> str:
    return random.choice(
        [
            f"See you later, {name}",
            f"Bye {name}",
            f"Until next time, {name}",
            f"{name} has left",
        ]
    )


def _time_of_day_phrase(current_time: datetime) -> str | None:
    hour = current_time.hour
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 18:
        return "Good afternoon"
    if 18 <= hour < 24:
        return "Good evening"
    return None
