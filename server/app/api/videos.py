"""Search public Bilibili school lessons and embed the official player."""
import html
import json
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Student
from ..services import content_policy, fence
from ..services.teacher_channels import current_channel
from .chat import _check_policy
from .deps import current_student

router = APIRouter(prefix="/chat/videos", tags=["videos"])
BVID = re.compile(r"BV[0-9A-Za-z]{10}\Z")
SCHOOL_CATEGORY = 208


async def provider(path: str, params: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://api.bilibili.com/x/web-interface/" + path,
                                        params=params, headers={"User-Agent": "Mozilla/5.0",
                                                                "Referer": "https://www.bilibili.com/"})
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, dict) or body.get("code") != 0 or not isinstance(body.get("data"), dict):
            raise ValueError("provider unavailable")
        return body["data"]
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, "视频平台暂不可用，请稍后重试") from None


def plain(value) -> str:
    return html.unescape(re.sub(r"<[^>]*>", "", str(value or "")))


def visible(item: dict, student: Student) -> bool:
    text = plain(item.get("title")) + " " + plain(item.get("description", item.get("desc")))
    # shortcut: metadata filtering cannot review video frames; use reviewed sources if required.
    try:
        blocked, _ = content_policy.inspect(text)
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "视频平台暂不可用，请稍后重试") from None
    return not blocked and not any(word and word.casefold() in text.casefold()
                                   for word in json.loads(student.forbidden_words_json))


def check_access(student, db, channel):
    _check_policy(student, db, channel=channel, check_message_quota=False)


@router.get("")
async def search(q: str = Query(min_length=1, max_length=100), page: int = Query(default=1, ge=1, le=50),
                 student: Student = Depends(current_student), db: Session = Depends(get_db),
                 channel: str = Depends(current_channel)):
    check_access(student, db, channel)
    q = q.strip()
    if not q:
        raise HTTPException(422, "请输入视频搜索关键词")
    verdict = await fence.evaluate(q, student.grade_band, student.family_id,
                                   forbidden_words=json.loads(student.forbidden_words_json),
                                   fence_level=student.fence_level)
    if verdict["decision"] != "allow":
        raise HTTPException(403, "请搜索学习相关的讲解视频")
    data = await provider("search/type", {"search_type": "video", "keyword": q,
                                           "tids": SCHOOL_CATEGORY, "page": page, "page_size": 20})
    results = data.get("result", [])
    try:
        pages = int(data.get("numPages", 1))
        if not isinstance(results, list):
            raise ValueError("invalid results")
    except (ValueError, TypeError):
        raise HTTPException(503, "视频平台暂不可用，请稍后重试") from None
    items = []
    for item in results:
        if not isinstance(item, dict) or not BVID.fullmatch(str(item.get("bvid", ""))):
            continue
        if str(item.get("typeid")) != str(SCHOOL_CATEGORY) or not visible(item, student):
            continue
        items.append(dict(id=item["bvid"], title=plain(item.get("title")),
                          author=plain(item.get("author")), duration=plain(item.get("duration"))))
    # Continue even when a whole page was filtered; do not misreport it as the last page.
    return dict(items=items, page=page, has_more=page < min(pages, 50))


@router.get("/{video_id}")
async def playback(video_id: str, student: Student = Depends(current_student), db: Session = Depends(get_db),
                   channel: str = Depends(current_channel)):
    check_access(student, db, channel)
    if not BVID.fullmatch(video_id):
        raise HTTPException(422, "无效的视频编号")
    item = await provider("view", {"bvid": video_id})
    if item.get("bvid") != video_id or item.get("tid") != SCHOOL_CATEGORY or not visible(item, student):
        raise HTTPException(404, "视频不可用")
    return dict(id=video_id, title=plain(item.get("title")),
                embed_url=f"https://player.bilibili.com/player.html?bvid={video_id}&page=1&autoplay=0&danmaku=0")
