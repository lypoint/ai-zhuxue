"""Store authorities determine products, account ownership and entitlement periods."""
import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
import jwt
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Family, Subscription, StoreAccount, StoreEvent, StoreSubscription, StoreTransaction

log = logging.getLogger(__name__)


class StoreError(Exception):
    pass


def products(channel: str) -> dict[str, str]:
    try:
        mapping = json.loads(settings.store_products_json or "{}").get(channel, {})
        if not isinstance(mapping, dict) or len(set(mapping.values())) != len(mapping):
            raise ValueError()
        for code, product in mapping.items():
            seats = int(code.removeprefix("family_monthly_"))
            if code != f"family_monthly_{seats}" or not 1 <= seats <= 1000 or not isinstance(product, str) or not product:
                raise ValueError()
        return mapping
    except (ValueError, TypeError, AttributeError):
        raise StoreError("商店商品映射配置无效") from None


def seats_for(channel: str, product: str) -> int:
    for code, registered in products(channel).items():
        if product == registered:
            return int(code.removeprefix("family_monthly_"))
    raise StoreError("未注册的月订阅商品")


def cipher() -> Fernet:
    try:
        return Fernet(settings.store_token_secret.encode())
    except (ValueError, TypeError):
        raise StoreError("商店令牌加密密钥未配置") from None


def configured(channel: str):
    cipher()
    try:
        if channel == "appstore":
            if settings.env == "prod" and settings.apple_environment != "Production":
                raise ValueError()
            apple_verifier()
            if not settings.apple_key_id or not settings.apple_issuer_id:
                raise ValueError()
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey, SECP256R1
            key = load_pem_private_key(Path(settings.apple_private_key_path).read_bytes(), password=None)
            if not isinstance(key, EllipticCurvePrivateKey) or not isinstance(key.curve, SECP256R1):
                raise ValueError()
        else:
            if not settings.google_pubsub_email or not settings.google_pubsub_audience:
                raise ValueError()
            if not google_gateway():
                credentials = json.loads(Path(settings.google_service_account_path).read_text())
                if not credentials.get("client_email"):
                    raise ValueError()
                jwt.encode({"iss": credentials["client_email"]}, credentials["private_key"], algorithm="RS256")
    except StoreError:
        raise
    except Exception:
        raise StoreError("商店验单凭据未配置，暂不可购买") from None


def account(family_id: int, db: Session) -> StoreAccount:
    db.query(Family).filter_by(id=family_id).with_for_update().one()
    row = db.get(StoreAccount, family_id)
    if row is None:
        row = StoreAccount(family_id=family_id, account_token=str(uuid.uuid4()))
        db.add(row)
        db.commit()
    return row


@dataclass(frozen=True)
class VerifiedSubscription:
    channel: str
    chain: str
    reference: str
    account_token: str
    product: str
    expires: datetime
    state: str
    auto_renew: bool
    linked_chain: str | None = None
    needs_acknowledgement: bool = False
    transaction_id: str | None = None
    price_milliunits: int | None = None
    currency: str | None = None
    first_paid_at: datetime | None = None
    next_billing_at: datetime | None = None
    period_started_at: datetime | None = None


def naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def entitlement_expiry(row) -> datetime:
    end = naive(row.expires_at)
    if isinstance(row, StoreSubscription) and row.state in ("active", "grace", "expired"):
        end += timedelta(seconds=int(row.trial_extension_seconds or 0))
    return end


def active(row: StoreSubscription) -> bool:
    now = datetime.utcnow()
    eligible = row.state in ("active", "grace") or (
        row.state == "expired" and naive(row.expires_at) <= now and (row.trial_extension_seconds or 0) > 0)
    return eligible and entitlement_expiry(row) > now


def test_accounts() -> set[str]:
    return {value.strip().lower() for value in settings.store_test_account_tokens.split(",") if value.strip()}


