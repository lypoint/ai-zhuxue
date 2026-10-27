"""Mandatory content rules; operator additions never remove the built-in safety floor."""
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from ..config import settings

BASE_VERSION = "20261027-1"
CATEGORIES = {"nsfw", "violence", "hate", "csam", "deepfake", "copyright", "terrorism", "weapons"}
BASE_TERMS = {
    "nsfw": ["pornography", "色情", "一键脱衣", "nudify"],
    "violence": ["血腥虐杀", "dismember a person"],
    "hate": ["种族灭绝", "racial extermination"],
    "csam": ["child sexual abuse", "child pornography", "儿童色情", "未成年人色情"],
    "deepfake": ["换脸", "face swap", "deepfake", "伪造真人", "真人亲密合成"],
    "copyright": ["盗版水印", "去除版权水印", "remove copyright watermark"],
    "terrorism": ["恐怖袭击计划", "plan a terrorist attack"],
    "weapons": ["大规模杀伤性武器", "manufacture chemical weapons", "bioweapon instructions"],
}


def current():
    if not settings.content_safety_rules_path:
        return {"revision": "builtin", "updated_at": "2026-10-27", "blocked_terms": {}}
    data = json.loads(Path(settings.content_safety_rules_path).read_text())
    validate(data["blocked_terms"])
    if not isinstance(data.get("revision"), str) or not data["revision"]:
        raise ValueError("Missing policy revision")
    return data


def validate(terms):
    if not isinstance(terms, dict) or set(terms) - CATEGORIES:
        raise ValueError("Unknown content category")
    if sum(len(values) for values in terms.values() if isinstance(values, list)) > 500:
        raise ValueError("At most 500 additional terms")
    for values in terms.values():
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() or len(v) > 100 for v in values):
            raise ValueError("Use nonempty terms of at most 100 characters")


def update(revision, terms):
    validate(terms)
    if not settings.content_safety_rules_path:
        raise RuntimeError("Configure CONTENT_SAFETY_RULES_PATH before editing")
    path = Path(settings.content_safety_rules_path)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if current()["revision"] != revision:
            raise FileExistsError("Policy changed; reload before saving")
        data = {"revision": uuid.uuid4().hex, "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "blocked_terms": {k: list(dict.fromkeys(v.strip() for v in values)) for k, values in terms.items()}}
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False)
        try:
            os.chmod(temporary, 0o640)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return data


def inspect(content):
    data = current()
    version = BASE_VERSION + ":" + data["revision"]
    for category in sorted(CATEGORIES):
        for term in BASE_TERMS[category] + data["blocked_terms"].get(category, []):
            matched = re.search(r"\b" + re.escape(term) + r"\b", content, re.I) if term.isascii() else term.casefold() in content.casefold()
            if matched:
                return category, version
    return None, version
