"""Authenticated, bounded first-party browser telemetry; no public ingestion endpoint."""
import json
import time
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..ratelimit import _hit
from ..services.analytics import PARENT_EVENTS, STUDENT_EVENTS, record, safe_properties
from .browser import require_session

router = APIRouter(prefix="/browser", tags=["analytics"])


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str = Field(max_length=40)
    properties: dict[str, str | int] = Field(default_factory=dict, max_length=8)


@router.post("/{role}/events", status_code=204)
def ingest(role: Literal["parent", "student"], body: EventIn, request: Request, db: Session = Depends(get_db)):
    row, _, _ = require_session(request, role, db)
    if body.name not in (STUDENT_EVENTS if role == "student" else PARENT_EVENTS):
        raise HTTPException(422, "Unknown browser event")
    props = safe_properties(body.properties)
    if props != body.properties or len(json.dumps(props)) > 512:
        raise HTTPException(422, "Only fixed event properties are allowed")
    if not _hit(db, f"analytics:{role}:{row.subject_id}", 60, int(time.time() // 60)):
        db.commit()
        raise HTTPException(429, "Analytics rate limit")
    record(db, body.name, row.family_id, f"web:{role}:{row.subject_id}:{body.id}",
           student_id=row.subject_id if role == "student" else None, source=role + "_web", **props)
    db.commit()
