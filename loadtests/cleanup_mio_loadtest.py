#!/usr/bin/env python3
"""Delete only Mio load-test participants matching an exact run prefix."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


def request_json(url: str, *, method: str = "GET", payload: object | None = None) -> object:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    response = request_json(f"{base_url}/api/admin/participants")
    participants = response.get("participants") if isinstance(response, dict) else response
    if not isinstance(participants, list):
        raise RuntimeError("unexpected admin participant response")
    selected = [
        item["session_id"]
        for item in participants
        if isinstance(item, dict)
        and not item.get("is_seed")
        and str(item.get("nickname", "")).startswith(args.prefix)
    ]
    print(json.dumps({"prefix": args.prefix, "matched": len(selected)}, ensure_ascii=False))
    if not args.execute:
        return 0

    deleted = 0
    for index in range(0, len(selected), 100):
        batch = selected[index : index + 100]
        result = request_json(
            f"{base_url}/api/admin/participants",
            method="DELETE",
            payload={"session_ids": batch},
        )
        if isinstance(result, dict):
            deleted += int(result.get("deleted", 0))
        print(json.dumps(result, ensure_ascii=False))
    print(json.dumps({"prefix": args.prefix, "deleted_total": deleted}, ensure_ascii=False))
    return 0 if deleted == len(selected) else 2


if __name__ == "__main__":
    raise SystemExit(main())