def allow_test_purchase(account_token: str):
    if settings.env == "prod" and account_token.lower() not in test_accounts():
        raise StoreError("该家庭未获授权使用商店测试订阅")


def apple_verifier(environment: str | None = None):
    from appstoreserverlibrary.models.Environment import Environment
    from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier
    environment = environment or settings.apple_environment
    if settings.env == "prod" and environment != "Production" and not test_accounts():
        raise StoreError("生产环境未配置商店测试家庭")
    if not settings.apple_root_cert_paths or (environment == "Production" and not settings.apple_app_id):
        raise StoreError("Apple 验签配置不完整")
    return SignedDataVerifier([Path(p.strip()).read_bytes() for p in settings.apple_root_cert_paths.split(",")],
                              True, Environment(environment), settings.apple_bundle_id, settings.apple_app_id)


def _apple_status(reference: str, environment: str) -> VerifiedSubscription:
    from appstoreserverlibrary.api_client import AppStoreServerAPIClient, APIException
    from appstoreserverlibrary.models.Environment import Environment
    try:
        verifier = apple_verifier(environment)
        client = AppStoreServerAPIClient(Path(settings.apple_private_key_path).read_bytes(), settings.apple_key_id,
                                        settings.apple_issuer_id, settings.apple_bundle_id, Environment(environment))
        # Decode the queried transaction to bind the exact subscription chain.
        queried = verifier.verify_and_decode_signed_transaction(client.get_transaction_info(reference).signedTransactionInfo)
        candidates = []
        response = client.get_all_subscription_statuses(reference)
        for group in response.data or []:
            for item in group.lastTransactions or []:
                tx = verifier.verify_and_decode_signed_transaction(item.signedTransactionInfo)
                if tx.originalTransactionId == queried.originalTransactionId:
                    renewal = verifier.verify_and_decode_renewal_info(item.signedRenewalInfo)
                    candidates.append((tx, renewal, item.status))
        if not candidates:
            raise StoreError("Apple 订阅不存在")
        tx, renewal, status = max(candidates, key=lambda x: x[0].purchaseDate or 0)
        if tx.type != "Auto-Renewable Subscription" or not tx.expiresDate:
            raise StoreError("商品不是自动续订订阅")
        seats_for("appstore", tx.productId)
        state = {1: "active", 2: "expired", 4: "grace"}.get(int(status), "inactive")
        if tx.revocationDate:
            state = "revoked"
        end = renewal.gracePeriodExpiresDate if state == "grace" else tx.expiresDate
        if environment == "Sandbox":
            allow_test_purchase(str(tx.appAccountToken or ""))
        prefix = "sandbox:" if environment == "Sandbox" else ""
        return VerifiedSubscription("appstore", prefix + tx.originalTransactionId, prefix + tx.originalTransactionId,
            str(tx.appAccountToken or "").lower(), tx.productId,
            datetime.fromtimestamp(end / 1000, timezone.utc).replace(tzinfo=None), state,
            int(renewal.autoRenewStatus or 0) == 1, transaction_id=prefix + tx.transactionId,
            price_milliunits=tx.price, currency=tx.currency,
            first_paid_at=datetime.fromtimestamp(tx.originalPurchaseDate / 1000, timezone.utc) if getattr(tx, "originalPurchaseDate", None) else None,
            next_billing_at=datetime.fromtimestamp((getattr(renewal, "renewalDate", None) or tx.expiresDate) / 1000, timezone.utc)
                if state == "active" else None,
            period_started_at=datetime.fromtimestamp(tx.purchaseDate / 1000, timezone.utc) if tx.purchaseDate else None)
    except (StoreError, APIException):
        raise
    except Exception:
        raise StoreError("Apple 验单暂时失败，请稍后恢复购买") from None


