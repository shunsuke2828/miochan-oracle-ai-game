#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def epoch_ms(value: str) -> int:
    timezone = "+00:00" if value.endswith("Z") else value[-6:]
    parsed = datetime.strptime(value[:19] + timezone, "%Y-%m-%dT%H:%M:%S%z")
    fraction = re.search(r"\.(\d+)", value)
    milliseconds = int((fraction.group(1) if fraction else "0")[:3].ljust(3, "0"))
    return int(parsed.timestamp() * 1000) + milliseconds


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return round(ordered[index], 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_json", type=Path)
    parser.add_argument("--game-start-ms", type=int, required=True)
    parser.add_argument("--hold-until-ms", type=int, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    endpoint_status: Counter[str] = Counter()
    endpoint_counts: Counter[str] = Counter()
    request_seconds: Counter[int] = Counter()
    game_endpoint_counts: Counter[str] = Counter()
    durations: dict[str, list[float]] = defaultdict(list)
    first_request_ms: int | None = None
    last_request_ms: int | None = None

    with args.raw_json.open(encoding="utf-8") as source:
        for line in source:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            metric = record.get("metric")
            data = record.get("data") or {}
            tags = data.get("tags") or {}
            endpoint = tags.get("endpoint", "untagged")
            if metric == "http_reqs":
                time_value = data.get("time")
                if not time_value:
                    continue
                timestamp_ms = epoch_ms(time_value)
                value = int(data.get("value", 1))
                status = str(tags.get("status", "unknown"))
                endpoint_counts[endpoint] += value
                endpoint_status[f"{endpoint}:{status}"] += value
                request_seconds[timestamp_ms // 1000] += value
                first_request_ms = timestamp_ms if first_request_ms is None else min(first_request_ms, timestamp_ms)
                last_request_ms = timestamp_ms if last_request_ms is None else max(last_request_ms, timestamp_ms)
                if args.game_start_ms <= timestamp_ms < args.game_start_ms + 60_000:
                    game_endpoint_counts[endpoint] += value
            elif metric == "http_req_duration":
                durations[endpoint].append(float(data.get("value", 0)))

    game_start_second = args.game_start_ms // 1000
    game_buckets = [request_seconds.get(game_start_second + offset, 0) for offset in range(60)]
    hold_start_second = game_start_second
    hold_seconds = max(1, (args.hold_until_ms - args.game_start_ms) // 1000)
    hold_buckets = [request_seconds.get(hold_start_second + offset, 0) for offset in range(hold_seconds)]
    errors = sum(
        count
        for key, count in endpoint_status.items()
        if key.rsplit(":", 1)[-1].isdigit() and int(key.rsplit(":", 1)[-1]) >= 400
    )

    report = {
        "request_window": {
            "first": datetime.fromtimestamp(first_request_ms / 1000).isoformat() if first_request_ms else None,
            "last": datetime.fromtimestamp(last_request_ms / 1000).isoformat() if last_request_ms else None,
        },
        "requests": {
            "total": sum(endpoint_counts.values()),
            "errors_http_4xx_5xx": errors,
            "endpoint_counts": dict(sorted(endpoint_counts.items())),
            "endpoint_status": dict(sorted(endpoint_status.items())),
        },
        "game_first_60_seconds": {
            "total_requests": sum(game_buckets),
            "average_rps": round(sum(game_buckets) / 60, 2),
            "peak_one_second_rps": max(game_buckets, default=0),
            "minimum_one_second_rps": min(game_buckets, default=0),
            "endpoint_counts": dict(sorted(game_endpoint_counts.items())),
        },
        "game_to_hold_end": {
            "seconds": hold_seconds,
            "total_requests": sum(hold_buckets),
            "average_rps": round(sum(hold_buckets) / hold_seconds, 2),
            "peak_one_second_rps": max(hold_buckets, default=0),
        },
        "latency_ms": {
            endpoint: {
                "count": len(values),
                "p50": percentile(values, 0.50),
                "p95": percentile(values, 0.95),
                "p99": percentile(values, 0.99),
                "max": round(max(values), 3) if values else None,
            }
            for endpoint, values in sorted(durations.items())
        },
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
