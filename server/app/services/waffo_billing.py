"""Waffo authenticated checkout and authoritative subscription verification."""
import base64
import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Family, StoreAccount, StoreEvent, StoreSubscription, SubscriptionOrder
from . import store_billing as store
from .subscription import get_status

CHANNEL = "waffo"
PRICES = {1: "9.99", 2: "14.99", 10: "49.99", 100: "499.99"}
ORDER_FIELDS = """id storeId status testMode merchantProvidedBuyerIdentity metadata
 orderMerchantExternalId billingPeriod currency isInTrial willRenew currentPeriodNumber
 currentPeriodStart currentPeriodEnd createdAt supersededByOrderId changeOriginOrderId
 productVersion { productId billingPeriod metadata prices { currency priceInfo { amount trialAmount } } }
 payments { id status testMode periodNumber createdAt isFullyRefunded
 amount { amount currency } chargebacks { status } }"""


def test_accounts():
    return {v.strip().lower() for v in settings.waffo_test_account_tokens.split(",") if v.strip()}


def configured():
    if not settings.waffo_enabled:
        raise HTTPException(404, "Checkout is unavailable.")
    if not settings.waffo_merchant_id or not settings.waffo_store_id:
        raise store.StoreError("Waffo merchant configuration is incomplete.")
    store.cipher()


def request(path: str, body: dict, *, idempotency_key: str | None = None):
    configured()
    try:
        raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
        stamp = str(int(time.time()))
        digest = base64.b64encode(hashlib.sha256(raw).digest()).decode()
        canonical = f"POST\n{path}\n{stamp}\n{digest}".encode()
        key = serialization.load_pem_private_key(Path(settings.waffo_private_key_path).read_bytes(), None)
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
            raise ValueError()
        headers = {"Content-Type": "application/json", "X-Merchant-Id": settings.waffo_merchant_id,
                   "X-Timestamp": stamp, "X-Signature": base64.b64encode(
                       key.sign(canonical, padding.PKCS1v15(), hashes.SHA256())).decode()}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        with httpx.Client(timeout=20) as client:
            response = client.post("https://api.waffo.ai" + path, content=raw, headers=headers)
            response.raise_for_status()
            envelope = response.json()
        if envelope.get("errors") or not isinstance(envelope.get("data"), dict):
            raise ValueError()
        return envelope["data"]
    except (OSError, ValueError, TypeError, httpx.HTTPError):
        raise store.StoreError("Waffo is unavailable. Please retry.") from None


def query(text: str, variables: dict):
    return request("/v1/graphql", {"query": text, "variables": variables})


def authorize(family_id: int, db: Session):
    configured()
    token = store.account(family_id, db).account_token
    if settings.env == "prod" and settings.waffo_environment == "test" and token.lower() not in test_accounts():
        raise HTTPException(403, "This family is not enabled for test payments.")
    return token


def binding(token: str):
    return hmac.new(settings.store_token_secret.encode(), (CHANNEL + ":" + token).encode(), hashlib.sha256).hexdigest()


def safe_url(url: str, *, portal=False):
    parts = urlsplit(url)
    allowed = (parts.netloc == "pancake.waffo.ai" and parts.path.startswith("/consumer/portal/")) if portal else (
        parts.netloc == "pancake.waffo.ai" and re.fullmatch(r"/store/[^/]+/checkout/cs_[A-Za-z0-9_-]+", parts.path) or
        parts.netloc == "checkout.waffo.ai" and re.fullmatch(r"/[^/]+/checkout/cs_[A-Za-z0-9_-]+", parts.path))
    if parts.scheme != "https" or not allowed or parts.fragment:
        raise store.StoreError("Invalid Waffo destination.")
    return url


