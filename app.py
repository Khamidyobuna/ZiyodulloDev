from __future__ import annotations

import json
import re
import secrets
from functools import wraps

import requests
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

from ai_service import generate_ai_reply
from config import (
    ADMIN_SECRET_SLUG,
    DEFAULT_LANGUAGE,
    FLASK_SECRET_KEY,
    NOTIFICATION_BOT_TOKEN,
    NOTIFICATION_CHAT_ID,
    SUPPORTED_LANGUAGES,
)
from models import (
    AdminSettings,
    ContactMessages,
    SiteContent,
    close_db_session,
    get_admin_settings,
    get_db_session,
    init_db,
)
from translations import LANGUAGE_LABELS, get_page_meta, t


app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
init_db()

PAGE_ENDPOINTS = {
    "home": "home",
    "interests": "interests",
    "about": "about",
    "contact": "contact_page",
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or f"section-{secrets.token_hex(4)}"


def get_current_language() -> str:
    lang = request.args.get("lang") or session.get("lang") or DEFAULT_LANGUAGE
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE
    session["lang"] = lang
    return lang


def translate(key: str, lang: str | None = None) -> str:
    return t(key, lang or get_current_language())


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get("admin_logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "message": translate("toast.save_error")}), 401
            return redirect(url_for("admin_login", lang=get_current_language()))
        return view_func(*args, **kwargs)

    return wrapped_view


def url_for_lang(endpoint: str, **values) -> str:
    values.setdefault("lang", get_current_language())
    return url_for(endpoint, **values)


def serialize_section(section: SiteContent, lang: str) -> dict:
    localized = section.get_localized(lang)
    translations = section.get_translations()
    return {
        "id": section.id,
        "section_id": section.section_id,
        "page_name": section.page_name,
        "sort_order": section.sort_order,
        "is_active": section.is_active,
        "title": localized["title"],
        "content_html": localized["content_html"],
        "translations": {
            code: {
                "title": translations.get(code, {}).get("title", localized["title"]),
                "content_html": translations.get(code, {}).get("content_html", localized["content_html"]),
            }
            for code in SUPPORTED_LANGUAGES
        },
    }


def get_sections_for_page(page_name: str, lang: str):
    db_session = get_db_session()
    try:
        sections = (
            db_session.query(SiteContent)
            .filter(SiteContent.page_name == page_name, SiteContent.is_active.is_(True))
            .order_by(SiteContent.sort_order.asc(), SiteContent.id.asc())
            .all()
        )
        return [serialize_section(section, lang) for section in sections]
    finally:
        db_session.close()


def get_or_create_web_identity() -> str:
    if "chat_identity" not in session:
        session["chat_identity"] = f"web:{secrets.token_urlsafe(16)}"
    return session["chat_identity"]


def send_telegram_notification(contact_message: ContactMessages) -> tuple[bool, str | None]:
    api_url = f"https://api.telegram.org/bot{NOTIFICATION_BOT_TOKEN}/sendMessage"
    text = (
        "Yangi ZiyoDev contact xabari\n\n"
        f"Ism: {contact_message.name}\n"
        f"Email: {contact_message.email}\n"
        f"Mavzu: {contact_message.subject or 'Kiritilmagan'}\n"
        f"Xabar:\n{contact_message.message_content}"
    )
    response = requests.post(
        api_url,
        data={
            "chat_id": NOTIFICATION_CHAT_ID,
            "text": text,
        },
        timeout=15,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.ok and payload.get("ok"):
        return True, None

    return False, payload.get("description") or response.text or "Unknown Telegram error"


def page_options(lang: str) -> list[dict[str, str]]:
    return [
        {"value": "home", "label": t("page.home", lang)},
        {"value": "interests", "label": t("page.interests", lang)},
        {"value": "about", "label": t("page.about", lang)},
        {"value": "contact", "label": t("page.contact", lang)},
    ]


@app.before_request
def persist_language():
    get_current_language()


@app.after_request
def apply_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.context_processor
def inject_globals():
    current_lang = get_current_language()
    return {
        "current_year": 2026,
        "current_lang": current_lang,
        "languages": LANGUAGE_LABELS,
        "t": lambda key: translate(key, current_lang),
        "url_for_lang": url_for_lang,
    }


@app.teardown_appcontext
def shutdown_session(exception=None):  # pragma: no cover - Flask lifecycle hook
    close_db_session()


def render_page(page_name: str):
    lang = get_current_language()
    sections = get_sections_for_page(page_name, lang)
    get_or_create_web_identity()
    return render_template(
        "page.html",
        active_page=page_name,
        page_name=page_name,
        page_title=get_page_meta(page_name, lang)["title"],
        page_meta=get_page_meta(page_name, lang),
        sections=sections,
    )


@app.route("/")
def home():
    return render_page("home")


@app.route("/interests")
def interests():
    return render_page("interests")


@app.route("/about")
def about():
    return render_page("about")


@app.route("/contact")
def contact_page():
    return render_page("contact")


@app.route("/set-language/<lang>")
def set_language(lang: str):
    next_url = request.args.get("next") or url_for("home")
    if lang in SUPPORTED_LANGUAGES:
        session["lang"] = lang
    return redirect(next_url)


@app.route("/admin")
@app.route("/admin/login")
@app.route("/admin/logout")
def hidden_admin_routes():
    abort(404)


@app.route(f"/{ADMIN_SECRET_SLUG}/login", methods=["GET", "POST"])
def admin_login():
    lang = get_current_language()
    error_message = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        db_session = get_db_session()
        try:
            settings = get_admin_settings(db_session)
            if username == settings.username and settings.check_password(password):
                session["admin_logged_in"] = True
                return redirect(url_for("admin_dashboard", lang=lang))
        finally:
            db_session.close()
        error_message = {
            "uz": "Login yoki parol noto'g'ri.",
            "en": "Incorrect username or password.",
            "ru": "Неверный логин или пароль.",
        }[lang]
    return render_template("admin_login.html", error_message=error_message)


@app.route(f"/{ADMIN_SECRET_SLUG}/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login", lang=get_current_language()))


@app.route(f"/{ADMIN_SECRET_SLUG}")
@admin_required
def admin_dashboard():
    lang = get_current_language()
    db_session = get_db_session()
    try:
        sections = (
            db_session.query(SiteContent)
            .order_by(SiteContent.page_name.asc(), SiteContent.sort_order.asc(), SiteContent.id.asc())
            .all()
        )
        messages = (
            db_session.query(ContactMessages)
            .order_by(ContactMessages.created_at.desc(), ContactMessages.id.desc())
            .all()
        )
        serialized_sections = [serialize_section(section, lang) for section in sections]
        admin_settings = get_admin_settings(db_session)
        return render_template(
            "admin_dashboard.html",
            sections=serialized_sections,
            messages=messages,
            section_count=len(sections),
            message_count=len(messages),
            page_options=page_options(lang),
            admin_username=admin_settings.username,
        )
    finally:
        db_session.close()


def collect_translations(payload: dict) -> dict:
    translations = {}
    for lang in SUPPORTED_LANGUAGES:
        title_key = f"title_{lang}"
        content_key = f"content_html_{lang}"
        translations[lang] = {
            "title": (payload.get(title_key) or "").strip(),
            "content_html": (payload.get(content_key) or "").strip(),
        }
    uz_title = translations["uz"]["title"] or (payload.get("title") or "").strip()
    uz_content = translations["uz"]["content_html"] or (payload.get("content_html") or "").strip()

    for lang in SUPPORTED_LANGUAGES:
        translations[lang]["title"] = translations[lang]["title"] or uz_title
        translations[lang]["content_html"] = translations[lang]["content_html"] or uz_content

    return translations


@app.post("/api/update-content")
@admin_required
def update_content():
    payload = request.get_json(silent=True) or {}
    content_id = payload.get("content_id")
    page_name = (payload.get("page_name") or "").strip().lower()
    section_id = (payload.get("section_id") or "").strip()
    sort_order = int(payload.get("sort_order") or 0)
    is_active = bool(payload.get("is_active"))
    translations = collect_translations(payload)

    if not page_name or not translations["uz"]["title"] or not translations["uz"]["content_html"]:
        return jsonify({"success": False, "message": "Sahifa, o'zbekcha sarlavha va o'zbekcha kontent majburiy."}), 400

    db_session = get_db_session()
    try:
        if content_id:
            section = db_session.query(SiteContent).filter(SiteContent.id == int(content_id)).first()
            if not section:
                return jsonify({"success": False, "message": "Bo'lim topilmadi."}), 404
        else:
            base_section_id = section_id or f"{page_name}-{slugify(translations['uz']['title'])}"
            unique_section_id = base_section_id
            counter = 1
            while db_session.query(SiteContent).filter(SiteContent.section_id == unique_section_id).first():
                counter += 1
                unique_section_id = f"{base_section_id}-{counter}"
            section = SiteContent(
                section_id=unique_section_id,
                page_name=page_name,
                title=translations["uz"]["title"],
                content_html=translations["uz"]["content_html"],
            )
            db_session.add(section)

        requested_section_id = section_id or section.section_id
        duplicate = (
            db_session.query(SiteContent)
            .filter(SiteContent.section_id == requested_section_id, SiteContent.id != getattr(section, "id", 0))
            .first()
        )
        if duplicate:
            return jsonify({"success": False, "message": "Bu section_id allaqachon mavjud."}), 400

        section.section_id = requested_section_id
        section.page_name = page_name
        section.sort_order = sort_order
        section.is_active = is_active
        section.title = translations["uz"]["title"]
        section.content_html = translations["uz"]["content_html"]
        section.set_translations(translations)

        db_session.commit()
        return jsonify(
            {
                "success": True,
                "message": translate("toast.save_success"),
                "redirect_url": url_for(PAGE_ENDPOINTS.get(page_name, "home"), lang=get_current_language()),
            }
        )
    finally:
        db_session.close()


@app.post("/api/send-contact")
def send_contact():
    lang = get_current_language()
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip()
    subject = (payload.get("subject") or "").strip()
    message_content = (payload.get("message") or "").strip()

    if not name or not email or not message_content:
        return jsonify({"success": False, "message": translate("toast.contact_error", lang)}), 400

    db_session = get_db_session()
    try:
        contact_message = ContactMessages(
            name=name,
            email=email,
            subject=subject,
            message_content=message_content,
        )
        db_session.add(contact_message)
        db_session.commit()

        sent, error_description = send_telegram_notification(contact_message)
        response_payload = {
            "success": True,
            "message": translate("toast.contact_success", lang),
            "telegram_sent": sent,
        }

        if not sent:
            response_payload["warning"] = error_description
            if error_description and "chat not found" in error_description.lower():
                response_payload["warning_human"] = {
                    "uz": "Telegram bot chat_id ni topa olmadi. Botga avval /start yuborish yoki chat_id ni qayta tekshirish kerak.",
                    "en": "Telegram could not find this chat ID. Start the bot first or verify the chat ID.",
                    "ru": "Telegram не нашёл этот chat ID. Сначала отправьте боту /start или проверьте chat ID.",
                }[lang]

        return jsonify(response_payload)
    finally:
        db_session.close()


@app.post("/api/chat")
def chat_api():
    payload = request.get_json(silent=True) or {}
    user_message = (payload.get("message") or "").strip()
    if not user_message:
        return jsonify({"success": False, "message": translate("chat.error")}), 400

    user_identifier = get_or_create_web_identity()
    reply = generate_ai_reply(
        user_identifier=user_identifier,
        user_message=user_message,
        preferred_language=get_current_language(),
    )
    return jsonify({"success": True, "reply": reply})


@app.post("/api/update-admin-settings")
@admin_required
def update_admin_settings():
    lang = get_current_language()
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    current_password = (payload.get("current_password") or "").strip()
    new_password = (payload.get("new_password") or "").strip()
    confirm_password = (payload.get("confirm_password") or "").strip()

    if not username or not current_password:
        return jsonify({"success": False, "message": translate("admin.settings_required", lang)}), 400

    if new_password and len(new_password) < 6:
        return jsonify({"success": False, "message": translate("admin.settings_password_short", lang)}), 400

    if new_password != confirm_password:
        return jsonify({"success": False, "message": translate("admin.settings_password_mismatch", lang)}), 400

    db_session = get_db_session()
    try:
        settings = get_admin_settings(db_session)
        duplicate = (
            db_session.query(AdminSettings)
            .filter(AdminSettings.username == username, AdminSettings.id != settings.id)
            .first()
        )
        if duplicate:
            return jsonify({"success": False, "message": translate("admin.settings_username_taken", lang)}), 400

        if not settings.check_password(current_password):
            return jsonify({"success": False, "message": translate("admin.settings_current_wrong", lang)}), 400

        settings.username = username
        if new_password:
            settings.set_password(new_password)

        db_session.commit()
        session["admin_logged_in"] = True
        return jsonify({"success": True, "message": translate("admin.settings_saved", lang)})
    finally:
        db_session.close()


if __name__ == "__main__":
    app.run(debug=True)
