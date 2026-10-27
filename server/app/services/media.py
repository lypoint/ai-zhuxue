"""Private Kodo images. Only sanitized, reviewed objects are readable by clients."""
import asyncio
import datetime as dt
import hashlib
import hmac
import re
import io
import json
import uuid
import warnings
from urllib.parse import quote, urlencode, urlsplit

import httpx
from fastapi import HTTPException
from PIL import Image, ImageOps
from qiniu import Auth, BucketManager, QiniuMacAuth, put_data

from ..config import settings
from ..models import MediaAsset


def require_storage():
    if not all((settings.qiniu_access_key, settings.qiniu_secret_key,
                settings.qiniu_bucket, settings.qiniu_domain)):
        raise HTTPException(503, "七牛私有图片存储尚未配置")
    if urlsplit(settings.qiniu_domain).scheme != "https":
        raise HTTPException(503, "七牛下载域名必须使用 HTTPS")


def auth():
    require_storage()
    return Auth(settings.qiniu_access_key, settings.qiniu_secret_key)


def download_url(key: str, expires: int = 300):
    require_storage()
    host = urlsplit(settings.qiniu_domain).hostname or ""
    match = re.fullmatch(r"([a-z0-9-]+)\.s3\.([a-z0-9-]+)\.qiniucs\.com", host)
    if match:
        if match[1] != settings.qiniu_bucket:
            raise HTTPException(503, "七牛 S3 下载域名与空间不匹配")
        return _s3_download_url(host, match[2], key, expires)
    return auth().private_download_url(
        settings.qiniu_domain.rstrip("/") + "/" + quote(key, safe="/"), expires=expires)


def _s3_download_url(host: str, region: str, key: str, expires: int) -> str:
    # Qiniu's official S3 HTTPS endpoint uses AWS Signature V4, not Kodo's e/token.
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    day = stamp[:8]
    scope = f"{day}/{region}/s3/aws4_request"
    params = {"X-Amz-Algorithm": "AWS4-HMAC-SHA256",
              "X-Amz-Credential": settings.qiniu_access_key + "/" + scope,
              "X-Amz-Date": stamp, "X-Amz-Expires": str(expires), "X-Amz-SignedHeaders": "host"}
    query = urlencode(sorted(params.items()), quote_via=quote, safe="~")
    path = "/" + quote(key, safe="/~")
    canonical = f"GET\n{path}\n{query}\nhost:{host}\n\nhost\nUNSIGNED-PAYLOAD"
    to_sign = f"AWS4-HMAC-SHA256\n{stamp}\n{scope}\n" + hashlib.sha256(canonical.encode()).hexdigest()
    signing_key = ("AWS4" + settings.qiniu_secret_key).encode()
    for value in (day, region, "s3", "aws4_request"):
        signing_key = hmac.new(signing_key, value.encode(), hashlib.sha256).digest()
    signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()
    return f"https://{host}{path}?{query}&X-Amz-Signature={signature}"


def upload_token(key: str):
    return auth().upload_token(settings.qiniu_bucket, key, 600, policy={
        "insertOnly": 1, "fsizeLimit": settings.image_max_bytes,
        "mimeLimit": "image/jpeg;image/png;image/webp", "detectMime": 1})


async def fetch_image(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            if int(response.headers.get("content-length", "0")) > settings.image_max_bytes:
                raise HTTPException(422, "图片超过大小限制")
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > settings.image_max_bytes:
                    raise HTTPException(422, "图片超过大小限制")
    return bytes(data)


def sanitize(data: bytes) -> tuple[bytes, int, int]:
    if len(data) > settings.image_max_bytes:
        raise HTTPException(422, "图片超过大小限制")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in ("JPEG", "PNG", "WEBP"):
                    raise ValueError("format")
                width, height = source.size
                if min(width, height) < 1 or width * height > settings.image_max_pixels:
                    raise ValueError("pixels")
                image = ImageOps.exif_transpose(source).convert("RGB")
                # Re-encode pixels only: no EXIF, GPS or animation survives.
                clean = Image.new("RGB", image.size, "white")
                clean.paste(image)
                output = io.BytesIO()
                clean.save(output, format="JPEG", quality=92)
                if output.tell() > settings.image_max_bytes:
                    raise ValueError("size")
                return output.getvalue(), clean.width, clean.height
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, "请选择大小合适的 JPEG、PNG 或 WebP 图片")


async def store(key: str, data: bytes):
    token = upload_token(key)
    _, info = await asyncio.to_thread(put_data, token, key, data, mime_type="image/jpeg")
    if info.status_code not in (200, 614):  # Retrying a completed immutable write is safe.
        raise HTTPException(503, "图片保存失败，请稍后重试")


async def remove(key: str):
    _, info = await asyncio.to_thread(BucketManager(auth()).delete, settings.qiniu_bucket, key)
    if info.status_code not in (200, 612):
        raise HTTPException(503, "图片删除失败，后台稍后重试")


async def moderate(key: str) -> bool:
    url = settings.qiniu_censor_url
    body = json.dumps({"data": {"uri": download_url(key)},
                       "params": {"scenes": ["pulp", "terror", "politician"]}}, separators=(",", ":"))
    require_storage()
    authorization = "Qiniu " + QiniuMacAuth(
        settings.qiniu_access_key, settings.qiniu_secret_key).token_of_request(
            "POST", None, url, None, "application/json", body)
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, content=body, headers={
            "Authorization": authorization, "Content-Type": "application/json"})
        response.raise_for_status()
        result = response.json()
    if result.get("code") != 200 or "suggestion" not in result.get("result", {}):
        raise HTTPException(503, "图片审核暂不可用，请稍后重试")
    return result["result"]["suggestion"] == "pass"


async def save_reviewed(db, student_id: int, data: bytes, message_id: int | None = None, *, publish: bool = True):
    clean, width, height = await asyncio.to_thread(sanitize, data)
    asset_id = uuid.uuid4().hex
    asset = MediaAsset(id=asset_id, student_id=student_id, message_id=message_id,
                       object_key=f"private/{student_id}/{asset_id}.jpg", status="checking",
                       mime_type="image/jpeg", byte_size=len(clean), width=width, height=height)
    db.add(asset)
    db.commit()  # Keep a deletion record even if storage or moderation fails.
    await store(asset.object_key, clean)
    approved = await moderate(asset.object_key)
    asset.status = ("ready" if publish else "checking") if approved else "blocked"
    db.commit()
    if not approved:
        raise HTTPException(422, "图片未通过审核，请更换图片")
    return asset


def block(asset: MediaAsset, caption: str = "") -> dict:
    return {"type": "image", "asset_id": asset.id, "caption": caption,
            "width": asset.width, "height": asset.height}


def detach_student(db, student_id: int):
    from ..models import ImageJob
    db.query(ImageJob).filter_by(student_id=student_id).delete(synchronize_session=False)
    db.query(MediaAsset).filter_by(student_id=student_id).update({
        MediaAsset.status: "deleting", MediaAsset.message_id: None, MediaAsset.student_id: None},
        synchronize_session=False)