def timestamp(value):
    try:
        return store.naive(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (ValueError, AttributeError, TypeError):
        raise store.StoreError("Waffo subscription dates are unavailable.") from None


def metadata(value):
    try:
        result = json.loads(value) if isinstance(value, str) else value
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise store.StoreError("Invalid Waffo metadata.") from None


def validate_product(data, code):
    seats = int(code.removeprefix("family_monthly_"))
    try:
        prices = {p["currency"]: p["priceInfo"] for p in data["prices"]}
        usd = prices["USD"]
        if (seats not in PRICES or data["billingPeriod"] != "monthly" or
                Decimal(usd["amount"]) != Decimal(PRICES[seats]) or
                Decimal(usd.get("trialAmount") or "0") != 0 or
                metadata(data["metadata"]).get("trialDays") != 30):
            raise ValueError()
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise store.StoreError("Waffo plans must match the website's USD monthly prices and free 30-day trial.") from None


def product(code):
    product_id = store.products(CHANNEL).get(code)
    if not product_id or not re.fullmatch(r"PROD_[A-Za-z0-9]{10,64}", product_id):
        raise HTTPException(422, "This plan is unavailable.")
    data = query("""query($id:String!){subscriptionProduct(id:$id){id storeId status billingPeriod metadata
        prices {currency priceInfo {amount trialAmount}} group {rules {sharedTrial selfServicePlanChange}}}}""", {"id": product_id})["subscriptionProduct"]
    if not data or data["storeId"] != settings.waffo_store_id or data["status"] != "active":
        raise store.StoreError("This Waffo product is unavailable.")
    validate_product(data, code)
    rules = (data.get("group") or {}).get("rules") or {}
    if rules.get("sharedTrial") is not True or rules.get("selfServicePlanChange") is not False:
        raise store.StoreError("Waffo plans must share trial eligibility and disable self-service plan changes.")
    return product_id


def catalog(family_id: int, db: Session):
    owner = db.get(StoreAccount, family_id)
    if (not settings.waffo_enabled or settings.env == "prod" and settings.waffo_environment == "test"
            and (not owner or owner.account_token.lower() not in test_accounts())):
        return {"enabled": False, "items": []}
    authorize(family_id, db)
    items = [{"product_code": code, "seat_count": seats, "amount": PRICES[seats], "currency": "USD"}
             for code in store.products(CHANNEL) if (seats := int(code.removeprefix("family_monthly_"))) in PRICES]
    return {"enabled": True, "test_mode": settings.waffo_environment == "test",
            "has_subscription": db.query(StoreSubscription.id).filter_by(family_id=family_id, channel=CHANNEL).first() is not None,
            "items": sorted(items, key=lambda i: i["seat_count"])}


def orders_for(token):
    return query("""query($store:String!,$buyer:String!){subscriptionOrders(storeId:$store,
        filter:{merchantProvidedBuyerIdentity:{eq:$buyer}},limit:100){id status isInTrial currentPeriodEnd}}""",
        {"store": settings.waffo_store_id, "buyer": token})["subscriptionOrders"]


def checkout(family_id: int, code: str, db: Session):
    token = authorize(family_id, db)
    product_id = product(code)
    db.query(Family).filter_by(id=family_id).with_for_update().one()
    store.block_other_channel(family_id, CHANNEL, db)
    status = get_status(family_id, db)
    if status["plan"] == "permanent" or status["active"] and status["plan"] != "free_trial":
        raise HTTPException(409, "Manage your existing subscription before purchasing again.")
    if int(code.removeprefix("family_monthly_")) < status["used_seats"]:
        raise HTTPException(409, "This plan has too few child profiles.")
    if db.query(SubscriptionOrder.id).filter_by(family_id=family_id, status="pending").first():
        raise HTTPException(409, "Resolve your pending payment before purchasing.")
    history = orders_for(token)
    if any(o["status"] in ("pending", "active", "trialing", "canceling", "past_due") for o in history):
        raise HTTPException(409, "An existing Waffo subscription needs attention. Refresh or manage it first.")
    prefix = "waffo-checkout:" + token + ":"
    pending = db.query(StoreEvent).filter(StoreEvent.event_key.startswith(prefix)).order_by(StoreEvent.created_at.desc()).first()
    saved = json.loads(store.cipher().decrypt(pending.encrypted_reference.encode())) if pending else None
    if saved and timestamp(saved["expires_at"]) > datetime.utcnow():
        if saved["product"] != product_id:
            raise HTTPException(409, "Finish the pending checkout before choosing another plan.")
        reference, url = saved["reference"], safe_url(saved["url"])
    else:
        reference = "waffo-" + uuid.uuid4().hex
        body = {"productId": product_id, "currency": "USD", "expiresInSeconds": 900,
                "successUrl": settings.web_parent_origin + "/subscription?waffo_return=" + reference,
                "orderMerchantExternalId": reference,
                "metadata": {"account_token": token, "binding": binding(token)}}
        # Never force withTrial=true: it bypasses the platform's eligibility protection.
        if any(o["status"] not in ("closed", "pending") for o in history):
            body["withTrial"] = False
        result = request("/v1/actions/checkout/create-session", body, idempotency_key=reference)
        url = safe_url(result["checkoutUrl"])
        saved = {"reference": reference, "product": product_id, "url": url, "expires_at": result["expiresAt"]}
        db.add(StoreEvent(event_key=prefix + reference, channel=CHANNEL, processed=True,
                         encrypted_reference=store.cipher().encrypt(json.dumps(saved).encode()).decode()))
        db.commit()
    session = request("/v1/actions/auth/issue-session-token", {"productId": product_id, "buyerIdentity": token})
    return {"reference": reference, "url": url + "#token=" + quote(session["token"], safe="")}


def verify_subscription(reference: str):
    if re.fullmatch(r"ORD_[A-Za-z0-9]{10,64}", reference):
        data = query("query($id:String!){subscriptionOrder(id:$id){" + ORDER_FIELDS + "}}", {"id": reference})["subscriptionOrder"]
    elif re.fullmatch(r"waffo-[a-f0-9]{32}", reference):
        rows = query("query($store:String!,$ref:String!){subscriptionOrders(storeId:$store,filter:{orderMerchantExternalId:{eq:$ref}},limit:2){" + ORDER_FIELDS + "}}",
                     {"store": settings.waffo_store_id, "ref": reference})["subscriptionOrders"]
        if len(rows) != 1:
            raise store.StoreError("Your subscription is still being confirmed. Please retry.")
        data = rows[0]
    else:
        raise store.StoreError("Invalid Waffo order reference.")
    if not data:
        raise store.StoreError("Waffo subscription not found.")
    custom = metadata(data["metadata"])
    token = data["merchantProvidedBuyerIdentity"]
    if (data["storeId"] != settings.waffo_store_id or data["testMode"] != (settings.waffo_environment == "test")
            or custom.get("account_token") != token or not isinstance(token, str) or
            not hmac.compare_digest(str(custom.get("binding", "")).encode(), binding(token).encode())):
        raise store.StoreError("This subscription was not created by this application.")
    if settings.env == "prod" and data["testMode"] and token.lower() not in test_accounts():
        raise store.StoreError("Test subscription is not authorized.")
    version = data["productVersion"]
    product_id = version["productId"]
    seats = store.seats_for(CHANNEL, product_id)
    validate_product(version, f"family_monthly_{seats}")
    if data["currency"] != "USD" or data["billingPeriod"] != "monthly":
        raise store.StoreError("Unexpected Waffo subscription currency or interval.")
    end, start = timestamp(data["currentPeriodEnd"]), timestamp(data["currentPeriodStart"])
    state = {"active": "active", "trialing": "trialing", "canceling": "active",
             "past_due": "grace", "canceled": "expired", "expired": "expired"}.get(data["status"], "inactive")
    if data["isInTrial"] and state == "active":
        state = "trialing"
    if data["supersededByOrderId"]:
        state = "replaced"
    payments = [p for p in data["payments"] if p["status"] == "succeeded" and
                p["periodNumber"] == data["currentPeriodNumber"] and p["testMode"] == data["testMode"]]
    payment = max(payments, key=lambda p: p["createdAt"]) if payments else None
    if state == "active" and not data["isInTrial"] and not payment:
        raise store.StoreError("The current subscription payment has not been confirmed.")
    if payment and ((Decimal(payment["amount"]["amount"]) > 0 and payment["isFullyRefunded"]) or
                    any(c["status"] not in ("won", "reversed") for c in payment["chargebacks"])):
        state = "revoked"
    if state == "grace":
        # The channel retries once, normally next day; never grant an unpaid full month.
        end = min(end, start + timedelta(days=2))
    amount = None
    if payment:
        try:
            if payment["amount"]["currency"] != "USD":
                raise ValueError()
            # GraphQL Money.amount is in minor units; ledger amounts use milliunits.
            amount = int(Decimal(payment["amount"]["amount"]) * 10)
        except (InvalidOperation, ValueError):
            raise store.StoreError("Invalid Waffo payment amount.") from None
    return store.VerifiedSubscription(CHANNEL, data["id"], data["id"], token, product_id, end, state,
        bool(data["willRenew"]) and state in ("active", "trialing", "grace"),
        linked_chain=data["changeOriginOrderId"], transaction_id=payment["id"] if payment else None,
        price_milliunits=amount, currency="USD", next_billing_at=end if data["willRenew"] and state != "grace" else None,
        period_started_at=start)


def manage(family_id: int, db: Session):
    token = authorize(family_id, db)
    result = request("/v1/actions/auth/issue-session-token", {
        "storeId": settings.waffo_store_id, "buyerIdentity": token, "purpose": "portal"})
    return {"url": safe_url(result["portalUrl"], portal=True) + "#token=" + quote(result["token"], safe="")}


def verify_signature(raw: bytes, header: str):
    configured()
    try:
        parts = dict(pair.strip().split("=", 1) for pair in header.split(","))
        stamp = parts["t"]
        age = time.time() * 1000 - int(stamp)
        if not -60_000 <= age <= 45 * 60 * 1000:
            raise ValueError()
        public = serialization.load_pem_public_key(Path(settings.waffo_webhook_public_key_path).read_bytes())
        public.verify(base64.b64decode(parts["v1"], validate=True), stamp.encode() + b"." + raw,
                      padding.PKCS1v15(), hashes.SHA256())
    except (ValueError, KeyError, OSError, InvalidSignature, TypeError):
        raise HTTPException(401, "Invalid Waffo signature.") from None
