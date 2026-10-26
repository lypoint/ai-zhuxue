"""Bounded first-party timings. No content, URLs, credentials or wall-clock subtraction."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import math
import re
import time
import uuid

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import settings

log = logging.getLogger(__name__)
current = ContextVar("performance_trace", default=None)
METRICS = {"server_headers_ms", "server_total_ms", "server_first_delta_ms", "server_done_ms",
           "policy_ms", "prepare_images_ms", "context_ms", "input_review_ms", "model_ms",
           "model_first_token_ms", "output_review_ms", "persist_ms", "upload_receive_ms",
           "image_sanitize_ms", "storage_upload_ms", "image_review_ms", "storage_read_ms",
           "browser_headers_ms", "browser_first_delta_ms", "browser_done_ms", "browser_total_ms",
           "edge_upstream_headers_ms"}
BROWSER_METRICS = {name for name in METRICS if name.startswith("browser_")} | {"edge_upstream_headers_ms"}


def safe_metrics(values, allowed=METRICS):
    return {name: round(float(value), 3) for name, value in values.items()
            if name in allowed and type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 3_600_000}


class Trace:
    def __init__(self, operation, trace_id=None, clock=time.perf_counter):
        try:
            self.id = str(uuid.UUID(trace_id))
        except (ValueError, TypeError, AttributeError):
            self.id = str(uuid.uuid4())
        self.operation, self.clock = operation, clock
        self.start = clock()
        self.metrics = {}
        self.family_id = self.student_id = self.message_id = None
        self.attempt = 1
        self.result = "incomplete"
        self.mode = "buffered"
        self.input = "text"
        self.model = "unknown"
        self.node = settings.performance_node
        self.variant = settings.performance_variant

    def elapsed(self):
        return (self.clock() - self.start) * 1000

    def mark(self, name):
        self.metrics.setdefault(name, self.elapsed())

    @contextmanager
    def span(self, name):
        start = self.clock()
        try:
            yield
        finally:
            self.metrics[name] = self.metrics.get(name, 0) + (self.clock() - start) * 1000


def bind(student):
    trace = current.get()
    if trace:
        trace.family_id, trace.student_id = student.family_id, student.id
    return trace


@contextmanager
def span(name):
    trace = current.get()
    if trace:
        with trace.span(name):
            yield
    else:
        yield


def mark(name):
    trace = current.get()
    if trace:
        trace.mark(name)


def model_label(provider, model):
    trace = current.get()
    label = f"{provider}/{model}"
    if trace and re.fullmatch(r"[a-zA-Z0-9_./:@+-]{1,120}", label):
        trace.model = label


def save(db, trace, source="server", metrics=None, result=None):
    from ..models import Family, PerformanceTrace
    if not trace.family_id or not (family := db.get(Family, trace.family_id)) or family.access_disabled:
        return
    values = dict(trace_id=trace.id, source=source, family_id=trace.family_id, student_id=trace.student_id,
                  operation=trace.operation, node=trace.node, variant=trace.variant, model=trace.model,
                  mode=trace.mode, input_kind=trace.input, result=result or trace.result,
                  message_id=trace.message_id, attempt=trace.attempt, occurred_at=datetime.now(timezone.utc),
                  metrics=json.dumps(safe_metrics(trace.metrics if metrics is None else metrics)))
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    db.execute(insert(PerformanceTrace).values(**values).on_conflict_do_nothing(
        index_elements=["trace_id", "source", "family_id"]))


def persist(trace):
    if not trace.family_id:
        return
    try:
        from ..db import SessionLocal
        with SessionLocal.begin() as db:
            save(db, trace)
    except Exception:
        # No exception message: DB errors can contain connection details or SQL parameters.
        log.warning("performance_write_failed")
