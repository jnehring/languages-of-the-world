from __future__ import annotations

from typing import Dict

from .base import ScrapeItem, ScrapeTask
from .speakers import SpeakerCountTask, parse_speaker_count

_TASKS: Dict[str, ScrapeTask] = {
    "speakers": SpeakerCountTask(),
}


def get_task(name: str) -> ScrapeTask:
    try:
        return _TASKS[name]
    except KeyError:
        known = ", ".join(sorted(_TASKS))
        raise SystemExit(f"Unknown task {name!r}. Available tasks: {known}")


def list_tasks() -> list[str]:
    return sorted(_TASKS)