def apple_status(reference: str) -> VerifiedSubscription:
    from appstoreserverlibrary.api_client import APIException
    explicit_sandbox = reference.startswith("sandbox:")
    if explicit_sandbox:
        reference = reference.removeprefix("sandbox:")
    environment = "Sandbox" if explicit_sandbox else settings.apple_environment
    try:
        return _apple_status(reference, environment)
    except APIException as error:
        if environment == "Production" and error.http_status_code == 404 and test_accounts():
            try:
                return _apple_status(reference, "Sandbox")
            except StoreError:
                raise
            except Exception:
                pass
        raise StoreError("Apple 验单暂时失败，请稍后恢复购买") from None


def apple_notification(payload: str):
    environments = [settings.apple_environment]
    if settings.apple_environment == "Production" and test_accounts():
        environments.append("Sandbox")
    for environment in environments:
        try:
            verifier = apple_verifier(environment)
            notification = verifier.verify_and_decode_notification(payload)
            if notification.notificationType == "TEST":
                return notification, None
            transaction = verifier.verify_and_decode_signed_transaction(notification.data.signedTransactionInfo)
            if environment == "Sandbox":
                allow_test_purchase(str(transaction.appAccountToken or ""))
            reference = ("sandbox:" if environment == "Sandbox" else "") + transaction.originalTransactionId
            return notification, reference
        except Exception:
            continue
    raise StoreError("Apple 通知验签或测试家庭授权失败")


def google_gateway() -> str:
    origin = settings.google_gateway_url.rstrip("/")
    if origin:
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or len(settings.google_gateway_token) < 32):
            raise StoreError("Google 验单中继配置无效")
    return origin


