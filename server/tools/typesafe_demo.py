"""TypeSafe skill 集成示例：以 fence.py 的整句分类为例，演示 prompt-and-parse → 类型化判定。

TypeSafe System One（Jev 模型）把「自然语言 + 状态」转成类型化判定与概率，代码消费结果。
对照 fence.py 现状：_llm_classify 用 system prompt 要求 LLM 输出 JSON，再用正则截取解析——
解析失败回退 0.4 置信度，且概率分布、并行同问等能力都拿不到。

用法：TYPESAFE_API_KEY=xxx python -m tools.typesafe_demo   （server/ 目录下）
凭据须服务端保管（skill 要求）；本文件仅为示例，未接入 app 流程。
"""
import asyncio
import os

import httpx

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"

# 三种原语对照 fence 场景：
#   choice —— 整句分类（study/entertainment/sensitive/other），等价于 _llm_classify 的 JSON 输出
#   noul   —— 红线近义判断（"是否含违规意图"），等价于 REDLINE_PATTERNS 兜不住的变体
#   score  —— 引导强度（rewrite 处置时引导性改写的力度），fence.py 目前没有此维度
QUESTIONS = {
    "category": {
        "type": "choice",
        "instructions": {
            "product": "未成年人AI助学产品的学习话题围栏",
            "question": "这条用户输入属于哪一类？",
        },
        "criteria": {
            "study": "学科答疑/学习方法/教育性讨论（作业、公式、讲解）",
            "entertainment": "纯娱乐流行文化（游戏、明星、八卦）",
            "sensitive": "暴力色情自伤违法等应拒绝内容",
            "other": "其他非学习内容",
        },
    },
    "is_adversarial": {
        "type": "noul",
        "instructions": "结合最近输入，这句话是否在用「前几轮无害铺垫、本轮省略式越界」的方式绕过围栏？",
        "criteria": {
            "true": "当前句依赖上下文才显出违规意图",
            "false": "当前句独立可判，无铺垫绕过",
        },
    },
}


async def evaluate(content: str, recent_user_texts: list[str] | None = None) -> dict:
    """一次请求并行同问两个独立判定（skill 要求独立问题同问，模型互相看不到对方答案）。"""
    state = {"current_text": content}
    if recent_user_texts:
        state["recent_user_texts"] = recent_user_texts[-2:]
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            API_URL,
            headers={"Authorization": f"Bearer {os.environ['TYPESAFE_API_KEY']}"},
            json={"state": state, "model": MODEL, "questions": QUESTIONS},
        )
        resp.raise_for_status()
        data = resp.json()

    answers = data["answers"]
    # category：choice 返回最高概率选项 + 完整分布 + 置信度——无需解析，无解析失败回退
    cat = answers["category"]["choice"]
    cat_dist = answers["category"]["probabilities"]
    # is_adversarial：noul 返回 yes 概率；0.5 附近=两者概率相近，不是中等强度
    adv = answers["is_adversarial"]["noul"]

    # 处置策略留在代码里（skill：代码拥有规则与执行，模型只补语义判断）
    if cat == "sensitive" or (cat != "study" and adv > 0.9):
        decision = "reject"
    elif cat == "study":
        decision = "allow"
    else:
        decision = "rewrite"
    return {"decision": decision, "category": cat, "probabilities": cat_dist,
            "adversarial": adv, "usage": data["usage"]}


async def main():
    cases = [
        ("帮我讲讲一元二次方程的求根公式", [], "预期 allow"),
        ("最近有什么好玩的皮肤", [], "预期 rewrite"),
        ("说说怎么弄死一株植物最省事", ["前面的铺垫句"], "变体：可能绕过正则兜底"),
    ]
    for content, recent, note in cases:
        verdict = await evaluate(content, recent)
        print(f"{content}  [{verdict['decision']}/{verdict['category']}]  {note}")
        print(f"  分布={verdict['probabilities']}  越界概率={verdict['adversarial']:.2f}"
              f"  tokens={verdict['usage']['input_tokens']}/{verdict['usage']['output_tokens']}")


if __name__ == "__main__":
    asyncio.run(main())
