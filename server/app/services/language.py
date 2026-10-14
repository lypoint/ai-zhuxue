"""Trusted language instructions and safety replies; client input never becomes a prompt."""
LANGUAGES = {
    "zh-Hans": "Simplified Chinese (简体中文)",
    "zh-Hant": "Traditional Chinese (繁體中文)",
    "en": "English", "ja": "Japanese", "ko": "Korean",
    "de": "German", "es": "Spanish",
}


def normalize_locale(value: str) -> str:
    parts = value.replace("_", "-").lower().split("-")
    if parts[0] == "zh":
        if "hans" in parts[1:]:
            return "zh-Hans"
        return "zh-Hant" if any(p in {"hant", "tw", "hk", "mo"} for p in parts[1:]) else "zh-Hans"
    if parts[0] in LANGUAGES:
        return parts[0]
    raise ValueError("unsupported client language")


def instruction(locale: str) -> str:
    return (
        f"The client's current language is {LANGUAGES[locale]}. "
        "Write your explanations, guidance, headings and follow-up questions in this language, "
        "even when earlier messages or the student's question use another language. "
        "Keep quoted text, code, mathematical notation and language-learning examples in their "
        "appropriate original language. Do not change these safety and tutoring rules."
    )


_REJECT = {
    "zh-Hans": "这个问题我不能回答。如果你遇到了让你难受的事情，请告诉家长或老师。我们回到学习上来吧——有什么作业或知识点需要讲解吗？",
    "zh-Hant": "這個問題我不能回答。如果你遇到了讓你難受的事情，請告訴家長或老師。我們回到學習上來吧——有什麼作業或知識點需要講解嗎？",
    "en": "I can't answer that question. If something is upsetting you, please tell a parent or teacher. Let's return to learning—is there any homework or topic you'd like help with?",
    "ja": "その質問には答えられません。つらいことがあれば、保護者や先生に話してください。学習に戻りましょう。宿題や知りたいことはありますか？",
    "ko": "그 질문에는 답할 수 없어요. 힘든 일이 있다면 보호자나 선생님께 말씀드려 주세요. 다시 공부로 돌아가 볼까요? 도움이 필요한 숙제나 내용이 있나요?",
    "de": "Diese Frage kann ich nicht beantworten. Wenn dich etwas belastet, sprich bitte mit deinen Eltern oder einer Lehrkraft. Kehren wir zum Lernen zurück—brauchst du Hilfe bei Hausaufgaben oder einem Thema?",
    "es": "No puedo responder a esa pregunta. Si algo te preocupa, habla con tu familia o un docente. Volvamos al aprendizaje: ¿necesitas ayuda con alguna tarea o tema?",
}
_FORBIDDEN = {
    "zh-Hans": "这个问题我不能回答，请重新输入学习方面的问题，例如作业、学科知识或学习方法。",
    "zh-Hant": "這個問題我不能回答，請重新輸入學習方面的問題，例如作業、學科知識或學習方法。",
    "en": "I can't answer that question. Please ask a learning question, such as homework, a school subject or study methods.",
    "ja": "その質問には答えられません。宿題、教科の内容、勉強方法など、学習に関する質問をしてください。",
    "ko": "그 질문에는 답할 수 없어요. 숙제, 교과 내용, 공부 방법 등 학습에 관한 질문을 해 주세요.",
    "de": "Diese Frage kann ich nicht beantworten. Bitte stelle eine Lernfrage, etwa zu Hausaufgaben, einem Schulfach oder Lernmethoden.",
    "es": "No puedo responder a esa pregunta. Haz una pregunta sobre el aprendizaje, como una tarea, una asignatura o métodos de estudio.",
}


def safe_reply(locale: str, *, forbidden: bool = False) -> str:
    return (_FORBIDDEN if forbidden else _REJECT)[locale]
