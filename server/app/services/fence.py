"""学习话题围栏：红线白名单 → 分类（LLM/规则） → 低置信度二次判定 → 分级处置。

设计对应评审结论：
- 判定走「整句分类 + 白名单兜底 + LLM 二次判定」，刻意避开 US12549500 的
  「延续判断→向量短清单→AI判定→拒绝通知」特征链（规避设计路径 A，见 patent-disclosure）。
- 分级处置：学习→放行；敏感/红线→拒绝；娱乐及其他→引导性改写（对冲过滤过严的用户反弹，S6）。
- 验收指标（TC260 框架 + 学习话题双题库）见 guardrail-acceptance-plan，题库评测脚本在 tools/eval_fence.py。
"""
import json
import re

from ..config import settings
from . import llm

# 红线词兜底：命中即硬拒绝（最小集，生产替换为 TC260 应拒答题库驱动的完整词表）
REDLINE_PATTERNS = [
    r"自杀|自残|割腕|轻生",
    r"色情|裸聊|约炮",
    r"毒品|冰毒|摇头丸",
    r"赌博|赌球|博彩",
    r"枪支|弹药|炸弹|爆炸物",
    r"怎么(?:杀|弄死).{0,6}人",
    r"偷东西|恐吓信|假币|霸凌|作弊考试|考试作弊",
    r"黑别人(?:的)?账号|进入别人电脑",
    r"管制刀具|违禁刀|翻墙进",
    r"安眠药.{0,6}(?:出事|死)",
    r"酒驾|醉驾",
    r"危险气体|制取.{0,6}气体",
]

# 学习信号（heuristic 降级模式用；llm 模式仅作参考不直接放行）
STUDY_HINTS = re.compile(
    r"作业|题目|方程|函数|单词|语法|作文|阅读|背诵|公式|定理|历史|地理|物理|化学|生物|"
    r"数学|语文|英语|考试|复习|预习|知识点|讲解|怎么解|为什么|如何写|翻译|"
    r"光合|细胞|元素周期|化学反应|古诗|修辞|成语|应用题|几何|三角形",
    re.I,
)
ENTERTAINMENT_HINTS = re.compile(r"游戏|明星|八卦|追剧|段子|笑话|吐槽|直播|网红|皮肤|充值")

CLASSIFY_SYSTEM = (
    "你是未成年人AI助学产品的学习话题分类器。判断用户输入是否属于学习内容。"
    "只输出JSON：{\"category\":\"study|entertainment|sensitive|other\",\"confidence\":0到1}。"
    "study=学科答疑/学习方法/教育性讨论；entertainment=纯娱乐流行文化；"
    "sensitive=暴力色情自伤违法等；other=其他非学习。"
)
SECOND_PASS_SYSTEM = (
    "你是复核员。请严格复核该输入是否属于学习内容，宁可错杀不可放过敏感内容，"
    "但日常学科问题必须判为study。只输出JSON："
    "{\"category\":\"study|entertainment|sensitive|other\",\"confidence\":0到1}。"
)

REJECT_REPLY = "这个问题我不能回答。如果你遇到了让你难受的事情，请告诉家长或老师。我们回到学习上来吧——有什么作业或知识点需要讲解吗？"


def _heuristic_classify(content: str) -> tuple[str, float]:
    if any(re.search(p, content) for p in REDLINE_PATTERNS):
        return "sensitive", 1.0
    study = bool(STUDY_HINTS.search(content))
    ent = bool(ENTERTAINMENT_HINTS.search(content))
    if study and not ent:
        return "study", 0.7
    if ent and not study:
        return "entertainment", 0.7
    if study and ent:
        return "study", 0.55
    return "other", 0.5


