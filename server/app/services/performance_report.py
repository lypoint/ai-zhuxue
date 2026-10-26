"""Matched per-attempt residuals, never differences between unrelated percentiles."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import math

from fastapi import HTTPException
from ..models import PerformanceTrace, Family
from ..local_time import as_utc


def quantiles(values):
    values = sorted(values)
    def percentile(fraction):
        if not values:
            return None
        position = (len(values) - 1) * fraction
        low, high = math.floor(position), math.ceil(position)
        return round(values[low] + (values[high] - values[low]) * (position - low), 3)
    return {"samples": len(values), "p50_ms": percentile(0.5), "p95_ms": percentile(0.95)}


def report(db, start, end):
    begin = datetime.combine(start, datetime.min.time(), timezone.utc)
    finish = datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc)
    # shortcut: bounded raw-trace scan; move to daily aggregates when operational volume requires it.
    rows = db.query(PerformanceTrace).join(Family, Family.id == PerformanceTrace.family_id).filter(
        PerformanceTrace.occurred_at >= begin - timedelta(hours=1), PerformanceTrace.occurred_at < finish + timedelta(hours=1),
        Family.access_disabled.is_(False)).limit(50_001).all()
    if len(rows) > 50_000:
        raise HTTPException(422, "Too many timing rows; choose a narrower date range")
    browsers = {(row.trace_id, row.family_id, row.student_id): row for row in rows if row.source == "browser"}
    groups = {}
    for row in rows:
        if row.source != "server" or not begin <= as_utc(row.occurred_at) < finish:
            continue
        key = (row.operation, row.node, row.variant, row.model, row.mode, row.input_kind, row.result, row.attempt > 1)
        group = groups.setdefault(key, {"server_samples":0, "paired_samples":0, "browser_errors":0,
                                       "negative_residual_samples":0, "metrics":defaultdict(list)})
        group["server_samples"] += 1
        server = json.loads(row.metrics)
        for metric, value in server.items():
            group["metrics"][metric].append(value)
        browser_row = browsers.get((row.trace_id, row.family_id, row.student_id))
        if not browser_row or browser_row.operation != row.operation:
            continue
        group["paired_samples"] += 1
        group["browser_errors"] += browser_row.result in ("error", "cancelled")
        # Failed browser attempts have incomplete durations; keep counts without mixing success latency.
        if browser_row.result in ("error", "cancelled"):
            continue
        browser = json.loads(browser_row.metrics)
        for metric, value in browser.items():
            group["metrics"][metric].append(value)
        # Envelopes encompass both directions and uninstrumented proxy/queue time, NOT one-way latency.
        negative = False
        for name, outer, inner in [
            ("edge_api_headers_residual_ms", browser.get("edge_upstream_headers_ms"), server.get("server_headers_ms")),
            ("browser_edge_headers_residual_ms", browser.get("browser_headers_ms"), browser.get("edge_upstream_headers_ms")),
            ("first_delta_path_residual_ms", browser.get("browser_first_delta_ms"), server.get("server_first_delta_ms")),
        ]:
            if outer is None or inner is None:
                continue
            value = outer - inner
            if value < 0:
                negative = True
            else:
                group["metrics"][name].append(value)
        group["negative_residual_samples"] += negative
    result = []
    for key, group in groups.items():
        operation, node, variant, model, mode, input_kind, outcome, retry = key
        result.append({"operation":operation,"node":node,"variant":variant,"model":model,
                       "mode":mode,"input_kind":input_kind,"result":outcome,"retry":retry,
                       **{name:value for name,value in group.items() if name != "metrics"},
                       "metrics":{name:quantiles(values) for name, values in group["metrics"].items()}})
    return {"start":start.isoformat(),"end":end.isoformat(),"timezone":"UTC","groups":result,
            "browser_samples_untrusted":True,
            "interpretation":"Compare identical model/mode/input/result/retry groups across baseline/direct. Residuals are round-trip envelopes, not causal speedup or one-way network times."}
