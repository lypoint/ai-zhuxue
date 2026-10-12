"""WeChat Pay API v3 APP gateway; entitlement changes belong to order service."""
import base64
import binascii
import json
import secrets
import time
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

import httpx
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import Settings


class PaymentError(Exception):
    """Safe message for API clients; never includes provider bodies or secrets."""


class WeChatPay:
    base_url = "https://api.mch.weixin.qq.com"

    def __init__(self, config: Settings):
        self.config = config
        identifiers = (config.wechat_app_id, config.wechat_mch_id,
                       config.wechat_merchant_serial, config.wechat_platform_serial,
                       config.wechat_api_v3_key)
        callback = urlparse(config.wechat_notify_url)
        if (config.payment_mode != "wechat" or
                any(not value or "demo" in value.lower() for value in identifiers) or
                len(config.wechat_api_v3_key.encode()) != 32 or
                callback.scheme != "https" or not callback.hostname or
                callback.hostname.endswith("example.com") or callback.fragment or
                callback.username or callback.password):
            raise PaymentError("微信支付配置尚未完成")
        try:
            self.private_key = serialization.load_pem_private_key(
                Path(config.wechat_private_key_path).read_bytes(), password=None)
            self.platform_key = serialization.load_pem_public_key(
                Path(config.wechat_platform_public_key_path).read_bytes())
        except (OSError, ValueError, TypeError):
            raise PaymentError("微信支付密钥配置无效") from None
        if (not isinstance(self.private_key, rsa.RSAPrivateKey) or
                not isinstance(self.platform_key, rsa.RSAPublicKey) or
                self.private_key.key_size < 2048 or self.platform_key.key_size < 2048):
            raise PaymentError("微信支付必须配置 RSA 2048 位或更高的密钥")

    def sign(self, message: bytes) -> str:
        return base64.b64encode(self.private_key.sign(
            message, padding.PKCS1v15(), hashes.SHA256())).decode()

    def authorization(self, method: str, path: str, body: bytes) -> str:
        timestamp, nonce = str(int(time.time())), secrets.token_hex(16)
        signature = self.sign(
            f"{method}\n{path}\n{timestamp}\n{nonce}\n".encode() + body + b"\n")
        return ('WECHATPAY2-SHA256-RSA2048 '
                f'mchid="{self.config.wechat_mch_id}",nonce_str="{nonce}",'
                f'timestamp="{timestamp}",serial_no="{self.config.wechat_merchant_serial}",'
                f'signature="{signature}"')

    def verify(self, headers, body: bytes):
        """Verify exact wire bytes before parsing response/notification JSON."""
        headers = {key.lower(): value for key, value in headers.items()}
        try:
            timestamp = headers["wechatpay-timestamp"]
            nonce = headers["wechatpay-nonce"]
            if (abs(time.time() - int(timestamp)) > 300 or not nonce or
                    headers["wechatpay-serial"] != self.config.wechat_platform_serial):
                raise ValueError
            signature = base64.b64decode(headers["wechatpay-signature"], validate=True)
            self.platform_key.verify(signature,
                                     f"{timestamp}\n{nonce}\n".encode() + body + b"\n",
                                     padding.PKCS1v15(), hashes.SHA256())
        except (KeyError, ValueError, TypeError, InvalidSignature, binascii.Error):
            raise PaymentError("微信支付签名校验失败") from None

    async def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode() if payload else b""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.request(method, self.base_url + path, content=body,
                                                headers={"Authorization": self.authorization(method, path, body),
                                                         "Accept": "application/json",
                                                         "Wechatpay-Serial": self.config.wechat_platform_serial,
                                                         "Content-Type": "application/json"})
        except httpx.HTTPError:
            raise PaymentError("微信支付连接失败，请稍后重试") from None
        self.verify(response.headers, response.content)
        if response.status_code >= 400:
            raise PaymentError("微信支付请求未成功，请稍后重试")
        if response.status_code == 204:
            return {}
        try:
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError
            return result
        except ValueError:
            raise PaymentError("微信支付响应无效") from None

    async def prepay(self, order_number: str, amount_cents: int, description: str) -> dict:
        if not 0 < amount_cents < 100_000_000:
            raise PaymentError("支付金额无效")
        result = await self.request("POST", "/v3/pay/transactions/app", {
            "appid": self.config.wechat_app_id, "mchid": self.config.wechat_mch_id,
            "description": description, "out_trade_no": order_number,
            "notify_url": self.config.wechat_notify_url,
            "amount": {"total": amount_cents, "currency": "CNY"},
        })
        prepay_id = result.get("prepay_id")
        if not isinstance(prepay_id, str) or not prepay_id:
            raise PaymentError("微信支付预支付订单无效")
        timestamp, nonce = str(int(time.time())), secrets.token_hex(16)
        signature = self.sign(
            f"{self.config.wechat_app_id}\n{timestamp}\n{nonce}\n{prepay_id}\n".encode())
        return {"appId": self.config.wechat_app_id, "partnerId": self.config.wechat_mch_id,
                "prepayId": prepay_id, "packageValue": "Sign=WXPay",
                "nonceStr": nonce, "timeStamp": timestamp, "sign": signature}

    async def query(self, order_number: str) -> dict:
        path = (f"/v3/pay/transactions/out-trade-no/{quote(order_number, safe='')}?" +
                urlencode({"mchid": self.config.wechat_mch_id}))
        return await self.request("GET", path)

    def notification(self, headers, body: bytes) -> dict:
        self.verify(headers, body)
        try:
            envelope = json.loads(body)
            resource = envelope["resource"]
            if (envelope["event_type"] != "TRANSACTION.SUCCESS" or
                    resource["algorithm"] != "AEAD_AES_256_GCM" or
                    resource["original_type"] != "transaction"):
                raise ValueError
            plaintext = AESGCM(self.config.wechat_api_v3_key.encode()).decrypt(
                resource["nonce"].encode(),
                base64.b64decode(resource["ciphertext"], validate=True),
                resource.get("associated_data", "").encode())
            transaction = json.loads(plaintext)
            if not isinstance(transaction, dict):
                raise ValueError
            return transaction
        except (KeyError, ValueError, TypeError, AttributeError, InvalidTag, binascii.Error):
            raise PaymentError("微信支付通知无效") from None

    def validate_success(self, transaction: dict, order_number: str, amount_cents: int):
        amount = transaction.get("amount") or {}
        if (transaction.get("appid") != self.config.wechat_app_id or
                transaction.get("mchid") != self.config.wechat_mch_id or
                transaction.get("out_trade_no") != order_number or
                transaction.get("trade_state") != "SUCCESS" or
                transaction.get("trade_type") != "APP" or
                not isinstance(transaction.get("transaction_id"), str) or
                not transaction["transaction_id"] or
                not isinstance(amount, dict) or
                type(amount.get("total")) is not int or amount["total"] != amount_cents or
                amount.get("currency") != "CNY"):
            raise PaymentError("微信支付订单核对失败")
