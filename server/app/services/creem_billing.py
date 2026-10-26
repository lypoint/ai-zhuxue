"""Creem test payments only; reuse the encrypted family subscription ledger."""
import hashlib
import hmac
import re
from datetime import datetime
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Family, StoreAccount, StoreEvent, SubscriptionOrder
from . import store_billing as store
from .subscription import get_status

CHANNEL = "creem_test"


def configured():
    if not settings.creem_test_enabled:
        raise HTTPException(404, "Test checkout is unavailable.")
    if not settings.creem_test_api_key.startswith("creem_test_") or not settings.creem_test_webhook_secret:
        raise store.StoreError("Creem test credentials are incomplete.")
    store.cipher()


def request(method: str, path: str, body=None):
    configured()
    try:
        with httpx.Client(timeout=20) as client:
            response = client.request(method, "https://test-api.creem.io/v1" + path,
                headers={"x-api-key": settings.creem_test_api_key, "User-Agent": "AIStudyNestTestIntegration/1.0"}, json=body)
            response.raise_for_status()
            data = response.json()
            if data.get("mode") != "test" and not (path == "/customers/billing" and "customer_portal_link" in data):
                raise ValueError()
            return data
    except (httpx.HTTPError, KeyError, ValueError, AttributeError):
        raise store.StoreError("Creem test service is unavailable. Please retry.") from None


def entity_id(value):
    return value.get("id") if isinstance(value, dict) else value


def binding(token: str):
    return hmac.new(settings.store_token_secret.encode(), (CHANNEL + ":" + token).encode(), hashlib.sha256).hexdigest()


def test_accounts():
    return {value.strip().lower() for value in settings.creem_test_account_tokens.split(",") if value.strip()}


def allow_test_purchase(token):
    if settings.env == "prod" and token.lower() not in test_accounts():
        raise store.StoreError("This family is not enabled for Creem testing.")


def authorize(family_id: int, db: Session):
    configured()
    token = store.account(family_id, db).account_token
    allow_test_purchase(token)
    return token


def owned(data, token=None):
    custom = data.get("metadata") or {}
    owner = custom.get("account_token")
    if (data.get("mode") != "test" or not isinstance(owner, str) or not owner or
            not hmac.compare_digest(str(custom.get("binding", "")).encode(), binding(owner).encode())):
        raise store.StoreError("This test payment was not created by this application.")
    if token is not None and owner != token:
        raise HTTPException(409, "This checkout belongs to another family.")
    allow_test_purchase(owner)
    return owner


def monthly_product(product_id):
    if not re.fullmatch(r"prod_[A-Za-z0-9]{10,64}", product_id):
        raise store.StoreError("Invalid Creem test product configuration.")
    product = request("GET", "/products?" + urlencode({"product_id": product_id}))
    if (product.get("status") != "active" or product.get("billing_type") != "recurring" or
            product.get("billing_period") != "every-month" or product.get("trial_period_days") or
            product.get("usage_prices") or product.get("pay_what_you_want")):
        raise store.StoreError("Test products must be active monthly subscriptions without trials or usage charges.")
    return product


def catalog(family_id: int, db: Session):
    owner = db.get(StoreAccount, family_id)
    if not settings.creem_test_enabled or settings.env == "prod" and (not owner or owner.account_token.lower() not in test_accounts()):
        return {"enabled": False, "items": []}
    authorize(family_id, db)
    items = []
    for code, product_id in store.products(CHANNEL).items():
        product = monthly_product(product_id)
        items.append({"product_code": code, "seat_count": int(code.removeprefix("family_monthly_")),
            "amount": str(product["price"]), "currency": product["currency"], "name": product["name"]})
    return {"enabled": True, "items": sorted(items, key=lambda item: item["seat_count"])}


def checkout_result(data):
    url = data.get("checkout_url", "")
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc not in ("creem.io", "www.creem.io") or not parts.path.startswith("/test/"):
        raise store.StoreError("Invalid Creem test checkout URL.")
    return {"checkout_id": data["id"], "url": url}


