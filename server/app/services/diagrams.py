"""Bounded drawing instructions; never execute model-provided code or expressions."""
import io
import math
from typing import Literal

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..config import settings


class Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["line", "arrow", "rect", "ellipse", "text", "polyline"]
    points: list[tuple[float, float]] = Field(min_length=1, max_length=300)
    label: str = Field(default="", max_length=100)
    color: Literal["black", "blue", "red", "green", "gray"] = "black"

    @field_validator("points")
    @classmethod
    def bounded(cls, points):
        if any(not math.isfinite(v) or not 0 <= v <= 1000 for point in points for v in point):
            raise ValueError("coordinates must be finite and in 0..1000")
        return points


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["none", "drawing", "illustration", "edit"]
    caption: str = Field(default="", max_length=1000)
    prompt: str = Field(default="", max_length=3000)
    shapes: list[Shape] = Field(default_factory=list, max_length=100)

    @model_validator(mode="before")
    @classmethod
    def drawing_shapes_only(cls, data):
        if isinstance(data, dict) and data.get("kind") in ("none", "illustration", "edit"):
            return {**data, "shapes": []}
        return data


def render(plan: Plan) -> bytes:
    if plan.kind != "drawing" or not plan.shapes:
        raise ValueError("drawing requires shapes")
    font = ImageFont.truetype(settings.image_font_path, 22) if settings.image_font_path else ImageFont.load_default(size=22)
    if not settings.image_font_path and any(any(ord(c) > 255 for c in s.label) for s in plan.shapes):
        raise ValueError("IMAGE_FONT_PATH is required for Chinese diagram labels")
    image = Image.new("RGB", (1100, 1100), "white")
    draw = ImageDraw.Draw(image)
    for shape in plan.shapes:
        points = [(x + 50, y + 50) for x, y in shape.points]
        if shape.kind == "text":
            draw.text(points[0], shape.label, font=font, fill=shape.color)
        elif shape.kind in ("rect", "ellipse"):
            if len(points) != 2:
                raise ValueError("bounding box requires two points")
            (x1, y1), (x2, y2) = points
            if x2 <= x1 or y2 <= y1:
                raise ValueError("invalid bounding box")
            getattr(draw, "rectangle" if shape.kind == "rect" else "ellipse")(points, outline=shape.color, width=3)
        else:
            if len(points) < 2:
                raise ValueError("line requires at least two points")
            draw.line(points, fill=shape.color, width=3)
            if shape.kind == "arrow":
                x, y = points[-1]
                angle = math.atan2(y - points[-2][1], x - points[-2][0])
                draw.line([(x - 15 * math.cos(angle - .5), y - 15 * math.sin(angle - .5)),
                           (x, y), (x - 15 * math.cos(angle + .5), y - 15 * math.sin(angle + .5))],
                          fill=shape.color, width=3)
    output = io.BytesIO()
    image.save(output, "JPEG", quality=92)
    return output.getvalue()