async def google_request(method: str, path: str, body=None):
    try:
        gateway = google_gateway()
        if gateway:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(gateway + "/google/request",
                    headers={"Authorization": "Bearer " + settings.google_gateway_token},
                    json={"method": method, "path": path, "body": body})
                response.raise_for_status()
                return response.json() if response.content else {}
        service = json.loads(Path(settings.google_service_account_path).read_text())
        now = int(time.time())
        assertion = jwt.encode({"iss": service["client_email"], "scope": "https://www.googleapis.com/auth/androidpublisher",
            "aud": "https://oauth2.googleapis.com/token", "iat": now, "exp": now + 3600}, service["private_key"], algorithm="RS256")
        async with httpx.AsyncClient(timeout=20) as client:
            token = await client.post("https://oauth2.googleapis.com/token", data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
            token.raise_for_status()
            response = await client.request(method, "https://androidpublisher.googleapis.com/androidpublisher/v3/" + path,
                headers={"Authorization": "Bearer " + token.json()["access_token"]}, json=body)
            response.raise_for_status()
            return response.json() if response.content else {}
    except Exception:
        raise StoreError("Google Play 验单暂时失败，请稍后恢复购买") from None


async def google_status(reference: str) -> VerifiedSubscription:
    package = quote(settings.google_package_name, safe="")
    data = await google_request("GET", f"applications/{package}/purchases/subscriptionsv2/tokens/{quote(reference, safe='')}")
    # Production deployments never accept test purchases.
    if "testPurchase" in data:
        allow_test_purchase(data.get("externalAccountIdentifiers", {}).get("obfuscatedExternalAccountId", ""))
    state = {"SUBSCRIPTION_STATE_ACTIVE": "active", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": "grace",
             "SUBSCRIPTION_STATE_CANCELED": "active", "SUBSCRIPTION_STATE_EXPIRED": "expired"}.get(data.get("subscriptionState"), "inactive")
    items = [i for i in data.get("lineItems", []) if i.get("expiryTime") and i.get("autoRenewingPlan") is not None]
    if len(items) != 1:
        raise StoreError("订阅必须只有一个自动续订商品")
    item = items[0]
    product = item["productId"]
    seats_for("googleplay", product)
    expiry = datetime.fromisoformat(item["expiryTime"].replace("Z", "+00:00"))
    return VerifiedSubscription("googleplay", hashlib.sha256(reference.encode()).hexdigest(), reference,
        data.get("externalAccountIdentifiers", {}).get("obfuscatedExternalAccountId", ""), product,
        naive(expiry), state, item.get("autoRenewingPlan", {}).get("autoRenewEnabled", False),
        hashlib.sha256(data["linkedPurchaseToken"].encode()).hexdigest() if data.get("linkedPurchaseToken") else None,
        state in ("active", "grace") and naive(expiry) > datetime.utcnow() and data.get("acknowledgementState") == "ACKNOWLEDGEMENT_STATE_PENDING",
        transaction_id=item.get("latestSuccessfulOrderId") or data.get("latestOrderId"),
        first_paid_at=datetime.fromisoformat(data["startTime"].replace("Z", "+00:00")) if data.get("startTime") else None,
        next_billing_at=naive(expiry) if state == "active" else None)


async def verify(channel: str, reference: str) -> VerifiedSubscription:
    if channel == "creem_test":
        from .creem_billing import verify_subscription
        return await asyncio.to_thread(verify_subscription, reference)
    if channel == "paddle_sandbox":
        from .paddle_billing import verify_subscription
        return await asyncio.to_thread(verify_subscription, reference)
    if channel == "appstore":
        return await asyncio.to_thread(apple_status, reference)
    return await google_status(reference)


def record(result: VerifiedSubscription, db: Session, family_id: int | None = None) -> StoreSubscription | None:
    owner = db.query(StoreAccount).filter_by(account_token=result.account_token).first()
    if owner is None:
        if family_id is not None:
            raise HTTPException(409, "此购买未绑定当前家庭，请使用原家庭账号恢复购买")
        return None
    if family_id is not None and owner.family_id != family_id:
        raise HTTPException(409, "此购买属于其他家庭")
    db.query(Family).filter_by(id=owner.family_id).with_for_update().one()
    row = db.query(StoreSubscription).filter_by(channel=result.channel, chain_key=result.chain).with_for_update().first()
    linked = db.query(StoreSubscription).filter_by(channel=result.channel, chain_key=result.linked_chain).with_for_update().first() if result.linked_chain else None
    successor = db.query(StoreSubscription).filter_by(channel=result.channel, linked_chain=result.chain).first()
    if any(r and r.family_id != owner.family_id for r in (row, linked, successor)):
        raise HTTPException(409, "订阅交易链已绑定其他家庭")
    if row is None:
        row = StoreSubscription(family_id=owner.family_id, channel=result.channel, chain_key=result.chain)
        if linked:
            row.trial_extension_seconds = min(int(linked.trial_extension_seconds or 0),
                max(0, int((entitlement_expiry(linked) - datetime.utcnow()).total_seconds())))
        db.add(row)
    elif result.state == "expired" and naive(result.expires) < naive(row.expires_at):
        # An early termination must not turn a refund/revocation into bonus access.
        result = replace(result, state="revoked", auto_renew=False)
    if row.state == "revoked" and result.state == "expired":
        result = replace(result, state="revoked", auto_renew=False)
    if row.expires_at and naive(result.expires) > naive(row.expires_at) and result.period_started_at:
        spent = max(0, int((naive(result.period_started_at) - naive(row.expires_at)).total_seconds()))
        row.trial_extension_seconds = max(0, int(row.trial_extension_seconds or 0) - spent)
    elif row.state == "expired" and naive(result.expires) > naive(row.expires_at):
        # Keep only unspent bonus time when a lapsed subscription is restarted.
        row.trial_extension_seconds = min(int(row.trial_extension_seconds or 0),
            max(0, int((entitlement_expiry(row) - datetime.utcnow()).total_seconds())))
    # Capture once from the authority's initial purchase time, never from restore time.
    # Missing authority timestamps can be filled by a subsequent reconciliation.
    if (result.state == "active" and naive(result.expires) > datetime.utcnow()
            and result.first_paid_at is not None and naive(result.first_paid_at) <= datetime.utcnow()
            and row.state != "replaced" and not successor):
        sub = db.query(Subscription).filter_by(family_id=owner.family_id).with_for_update().one()
        if sub.plan == "free_trial" and not sub.trial_extension_claimed:
            row.trial_extension_seconds = max(0, int((naive(sub.expires_at) - naive(result.first_paid_at)).total_seconds()))
            sub.trial_extension_claimed = True
    row.encrypted_token = cipher().encrypt(result.reference.encode()).decode()
    row.product_id = result.product
    row.seat_count = seats_for(result.channel, result.product)
    row.expires_at = result.expires
    row.state = "replaced" if row.state == "replaced" or successor else result.state
    row.linked_chain = result.linked_chain
    row.auto_renew = result.auto_renew and row.state not in ("replaced", "revoked", "expired")
    row.next_billing_at = result.next_billing_at if row.auto_renew else None
    row.checked_at = datetime.utcnow()
    if row.state == "expired" and entitlement_expiry(row) <= datetime.utcnow():
        row.trial_extension_seconds = 0
    if result.transaction_id:
        transaction = db.query(StoreTransaction).filter_by(channel=result.channel, transaction_id=result.transaction_id).first()
        if transaction and transaction.family_id != owner.family_id:
            raise HTTPException(409, "商店交易已属于其他家庭")
        if transaction is None:
            transaction = StoreTransaction(family_id=owner.family_id, channel=result.channel,
                transaction_id=result.transaction_id, chain_key=result.chain, product_id=result.product)
            db.add(transaction)
        transaction.expires_at = result.expires
        transaction.state = row.state
        transaction.price_milliunits = result.price_milliunits
        transaction.currency = result.currency
        db.flush()
        from .analytics import record as record_event
        environment = "test" if (result.channel in {"creem_test", "paddle_sandbox"} or
            (result.channel == "appstore" and (result.chain.startswith("sandbox:") or settings.apple_environment == "Sandbox")) or
            result.account_token.lower() in test_accounts()) else "production"
        if result.state == "active":
            record_event(db, "subscription_activated", owner.family_id, f"transaction:{transaction.id}:active",
                   provider=result.channel, seat_count=row.seat_count,
                   environment=environment)
        if result.state == "active" and (result.price_milliunits or 0) > 0:
            record_event(db, "payment_confirmed", owner.family_id, f"transaction:{transaction.id}:paid",
                   provider=result.channel, environment=environment)
        if result.state == "revoked":
            record_event(db, "entitlement_revoked", owner.family_id, f"transaction:{transaction.id}:revoked", provider=result.channel)
    if linked:
        linked.state = "replaced"
        linked.auto_renew = False
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "订阅并发更新，请恢复购买重试") from None
    return row


