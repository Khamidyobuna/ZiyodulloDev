from __future__ import annotations

from typing import Iterable

import google.generativeai as genai

from config import CHAT_HISTORY_LIMIT, GEMINI_MODEL_CANDIDATES, GOOGLE_AI_API_KEY, ZIYODEV_SYSTEM_PROMPT
from models import ChatHistory, get_db_session


genai.configure(api_key=GOOGLE_AI_API_KEY)


def save_chat_message(user_identifier: str, role: str, message_content: str) -> None:
    db_session = get_db_session()
    try:
        db_session.add(
            ChatHistory(
                user_identifier=user_identifier,
                role=role,
                message_content=message_content,
            )
        )
        db_session.commit()
    finally:
        db_session.close()


def get_recent_history(user_identifier: str, limit: int = CHAT_HISTORY_LIMIT) -> list[ChatHistory]:
    db_session = get_db_session()
    try:
        messages = (
            db_session.query(ChatHistory)
            .filter(ChatHistory.user_identifier == user_identifier)
            .order_by(ChatHistory.timestamp.desc(), ChatHistory.id.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(messages))
    finally:
        db_session.close()


def build_prompt(history: Iterable[ChatHistory], preferred_language: str | None = None) -> str:
    lines = [f"System instruction: {ZIYODEV_SYSTEM_PROMPT}"]
    if preferred_language:
        lines.append(
            f"Preferred interface language hint: {preferred_language}. "
            "Still prioritize the language used in the latest user message."
        )
    lines.extend(["", "Conversation history:"])
    for item in history:
        speaker = "User" if item.role == "user" else "Assistant"
        lines.append(f"{speaker}: {item.message_content}")
    lines.append("")
    lines.append(
        "Answer naturally, clearly, and in the same language as the user's latest message unless they request otherwise."
    )
    return "\n".join(lines)


def extract_text(response) -> str:
    if getattr(response, "text", None):
        return response.text.strip()

    candidates = getattr(response, "candidates", None) or []
    parts: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", []) or []:
            text = getattr(part, "text", None)
            if text:
                parts.append(text)

    return "\n".join(parts).strip()


def localized_unavailable_message(preferred_language: str | None) -> str:
    messages = {
        "uz": "Hozir AI xizmatiga ulanib bo'lmadi. Iltimos, birozdan keyin yana urinib ko'ring.",
        "en": "I couldn't reach the AI service right now. Please try again in a moment.",
        "ru": "Сейчас не удалось подключиться к AI-сервису. Пожалуйста, попробуйте немного позже.",
    }
    return messages.get(preferred_language or "uz", messages["uz"])


def generate_ai_reply(
    user_identifier: str,
    user_message: str,
    preferred_language: str | None = None,
) -> str:
    clean_user_message = user_message.strip()
    save_chat_message(user_identifier, "user", clean_user_message)
    history = get_recent_history(user_identifier)
    prompt = build_prompt(history, preferred_language=preferred_language)

    last_error = None
    reply_text = ""
    for model_name in GEMINI_MODEL_CANDIDATES:
        try:
            model = genai.GenerativeModel(model_name=model_name)
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.8,
                    "max_output_tokens": 900,
                },
            )
            reply_text = extract_text(response)
            if reply_text:
                break
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            last_error = exc

    if not reply_text:
        base_message = localized_unavailable_message(preferred_language)
        error_hint = f" Texnik tafsilot: {last_error}" if last_error and preferred_language == "uz" else ""
        reply_text = f"{base_message}{error_hint}"

    save_chat_message(user_identifier, "model", reply_text)
    return reply_text