def checkout(family_id: int, code: str, db: Session):
    token = authorize(family_id, db)
    product = store.products(CHANNEL).get(code)
    if not product:
        raise HTTPException(422, "This plan is unavailable.")
    monthly_product(product)
    db.query(Family).filter_by(id=family_id).with_for_update().one()
    store.block_other_channel(family_id, CHANNEL, db)
    status = get_status(family_id, db)
    if status["plan"] == "permanent" or status["active"] and status["plan"] != "free_trial":
        raise HTTPException(409, "Manage your existing subscription before purchasing again.")
    if int(code.removeprefix("family_monthly_")) < status["used_seats"]:
        raise HTTPException(409, "This plan has too few child profiles.")
    if db.query(SubscriptionOrder.id).filter_by(family_id=family_id, status="pending").first():
        raise HTTPException(409, "Resolve your pending payment before purchasing.")
    prefix = "creem-checkout:" + token + ":"
    pending = db.query(StoreEvent).filter(StoreEvent.event_key.startswith(prefix)).order_by(StoreEvent.created_at.desc()).first()
    if pending:
        data = request("GET", "/checkouts?" + urlencode({"checkout_id": store.cipher().decrypt(pending.encrypted_reference.encode()).decode()}))
        owned(data, token)
        if data["status"] == "pending":
            if entity_id(data["product"]) != product:
                raise HTTPException(409, "Finish the pending checkout before choosing another plan.")
            return checkout_result(data)
        if data["status"] != "expired":
            raise HTTPException(409, "Your previous payment is being confirmed. Refresh your subscription.")
    data = request("POST", "/checkouts", {"product_id": product, "units": 1,
        "success_url": settings.web_parent_origin + "/subscription?creem_return=1",
        "metadata": {"account_token": token, "binding": binding(token)}})
    owned(data, token)
    result = checkout_result(data)
    # Checkout references are recovery records, not unpaid webhook jobs.
    db.add(StoreEvent(event_key=prefix + data["id"], channel=CHANNEL,
        encrypted_reference=store.cipher().encrypt(data["id"].encode()).decode(), processed=True))
    db.commit()
    return result


def verify_subscription(reference: str):
    if not re.fullmatch(r"(?:ch|sub)_[A-Za-z0-9]{10,64}", reference):
        raise store.StoreError("Invalid Creem test reference.")
    checkout_data = None
    if reference.startswith("ch_"):
        checkout_data = request("GET", "/checkouts?" + urlencode({"checkout_id": reference}))
        owned(checkout_data)
        if checkout_data["status"] != "completed" or checkout_data.get("units", 1) != 1:
            raise store.StoreError("Payment is still pending. Please retry after confirmation.")
        reference = entity_id(checkout_data.get("subscription"))
        if not isinstance(reference, str) or not re.fullmatch(r"sub_[A-Za-z0-9]{10,64}", reference):
            raise store.StoreError("Subscription is not available yet.")
    data = request("GET", "/subscriptions?" + urlencode({"subscription_id": reference}))
    token = owned(data)
    product_id = entity_id(data["product"])
    store.seats_for(CHANNEL, product_id)
    monthly_product(product_id)
    items = data.get("items") or []
    if len(items) != 1 or items[0].get("units", 1) != 1 or items[0].get("product_id") != product_id:
        raise store.StoreError("Unexpected Creem subscription items.")
    if checkout_data and (entity_id(checkout_data["product"]) != product_id or owned(checkout_data) != token):
        raise store.StoreError("Checkout and subscription do not match.")
    end = data.get("current_period_end_date")
    if not end or not data.get("last_transaction_id"):
        raise store.StoreError("Paid subscription period is unavailable.")
    transaction = request("GET", "/transactions?" + urlencode({"transaction_id": data["last_transaction_id"]}))
    if entity_id(transaction.get("subscription")) != data["id"]:
        raise store.StoreError("Transaction does not match subscription.")
    paid = transaction.get("status") == "paid" and not transaction.get("refunded_amount")
    ended_normally = data["status"] == "expired" or (
        data["status"] == "canceled" and data.get("canceled_at") and
        datetime.fromisoformat(data["canceled_at"].replace("Z", "+00:00")) >=
        datetime.fromisoformat(end.replace("Z", "+00:00")))
    return store.VerifiedSubscription(CHANNEL, data["id"], data["id"], token, product_id,
        store.naive(datetime.fromisoformat(end.replace("Z", "+00:00"))),
        ("active" if data["status"] in ("active", "scheduled_cancel") else
         "expired" if ended_normally else "inactive") if paid else "revoked",
        paid and data["status"] == "active", transaction_id=transaction["id"],
        price_milliunits=int(transaction["amount_paid"]) * 10 if transaction.get("amount_paid") is not None else None,
        currency=transaction.get("currency"),
        first_paid_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")) if data.get("created_at") else None,
        next_billing_at=datetime.fromisoformat(data["next_transaction_date"].replace("Z", "+00:00")) if data.get("next_transaction_date") else None,
        period_started_at=datetime.fromisoformat(data["current_period_start_date"].replace("Z", "+00:00")) if data.get("current_period_start_date") else None)


def verify_signature(raw: bytes, header: str):
    configured()
    digest = hmac.new(settings.creem_test_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(header.encode(), digest.encode()):
        raise HTTPException(401, "Invalid Creem signature.")