def effective(family_id: int, sub, db: Session):
    """Select one effective tier and its own period; never extend high seats with another source."""
    if sub.plan == "permanent":
        return sub
    rows = db.query(StoreSubscription).filter_by(family_id=family_id).all()
    candidates = [r for r in rows if active(r)]
    if naive(sub.expires_at) > datetime.utcnow():
        candidates.append(sub)
    if not candidates:
        return sub
    return max(candidates, key=lambda r: (r.seat_count, r is not sub or sub.plan != "free_trial", entitlement_expiry(r)))


def block_other_channel(family_id: int, channel: str, db: Session):
    from .subscription import ensure_subscription
    sub = ensure_subscription(family_id, db)
    if channel != "wechat" and sub.plan != "free_trial" and naive(sub.expires_at) > datetime.utcnow():
        raise HTTPException(409, "已有国内渠道订阅，请到期后切换渠道")
    for row in db.query(StoreSubscription).filter_by(family_id=family_id):
        if row.channel != channel and (active(row) or row.auto_renew):
            raise HTTPException(409, "已有其他商店订阅，请在原商店取消续订并到期后切换")


def enqueue(channel: str, key: str, reference: str, db: Session):
    event = db.get(StoreEvent, key)
    if event is None:
        db.add(StoreEvent(event_key=key, channel=channel,
            encrypted_reference=cipher().encrypt(reference.encode()).decode(), processed=False))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()


