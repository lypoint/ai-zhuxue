import asyncio
import base64
import hashlib
import json
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .deps import current_guardian
from ..config import settings
from ..db import get_db
from ..models import Guardian, StoreSubscription, SubscriptionOrder
from ..services import store_billing as billing
from ..services.subscription import get_status

router = APIRouter(tags=["store-billing"])
Channel = Literal["appstore", "googleplay"]


class PurchaseInput(BaseModel):
    channel: Channel
    product_code: str = Field(pattern=r"^family_monthly_[1-9][0-9]{0,3}$")


class VerifyInput(BaseModel):
    channel: Channel
    reference: str = Field(min_length=1, max_length=8192)


@router.get("/parent/billing/account")
def billing_account(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    return {"account_token": billing.account(guardian.family_id, db).account_token}


@router.post("/parent/billing/purchase")
def purchase(body: PurchaseInput, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    try:
        billing.configured(body.channel)
        product = billing.products(body.channel).get(body.product_code)
        if product is None:
            raise HTTPException(422, "该档位尚未在商店配置")
        token = billing.account(guardian.family_id, db).account_token
        billing.block_other_channel(guardian.family_id, body.channel, db)
        if db.query(SubscriptionOrder.id).filter_by(family_id=guardian.family_id, status="pending").filter(SubscriptionOrder.provider.in_(["wechat", "demo"])).first():
            raise HTTPException(409, "请先处理国内渠道待支付订单")
        status = get_status(guardian.family_id, db)
        seats = int(body.product_code.removeprefix("family_monthly_"))
        if status["active"] and status["plan"] != "free_trial" and seats <= status["seat_count"]:
            raise HTTPException(409, "有效订阅只能升级至更多名额；续订由商店自动处理")
        channel_rows = db.query(StoreSubscription).filter_by(family_id=guardian.family_id, channel=body.channel).all()
        if any(row.auto_renew and not billing.active(row) for row in channel_rows):
            raise HTTPException(409, "原订阅暂未生效，请先在商店修复付款或取消订阅")
        active_rows = [row for row in channel_rows if billing.active(row)]
        if active_rows and seats <= max(row.seat_count for row in active_rows):
            raise HTTPException(409, "当前商店订阅已包含该名额，只能升级更高档位")
        if len(active_rows) > 1:
            raise HTTPException(409, "存在多个有效订阅，请先在商店处理重复订阅")
        old_reference = billing.cipher().decrypt(active_rows[0].encrypted_token.encode()).decode() if active_rows and body.channel == "googleplay" else None
        return {"product_id": product, "account_token": token, "old_reference": old_reference}
    except billing.StoreError as error:
        raise HTTPException(503, str(error)) from None


@router.post("/parent/billing/verify")
async def verify(body: VerifyInput, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    try:
        if body.channel == "appstore" and (not body.reference.isascii() or not body.reference.isdigit() or len(body.reference) > 64):
            raise HTTPException(422, "Apple 交易号无效")
        return await asyncio.to_thread(billing.verify_family, guardian.family_id, body.channel, body.reference)
    except billing.StoreError as error:
        raise HTTPException(503, str(error)) from None


@router.post("/payments/appstore/notify")
async def apple_notify(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if len(raw) > 65536:
        raise HTTPException(413, "通知过大")
    try:
        notification, reference = await asyncio.to_thread(billing.apple_notification, json.loads(raw)["signedPayload"])
        if reference is None:
            return {"ok": True}
        key = "apple:" + notification.notificationUUID
        billing.enqueue("appstore", key, reference, db)
        await asyncio.to_thread(billing.process_event, key)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(503, "通知未处理，请重试") from None
    return {"ok": True}


def google_identity(header: str):
    if not settings.google_pubsub_audience or not settings.google_pubsub_email or not header.startswith("Bearer "):
        raise HTTPException(401, "Pub/Sub 身份验证失败")
    try:
        token = header[7:]
        gateway = billing.google_gateway()
        key = jwt.PyJWKClient(gateway + "/google/certs" if gateway else "https://www.googleapis.com/oauth2/v3/certs",
            headers={"Authorization": "Bearer " + settings.google_gateway_token} if gateway else {},
            timeout=10).get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=settings.google_pubsub_audience,
                            options={"require": ["exp", "iat", "iss", "aud", "email", "email_verified"]})
        if claims["iss"] not in ("https://accounts.google.com", "accounts.google.com") or claims["email"] != settings.google_pubsub_email or claims["email_verified"] is not True:
            raise ValueError()
    except Exception:
        raise HTTPException(401, "Pub/Sub 身份验证失败") from None


@router.post("/payments/googleplay/notify")
async def google_notify(request: Request, db: Session = Depends(get_db)):
    await asyncio.to_thread(google_identity, request.headers.get("authorization", ""))
    raw = await request.body()
    if len(raw) > 65536:
        raise HTTPException(413, "通知过大")
    try:
        message = json.loads(raw)["message"]
        data = json.loads(base64.b64decode(message["data"], validate=True))
        if data.get("packageName") != settings.google_package_name:
            raise ValueError()
        if "testNotification" in data:
            return {"ok": True}
        reference = data.get("subscriptionNotification", data.get("voidedPurchaseNotification", {}))["purchaseToken"]
        key = "google:" + hashlib.sha256(message["messageId"].encode()).hexdigest()
        billing.enqueue("googleplay", key, reference, db)
        await asyncio.to_thread(billing.process_event, key)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(503, "通知未处理，请重试") from None
    return {"ok": True}
