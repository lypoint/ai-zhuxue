"""Reusable vision/generation configuration, following the CMS fence pattern."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .admin import AdminPrincipal, _base_url, log, require_admin, require_manage, require_operate
from ..db import get_db
from ..models import ImageModelConfig, LLMGroup
from ..services import image_models
from ..services.keyvault import encrypt_api_key

router = APIRouter(prefix="/admin", tags=["image models"])


class ImageConfigIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["vision", "generation"]
    protocol: Literal["openai", "dashscope", "dashscope-wan"] = "openai"
    base_url: str = Field(min_length=1, max_length=500)
    model_id: str = Field(min_length=1, max_length=120)
    api_key: str = Field(default="", max_length=200)
    supports_edit: bool = False
    price_in: float = Field(default=0, ge=0, allow_inf_nan=False)
    price_out: float = Field(default=0, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def protocol_matches(self):
        if self.kind == "vision" and self.protocol != "openai":
            raise ValueError("读图使用 OpenAI 兼容协议")
        if self.supports_edit and (self.kind != "generation" or self.protocol != "dashscope"):
            raise ValueError("参考图编辑使用 DashScope 协议")
        return self


def public(config: ImageModelConfig):
    return {**{key: getattr(config, key) for key in (
        "id", "name", "kind", "protocol", "base_url", "model_id", "enabled",
        "supports_edit", "revision", "tested_revision", "price_in", "price_out")},
            "has_key": bool(config.api_key)}


@router.get("/image-models")
def list_configs(principal: AdminPrincipal = Depends(require_admin), db: Session = Depends(get_db)):
    require_operate(principal)
    return [public(config) for config in db.query(ImageModelConfig).order_by(ImageModelConfig.id).all()]


@router.post("/image-models")
def create(body: ImageConfigIn, principal: AdminPrincipal = Depends(require_admin), db: Session = Depends(get_db)):
    require_manage(principal)
    if not body.api_key.strip() or not body.name.strip() or not body.model_id.strip():
        raise HTTPException(422, "名称、模型和密钥不能为空")
    values = body.model_dump()
    values.update(name=body.name.strip(), model_id=body.model_id.strip(), base_url=_base_url(body.base_url),
                  api_key=encrypt_api_key(body.api_key.strip()))
    config = ImageModelConfig(**values)
    db.add(config)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "图片配置名称已存在")
    log(db, principal, "image_config.create", f"id={config.id}")
    return public(config)


@router.put("/image-models/{config_id}")
def update(config_id: int, body: ImageConfigIn, principal: AdminPrincipal = Depends(require_admin),
           db: Session = Depends(get_db)):
    require_manage(principal)
    config = db.get(ImageModelConfig, config_id)
    if not config:
        raise HTTPException(404, "图片配置不存在")
    if config.kind != body.kind:
        raise HTTPException(422, "配置类型不能修改，请新建配置")
    if not body.name.strip() or not body.model_id.strip():
        raise HTTPException(422, "名称和模型不能为空")
    values = body.model_dump(exclude={"api_key"})
    values.update(base_url=_base_url(body.base_url), name=body.name.strip(), model_id=body.model_id.strip())
    if body.api_key.strip():
        values["api_key"] = encrypt_api_key(body.api_key.strip())
    for key, value in values.items():
        setattr(config, key, value)
    config.revision += 1
    config.enabled = False
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "图片配置名称已存在")
    log(db, principal, "image_config.update", f"id={config.id} revision={config.revision}; retest required")
    return public(config)


@router.post("/image-models/{config_id}/test")
async def test(config_id: int, principal: AdminPrincipal = Depends(require_admin), db: Session = Depends(get_db)):
    require_manage(principal)
    config = db.get(ImageModelConfig, config_id)
    if not config:
        raise HTTPException(404, "图片配置不存在")
    revision = config.revision
    try:
        snapshot = image_models.config_snapshot(config)
        if config.kind == "vision":
            import json
            result = await image_models.complete(snapshot, '读取图片的大色块颜色，仅返回 JSON，color 为英文颜色名。',
                                                 [image_models.test_image()], json_output=True)
            if json.loads(result["content"]).get("color") != "red":
                raise ValueError("vision probe")
        else:
            url = await image_models.generate(snapshot, "A red circle on white background, no text",
                [image_models.test_image()] if config.supports_edit else [])
            image_models.media.sanitize(await image_models.fetch_generated(url))
    except Exception:
        db.refresh(config)
        if config.revision == revision:
            config.enabled, config.tested_revision = False, None
        log(db, principal, "image_config.test_failed", f"id={config_id} revision={revision}")
        raise HTTPException(503, "模型测试失败，请检查协议、模型权限和参数；生图测试可能产生费用")
    db.refresh(config)
    if config.revision != revision:
        raise HTTPException(409, "测试期间配置已修改，请重新测试")
    config.tested_revision = revision
    log(db, principal, "image_config.test_passed", f"id={config_id} revision={revision}")
    return public(config)


class EnabledIn(BaseModel):
    enabled: bool


@router.put("/image-models/{config_id}/enabled")
def enable(config_id: int, body: EnabledIn, principal: AdminPrincipal = Depends(require_admin), db: Session = Depends(get_db)):
    require_manage(principal)
    config = db.get(ImageModelConfig, config_id)
    if not config:
        raise HTTPException(404, "图片配置不存在")
    if body.enabled and config.tested_revision != config.revision:
        raise HTTPException(409, "请先测试当前版本")
    config.enabled = body.enabled
    log(db, principal, "image_config.enable", f"id={config_id} enabled={body.enabled}")
    return public(config)


@router.delete("/image-models/{config_id}")
def delete(config_id: int, principal: AdminPrincipal = Depends(require_admin), db: Session = Depends(get_db)):
    require_manage(principal)
    config = db.get(ImageModelConfig, config_id)
    if not config:
        raise HTTPException(404, "图片配置不存在")
    if db.query(LLMGroup.id).filter((LLMGroup.vision_config_id == config_id) |
                                   (LLMGroup.image_config_id == config_id)).first():
        raise HTTPException(409, "配置仍被老师使用")
    db.delete(config)
    log(db, principal, "image_config.delete", f"id={config_id}")
    return {"ok": True}


@router.post("/llm-groups/{group_id}/test-vision")
async def test_native(group_id: int, principal: AdminPrincipal = Depends(require_admin), db: Session = Depends(get_db)):
    require_manage(principal)
    group = db.get(LLMGroup, group_id)
    if not group:
        raise HTTPException(404, "老师不存在")
    snapshot = image_models.native_snapshot(group_id)
    try:
        import json
        result = await image_models.complete(snapshot, '读取图片的大色块颜色，仅返回 JSON，color 为英文颜色名。',
                                             [image_models.test_image()], json_output=True)
        if json.loads(result["content"]).get("color") != "red":
            raise ValueError("vision probe")
    except Exception:
        db.refresh(group)
        group.vision_test_signature = ""
        log(db, principal, "teacher.vision_test_failed", f"id={group_id}")
        raise HTTPException(503, "主模型读图测试失败")
    db.refresh(group)
    if image_models.signature(image_models.native_snapshot(group_id)) != image_models.signature(snapshot):
        raise HTTPException(409, "测试期间主模型配置已修改，请重新测试")
    group.vision_test_signature = image_models.signature(snapshot)
    log(db, principal, "teacher.vision_test", f"id={group_id}")
    return {"ok": True}


class TeacherImagesIn(BaseModel):
    image_input_mode: Literal["off", "native", "assisted"] = "off"
    vision_config_id: int | None = None
    image_config_id: int | None = None
    diagram_enabled: bool = False
    auto_diagram: bool = False
    image_daily_cap: int = Field(default=10, ge=0, le=1000)


@router.put("/llm-groups/{group_id}/images")
def teacher_images(group_id: int, body: TeacherImagesIn, principal: AdminPrincipal = Depends(require_admin),
                   db: Session = Depends(get_db)):
    require_manage(principal)
    group = db.get(LLMGroup, group_id)
    if not group:
        raise HTTPException(404, "老师不存在")
    for field, value in body.model_dump().items():
        setattr(group, field, value)
    from ..services.image_chat import validate_teacher
    validate_teacher(db, group)
    log(db, principal, "teacher.images_update", f"id={group_id} settings={body.model_dump_json()}")
    return {"ok": True}
