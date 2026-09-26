"""CMS 独立服务：只负责托管管理后台单页，API 调用指向后端 server。

与 server 完全解耦——本服务启动/关闭/升级不影响 API；反之亦然。
页面通过服务端注入的 CMS_API_BASE 环境变量（默认 http://localhost:8100）
或同源兜底确定后端地址。

启动：CMS_API_BASE=http://localhost:8100 uvicorn cms.main:app --port 8101
"""
import os
import json

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

API_BASE_FALLBACK = os.environ.get("CMS_API_BASE", "http://localhost:8100")

app = FastAPI(title="ai-zhuxue CMS", version="0.1.0", docs_url=None, redoc_url=None)

_INDEX_PATH = os.path.join(os.path.dirname(__file__), "index.html")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def cms_index():
    """CMS 单页；把后端基址注入 window.CMS_API_BASE。"""
    with open(_INDEX_PATH, encoding="utf-8") as f:
        html = f.read()
    safe_base = json.dumps(API_BASE_FALLBACK).replace("<", "\\u003c")
    inject = f"<script>window.CMS_API_BASE={safe_base};</script>"
    return HTMLResponse(html.replace("<head>", "<head>" + inject, 1))


@app.get("/health")
def health():
    return {"status": "ok", "service": "cms", "api_base": API_BASE_FALLBACK}
