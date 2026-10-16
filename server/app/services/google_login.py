"""Verify Google ID tokens using a fixed issuer, audience and Google signing keys."""
import jwt
from fastapi import HTTPException
from ..config import settings
from .store_billing import google_gateway


def verify_google_identity(token: str) -> dict:
    if not settings.google_login_client_id:
        raise HTTPException(503, "Google 登录尚未配置")
    try:
        gateway = google_gateway()
        keys = jwt.PyJWKClient(
            gateway + "/google/certs" if gateway else "https://www.googleapis.com/oauth2/v3/certs",
            headers={"Authorization": "Bearer " + settings.google_gateway_token} if gateway else {}, timeout=10)
        key = keys.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=settings.google_login_client_id,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "email", "email_verified"]})
        if (claims["iss"] not in ("https://accounts.google.com", "accounts.google.com")
                or claims["email_verified"] is not True
                or not isinstance(claims["sub"], str) or not 1 <= len(claims["sub"]) <= 255):
            raise ValueError()
        return claims
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(503, "Google 登录服务暂时不可用，请稍后重试") from None
    except Exception:
        raise HTTPException(401, "Google 登录凭证无效或已过期") from None
