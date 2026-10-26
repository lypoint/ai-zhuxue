"""Paddle Sandbox only: authoritative billing, using the existing family entitlement ledger."""
import hashlib
import hmac
import re
import time
from datetime import datetime

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Family, StoreAccount, StoreEvent, SubscriptionOrder
from . import store_billing as store
from .subscription import get_status

CHANNEL = "paddle_sandbox"


def configured():
    if not settings.paddle_sandbox_enabled:
        raise HTTPException(404, "Sandbox checkout is unavailable.")
    if ("_sdbx" not in settings.paddle_sandbox_api_key or
            not settings.paddle_sandbox_client_token.startswith("test_") or
            not settings.paddle_sandbox_webhook_secret):
        raise store.StoreError("Paddle Sandbox credentials are incomplete.")
    store.cipher()


def request(method: str, path: str, body=None):
    configured()
    try:
        with httpx.Client(timeout=15) as client:
            response = client.request(method, "https://sandbox-api.paddle.com" + path,
                headers={"Authorization": "Bearer " + settings.paddle_sandbox_api_key}, json=body)
            response.raise_for_status()
            return response.json()["data"]
    except (httpx.HTTPError, KeyError, ValueError):
        raise store.StoreError("Paddle Sandbox is unavailable. Please retry.") from None


def binding(token: str) -> str:
    return hmac.new(settings.store_token_secret.encode(), (CHANNEL + ":" + token).encode(), hashlib.sha256).hexdigest()


def test_accounts() -> set[str]:
    return {token.strip().lower() for token in settings.paddle_sandbox_test_account_tokens.split(",") if token.strip()}


def allow_test_purchase(token: str):
    if settings.env == "prod" and token.lower() not in test_accounts():
        raise store.StoreError("This family is not enabled for Paddle Sandbox testing.")


def authorize(family_id: int, db: Session) -> str:
    configured()
    token = store.account(family_id, db).account_token
    allow_test_purchase(token)
    return token


def monthly_price(price_id: str):
    if not re.fullmatch(r"pri_[a-z0-9]{26}", price_id):
        raise store.StoreError("Invalid Paddle Sandbox price configuration.")
    price = request("GET", "/prices/" + price_id)
    if (price["status"] != "active" or price["billing_cycle"] != {"interval": "month", "frequency": 1}
            or price.get("trial_period") or price.get("unit_price_overrides")
            or price.get("quantity") != {"minimum": 1, "maximum": 1}):
        raise store.StoreError("Sandbox plans must be active monthly prices, quantity one, without trials or overrides.")
    return price


def catalog(family_id: int, db: Session):
    if not settings.paddle_sandbox_enabled:
        return {"enabled": False, "items": []}
    owner = db.get(StoreAccount, family_id)
    if settings.env == "prod" and (not owner or owner.account_token.lower() not in test_accounts()):
        return {"enabled": False, "items": []}
    authorize(family_id, db)
    items = []
    for code, price_id in store.products(CHANNEL).items():
        price = monthly_price(price_id)
        items.append({"product_code": code, "seat_count": int(code.removeprefix("family_monthly_")),
            "amount": price["unit_price"]["amount"], "currency": price["unit_price"]["currency_code"],
            "name": price.get("name") or code})
    return {"enabled": True, "client_token": settings.paddle_sandbox_client_token,
            "items": sorted(items, key=lambda item: item["seat_count"])}


def checkout(family_id: int, code: str, db: Session):
    token = authorize(family_id, db)
    price = store.products(CHANNEL).get(code)
    if not price:
        raise HTTPException(422, "This plan is unavailable.")
    monthly_price(price)
    db.query(Family).filter_by(id=family_id).with_for_update().one()
    store.block_other_channel(family_id, CHANNEL, db)
    status = get_status(family_id, db)
    if status["plan"] == "permanent" or status["active"] and status["plan"] != "free_trial":
        raise HTTPException(409, "Manage your existing subscription before purchasing again.")
    if int(code.removeprefix("family_monthly_")) < status["used_seats"]:
        raise HTTPException(409, "This plan has too few child profiles.")
    if db.query(SubscriptionOrder.id).filter_by(family_id=family_id, status="pending").first():
        raise HTTPException(409, "Resolve your pending payment before purchasing.")
    # Serialize checkout creation per family and reuse unfinished Paddle transactions.
    prefix = "paddle-checkout:" + token + ":"
    pending = db.query(StoreEvent).filter(StoreEvent.event_key.startswith(prefix), StoreEvent.processed.is_(False)).first()
    if pending:
        tx = request("GET", "/transactions/" + store.cipher().decrypt(pending.encrypted_reference.encode()).decode())
        if tx["status"] in ("draft", "ready"):
            if tx["items"][0]["price"]["id"] != price:
                raise HTTPException(409, "Finish the pending checkout before choosing another plan.")
            return {"transaction_id": tx["id"]}
        if tx["status"] != "canceled":
            raise HTTPException(409, "Your previous payment is being confirmed. Refresh your subscription.")
        pending.processed = True
    tx = request("POST", "/transactions", {"items": [{"price_id": price, "quantity": 1}],
        "collection_mode": "automatic", "custom_data": {"account_token": token, "binding": binding(token)}})
    db.add(StoreEvent(event_key=prefix + tx["id"], channel=CHANNEL,
        encrypted_reference=store.cipher().encrypt(tx["id"].encode()).decode(), processed=False))
    db.commit()
    return {"transaction_id": tx["id"]}


