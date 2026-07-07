#!/usr/bin/env python3
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    os.environ["MIO_DATA_MODE"] = "adb"
    if not os.getenv("MIO_ADB_PASSWORD"):
        os.environ["MIO_ADB_PASSWORD"] = getpass.getpass("ADB password: ")

    from app.config import Settings
    from app.database import AdbRepository

    repository = AdbRepository(Settings())
    try:
        stats = repository.stats()
        participants = repository.list_participants()
        graph = repository.network_graph()
        context, labels = repository.business_context("今月の売上と解約率は？")
        print(
            "ADB OK — "
            f"participants={stats['participants']} completed={stats['completed']} "
            f"admin_rows={len(participants)} network_nodes={len(graph['nodes'])} "
            f"grounding={'ok' if context and labels else 'missing'} "
            f"driver={repository.driver}"
        )
    finally:
        repository.close()


if __name__ == "__main__":
    main()