def verify_family(family_id: int, channel: str, reference: str):
    from ..db import SessionLocal
    from .subscription import get_status
    # Blocking SQL row locks stay off the ASGI event loop throughout authority queries.
    with SessionLocal() as db:
        db.query(Family).filter_by(id=family_id).with_for_update().one()
        result = asyncio.run(verify(channel, reference))
        record(result, db, family_id)
        acknowledge(result)
        return get_status(family_id, db)


def acknowledge(result: VerifiedSubscription):
    if not result.needs_acknowledgement:
        return
    package = quote(settings.google_package_name, safe="")
    asyncio.run(google_request("POST", f"applications/{package}/purchases/subscriptions/{quote(result.product, safe='')}/tokens/{quote(result.reference, safe='')}:acknowledge", {}))


def _process_event(key: str):
    from ..db import SessionLocal
    with SessionLocal() as db:
        event = db.get(StoreEvent, key)
        if event.processed:
            return
        reference = cipher().decrypt(event.encrypted_reference.encode()).decode()
        chain = hashlib.sha256(reference.encode()).hexdigest() if event.channel == "googleplay" else reference
        existing = db.query(StoreSubscription).filter_by(channel=event.channel, chain_key=chain).first()
        if existing:
            db.query(Family).filter_by(id=existing.family_id).with_for_update().one()
        result = asyncio.run(verify(event.channel, reference))
        if existing is None:
            owner = db.query(StoreAccount).filter_by(account_token=result.account_token).first()
            if owner is None:
                return
            db.query(Family).filter_by(id=owner.family_id).with_for_update().one()
            # Initial notification may race first purchase / immediate upgrade.
            result = asyncio.run(verify(event.channel, reference))
        if record(result, db) is not None:
            acknowledge(result)
            event.processed = True
            db.commit()


def process_event(key: str):
    from ..db import SessionLocal
    try:
        _process_event(key)
    finally:
        with SessionLocal() as db:
            event = db.get(StoreEvent, key)
            if event and not event.processed:
                event.attempts += 1
                event.next_attempt_at = datetime.utcnow() + timedelta(seconds=min(3600, 60 * 2 ** min(event.attempts, 6)))
                db.commit()


def refresh_subscription(row_id: int):
    from ..db import SessionLocal
    with SessionLocal() as db:
        row = db.get(StoreSubscription, row_id)
        db.query(Family).filter_by(id=row.family_id).with_for_update().one()
        result = asyncio.run(verify(row.channel, cipher().decrypt(row.encrypted_token.encode()).decode()))
        record(result, db, row.family_id)
        acknowledge(result)


async def reconcile_forever():
    from ..db import SessionLocal
    while True:
        try:
            with SessionLocal() as db:
                keys = [e.event_key for e in db.query(StoreEvent).filter(StoreEvent.processed.is_(False), StoreEvent.next_attempt_at <= datetime.utcnow()).order_by(StoreEvent.next_attempt_at).limit(100)]
                cutoff = datetime.utcnow().timestamp() - 3600
                ids = [r.id for r in db.query(StoreSubscription).filter(StoreSubscription.state != "replaced", or_(StoreSubscription.auto_renew.is_(True), StoreSubscription.state.in_(["active", "grace"]), and_(StoreSubscription.state == "expired", StoreSubscription.trial_extension_seconds > 0)), StoreSubscription.checked_at < datetime.fromtimestamp(cutoff, timezone.utc).replace(tzinfo=None)).order_by(StoreSubscription.checked_at).limit(100)]
            for key in keys:
                try:
                    await asyncio.to_thread(process_event, key)
                except Exception:
                    log.warning("Store notification reconciliation failed")
            for row_id in ids:
                try:
                    await asyncio.to_thread(refresh_subscription, row_id)
                except Exception:
                    log.warning("Store subscription reconciliation failed")
        except Exception:
            log.warning("Store reconciliation unavailable")
        await asyncio.sleep(60)
