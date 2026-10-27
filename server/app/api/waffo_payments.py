import asyncio
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .deps import current_guardian
from ..config import settings
from ..db import get_db
from ..models import Guardian, StoreSubscription
from ..services import waffo_billing as waffo, store_billing as store

router = APIRouter(tags=["waffo"])


class CheckoutInput(BaseModel):
    product_code: str = Field(pattern=r"^family_monthly_(1|2|10|100)$")


class VerifyInput(BaseModel):
    reference: str = Field(pattern=r"^(?:waffo-[a-f0-9]{32}|ORD_[A-Za-z0-9]{10,64})$")


@router.get("/parent/waffo/catalog")
def catalog(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    try:
        return waffo.catalog(guardian.family_id, db)
    except store.StoreError as exc:
        raise HTTPException(503, str(exc)) from None


@router.post("/parent/waffo/checkout")
def checkout(body: CheckoutInput, response: Response, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return waffo.checkout(guardian.family_id, body.product_code, db)
    except store.StoreError as exc:
        raise HTTPException(503, str(exc)) from None


@router.post("/parent/waffo/verify")
def verify(body: VerifyInput, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    try:
        waffo.authorize(guardian.family_id, db)
        # The worker uses a separate session and must acquire the same family lock.
        family_id = guardian.family_id
        db.commit()
        return store.verify_family(family_id, waffo.CHANNEL, body.reference)
    except store.StoreError as exc:
        raise HTTPException(503, str(exc)) from None


@router.get("/parent/waffo/manage")
def manage(response: Response, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    try:
        return waffo.manage(guardian.family_id, db)
    except store.StoreError as exc:
        raise HTTPException(503, str(exc)) from None


@router.post("/parent/waffo/refresh")
def refresh(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    try:
        token = waffo.authorize(guardian.family_id, db)
        orders = waffo.orders_for(token)
        known = {row.chain_key for row in db.query(StoreSubscription).filter_by(
            family_id=guardian.family_id, channel=waffo.CHANNEL)}
        family_id = guardian.family_id
        db.commit()
        for order in orders:
            if order["id"] in known or order["status"] in ("active", "trialing", "canceling", "past_due"):
                store.verify_family(family_id, waffo.CHANNEL, order["id"])
        from ..services.subscription import get_status
        db.expire_all()
        return get_status(family_id, db)
    except store.StoreError as exc:
        raise HTTPException(503, str(exc)) from None


@router.post("/payments/waffo/notify")
async def notify(request: Request, db: Session = Depends(get_db)):
    raw = b""
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 65536:
            raise HTTPException(413, "Notification too large.")
        raw += chunk
    waffo.verify_signature(raw, request.headers.get("x-waffo-signature", ""))
    try:
        event = json.loads(raw)
        if event["storeId"] != settings.waffo_store_id or event["mode"] != settings.waffo_environment:
            raise HTTPException(400, "Unexpected Waffo store or environment.")
        kind, reference = event["eventType"], event["data"].get("orderId")
        if kind.startswith("subscription.") or kind in ("refund.succeeded", "chargeback.created", "chargeback.updated"):
            event_id = event.get("eventId", event.get("id"))
            emitted_at = event.get("timestamp", "")
            if (not reference or not isinstance(event_id, str) or not event_id or len(event_id) > 128
                    or not isinstance(emitted_at, str) or len(emitted_at) > 64):
                raise ValueError()
            # id can remain the order ID across renewals/cancellations. Retries preserve timestamp.
            identity = kind + ":" + event_id + ((":" + emitted_at) if emitted_at else "")
            key = "waffo:" + hashlib.sha256(identity.encode()).hexdigest()
            store.enqueue(waffo.CHANNEL, key, reference, db)
            await asyncio.to_thread(store.process_event, key)
        return {"ok": True}
    except HTTPException:
        raise
    except (ValueError, KeyError, TypeError):
        db.rollback()
        raise HTTPException(400, "Invalid Waffo notification.") from None
    except Exception:
        db.rollback()
        raise HTTPException(503, "Notification was not processed. Please retry.") from None