async def _llm_classify(content: str, system: str, family_id: int | None = None) -> tuple[str, float, dict]:
    result = await llm.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": content}],
        purpose="fence_classify", max_tokens=64, temperature=0.0, family_id=family_id,
    )
    try:
        data = json.loads(re.search(r"\{.*\}", result["content"], re.S).group(0))
        return data.get("category", "other"), float(data.get("confidence", 0.5)), result
    except (ValueError, AttributeError):
        return "other", 0.4, result


async def evaluate(content: str, grade_band: str = "8-12", family_id: int | None = None,
                   recent_user_texts: list[str] | None = None) -> dict:
    """返回 {decision: allow|rewrite|reject, category, confidence, stages: [FenceEvent dict...]}。

    recent_user_texts：当前消息之前的最近用户输入（最多取 2 条）。仅 llm 模式启用
    上下文级检查（多轮铺垫防御）：当前句分类非 sensitive 时，把「最近输入 + 当前句」
    拼接再分类一次，拼接后判 sensitive 则按 sensitive 处置——对抗"前几轮无害铺垫、
    后一轮省略式越界"的绕过。heuristic 模式无语义能力，跳过（见 fence-design 已知局限）。
    """
    stages = []

    def record(stage, decision, category, confidence, detail=""):
        stages.append({"stage": stage, "decision": decision, "category": category,
                       "confidence": confidence, "detail": detail})
        return decision

    # 1) 红线白名单：命中即拒，不做分类
    for pattern in REDLINE_PATTERNS:
        if re.search(pattern, content):
            record("whitelist", "reject", "sensitive", 1.0, pattern)
            record("policy", "reject", "sensitive", 1.0, "whitelist hard reject")
            return {"decision": "reject", "category": "sensitive", "confidence": 1.0, "stages": stages}

    # 2) 分类
    if settings.fence_mode == "llm":
        try:
            category, confidence, llm_result = await _llm_classify(content, CLASSIFY_SYSTEM, family_id)
        except llm.LLMUnavailable:
            category, confidence = _heuristic_classify(content)
            record("classifier", "pending", category, confidence, "llm unavailable -> heuristic")
        else:
            record("classifier", "pending", category, confidence, "llm")
    else:
        category, confidence = _heuristic_classify(content)
        record("classifier", "pending", category, confidence, "heuristic")

    # 2.5) 上下文级检查（仅 llm 模式；多轮铺垫防御的轻量版）
    if (settings.fence_mode == "llm" and recent_user_texts
            and category != "sensitive"):
        joined = "\n".join([*recent_user_texts[-2:], content])[:2000]
        try:
            ctx_cat, ctx_conf, _ = await _llm_classify(joined, CLASSIFY_SYSTEM, family_id)
        except llm.LLMUnavailable:
            record("context_check", "allow", category, confidence, "llm unavailable, skip")
        else:
            if ctx_cat == "sensitive":
                category, confidence = ctx_cat, max(confidence, ctx_conf)
                record("context_check", "pending", category, confidence,
                       "context join -> sensitive")
            else:
                record("context_check", "allow", category, confidence, "context clean")

    # 3) 低置信度二次判定（仅 llm 模式；heuristic 的 0.55/0.5 阈值直接走处置）
    if settings.fence_mode == "llm" and confidence < 0.6 and category != "sensitive":
        try:
            category2, confidence2, _ = await _llm_classify(content, SECOND_PASS_SYSTEM, family_id)
            record("second_pass", "pending", category2, confidence2, "second pass")
            category, confidence = category2, max(confidence, confidence2)
        except llm.LLMUnavailable:
            record("second_pass", "allow", category, confidence, "llm unavailable, keep first pass")

    # 4) 分级处置
    if category == "study":
        decision = "allow"
    elif category == "sensitive":
        decision = "reject"
    else:
        decision = "rewrite"  # 引导性改写：不硬拒绝，把话题带回学习
    record("policy", decision, category, confidence)
    return {"decision": decision, "category": category, "confidence": confidence, "stages": stages}


GUIDANCE_PREFIX = "咱们把话题放回学习上吧。"
