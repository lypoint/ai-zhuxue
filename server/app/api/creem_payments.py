import asyncio
import json
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .deps import current_guardian
from ..db import get_db
from ..models import Guardian, StoreSubscription
from ..services import creem_billing as creem, store_billing as store

router = APIRouter(tags=["creem-test"])


class CheckoutInput(BaseModel):
    product_code: str = Field(pattern=r"^family_monthly_[1-9][0-9]{0,3}$")


class VerifyInput(BaseModel):
    checkout_id: str = Field(pattern=r"^ch_[A-Za-z0-9]{10,64}$")


@router.get("/parent/creem/catalog")
def catalog(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    try:
        return creem.catalog(guardian.family_id, db)
    except store.StoreError as exc:
        raise HTTPException(503, str(exc)) from None


@router.post("/parent/creem/checkout")
def checkout(body: CheckoutInput, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    try:
        return creem.checkout(guardian.family_id, body.product_code, db)
    except store.StoreError as exc:
        raise HTTPException(503, str(exc)) from None


@router.post("/parent/creem/verify")
async def verify(body: VerifyInput, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    try:
        creem.authorize(guardian.family_id, db)
        return await asyncio.to_thread(store.verify_family, guardian.family_id, creem.CHANNEL, body.checkout_id)
    except store.StoreError as exc:
        raise HTTPException(503, str(exc)) from None


@router.get("/parent/creem/manage")
def manage(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    try:
        token = creem.authorize(guardian.family_id, db)
        row = db.query(StoreSubscription).filter_by(family_id=guardian.family_id, channel=creem.CHANNEL).order_by(StoreSubscription.id.desc()).first()
        if not row:
            raise HTTPException(404, "No Creem test subscription found.")
        data = creem.request("GET", "/subscriptions?subscription_id=" + row.chain_key)
        creem.owned(data, token)
        result = creem.request("POST", "/customers/billing", {"customer_id": creem.entity_id(data["customer"])})
        url = result["customer_portal_link"]
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc not in ("creem.io", "www.creem.io") or not parts.path.startswith("/test/my-orders/"):
            raise store.StoreError("Invalid Creem test portal URL.")
        return {"url": url}
    except store.StoreError as exc:
        raise HTTPException(503, str(exc)) from None


@router.post("/payments/creem/test/notify")
async def notify(request: Request, db: Session = Depends(get_db)):
    creem.configured()
    raw = b""
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 65536:
            raise HTTPException(413, "Notification too large.")
        raw += chunk
    creem.verify_signature(raw, request.headers.get("creem-signature", ""))
    try:
        event = json.loads(raw)
        kind = event["eventType"]
        obj = event["object"]
        reference = None
        if kind == "checkout.completed" or kind.startswith("subscription."):
            reference = obj["id"]
        elif kind in ("refund.created", "dispute.created"):
            reference = creem.entity_id(obj.get("subscription"))
        if reference:
            key = "creem:" + event["id"]
            store.enqueue(creem.CHANNEL, key, reference, db)
            await asyncio.to_thread(store.process_event, key)
        return {"ok": True}
    except Exception:
        db.rollback()
        raise HTTPException(503, "Notification was not processed. Please retry.") from None
