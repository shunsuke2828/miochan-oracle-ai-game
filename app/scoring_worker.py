from __future__ import annotations

import logging
import os
import signal
import threading
from typing import Any

from .config import settings
from .database import build_repository
from .rescue_service import build_rescue_service


LOGGER = logging.getLogger("mio-scoring-worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class ScoringWorker:
    def __init__(self, rescue: Any, *, concurrency: int, poll_seconds: float) -> None:
        self.rescue = rescue
        self.concurrency = max(1, min(concurrency, 4))
        self.poll_seconds = max(0.1, poll_seconds)
        self.stop_event = threading.Event()

    def stop(self, *_: object) -> None:
        self.stop_event.set()

    def _run_slot(self, slot: int) -> None:
        while not self.stop_event.is_set():
            try:
                did_work = self.rescue.process_next_finalization()
                if not did_work:
                    did_work = self.rescue.process_next_pending_turn()
                if not did_work:
                    self.stop_event.wait(self.poll_seconds)
            except Exception:
                LOGGER.exception("scoring slot failed: slot=%s", slot)
                self.stop_event.wait(max(1.0, self.poll_seconds))

    def run(self) -> None:
        threads = [
            threading.Thread(
                target=self._run_slot,
                args=(slot,),
                name=f"mio-scoring-{slot}",
                daemon=True,
            )
            for slot in range(1, self.concurrency + 1)
        ]
        for thread in threads:
            thread.start()
        LOGGER.info("scoring worker ready: concurrency=%s", self.concurrency)
        self.stop_event.wait()
        for thread in threads:
            thread.join(timeout=10)


def main() -> int:
    repository, warning = build_repository(settings)
    if warning:
        LOGGER.warning(warning)
    rescue = build_rescue_service(repository)
    if not callable(getattr(rescue, "process_next_finalization", None)):
        LOGGER.error("dedicated scoring requires the ADB rescue service")
        return 2
    worker = ScoringWorker(
        rescue,
        concurrency=int(os.getenv("MIO_SCORING_CONCURRENCY", "2")),
        poll_seconds=float(os.getenv("MIO_SCORING_POLL_SECONDS", "0.5")),
    )
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    try:
        worker.run()
    finally:
        close = getattr(repository, "close", None)
        if callable(close):
            close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