def resume(family_id: int, transaction_id: str, db: Session):
    token = authorize(family_id, db)
    tx = request("GET", "/transactions/" + transaction_id)
    custom = tx.get("custom_data") or {}
    if (custom.get("account_token") != token or
            not hmac.compare_digest(str(custom.get("binding", "")).encode(), binding(token).encode())):
        raise HTTPException(409, "This checkout belongs to another family.")
    if tx["status"] == "canceled":
        raise HTTPException(409, "This checkout was canceled.")
    return {"transaction_id": tx["id"], "status": tx["status"]}


def verify_subscription(reference: str) -> store.VerifiedSubscription:
    if not re.fullmatch(r"(?:txn|sub)_[a-z0-9]{26}", reference):
        raise store.StoreError("Invalid Paddle reference.")
    transaction = None
    if reference.startswith("txn_"):
        transaction = request("GET", "/transactions/" + reference)
        if transaction["status"] != "completed" or not transaction.get("subscription_id"):
            raise store.StoreError("Payment is still pending. Please refresh after confirmation.")
        reference = transaction["subscription_id"]
    data = request("GET", "/subscriptions/" + reference)
    custom = data.get("custom_data") or {}
    token = custom.get("account_token", "")
    if (not isinstance(token, str) or not token or
            not hmac.compare_digest(str(custom.get("binding", "")).encode(), binding(token).encode())):
        raise store.StoreError("This subscription was not created by this application.")
    allow_test_purchase(token)
    items = data["items"]
    if len(items) != 1 or items[0]["quantity"] != 1:
        raise store.StoreError("Unexpected subscription items.")
    price = items[0]["price"]
    store.seats_for(CHANNEL, price["id"])
    if price["billing_cycle"] != {"interval": "month", "frequency": 1} or data.get("currency_code") != price["unit_price"]["currency_code"]:
        raise store.StoreError("Unexpected subscription billing period or currency.")
    end = (data.get("current_billing_period") or {}).get("ends_at") or data.get("canceled_at")
    if not end:
        raise store.StoreError("Subscription expiry is unavailable.")
    return store.VerifiedSubscription(CHANNEL, data["id"], data["id"], token, price["id"],
        store.naive(datetime.fromisoformat(end.replace("Z", "+00:00"))),
        "active" if data["status"] == "active" else "expired" if data["status"] == "canceled" else "inactive",
        data["status"] == "active" and not data.get("scheduled_change"),
        transaction_id=transaction["id"] if transaction else None,
        price_milliunits=int(price["unit_price"]["amount"]) * 10,
        currency=price["unit_price"]["currency_code"],
        first_paid_at=datetime.fromisoformat(data["started_at"].replace("Z", "+00:00")) if data.get("started_at") else None,
        next_billing_at=datetime.fromisoformat(data["next_billed_at"].replace("Z", "+00:00")) if data.get("next_billed_at") else None,
        period_started_at=datetime.fromisoformat(data["current_billing_period"]["starts_at"].replace("Z", "+00:00"))
            if (data.get("current_billing_period") or {}).get("starts_at") else None)


def verify_signature(raw: bytes, header: str):
    configured()
    try:
        parts = [part.strip().split("=", 1) for part in header.split(";")]
        timestamp = next(value for key, value in parts if key == "ts")
        if abs(time.time() - int(timestamp)) > 5:
            raise ValueError()
        digest = hmac.new(settings.paddle_sandbox_webhook_secret.encode(), timestamp.encode() + b":" + raw, hashlib.sha256).hexdigest()
        if not any(key == "h1" and hmac.compare_digest(value, digest) for key, value in parts):
            raise ValueError()
    except (ValueError, StopIteration, TypeError):
        raise HTTPException(401, "Invalid Paddle signature.") from None
