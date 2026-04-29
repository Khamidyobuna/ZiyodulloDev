from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, scoped_session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash

from config import ADMIN_PASSWORD, ADMIN_USERNAME, DATABASE_URL
from translations import DEFAULT_SECTION_TRANSLATIONS


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = scoped_session(
    sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
)
Base = declarative_base()


class SiteContent(Base):
    __tablename__ = "site_content"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    page_name: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    content_html: Mapped[str] = mapped_column(Text, nullable=False)
    translations_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def get_translations(self) -> dict:
        try:
            data = json.loads(self.translations_json or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def set_translations(self, translations: dict) -> None:
        self.translations_json = json.dumps(translations, ensure_ascii=False)

    def get_localized(self, lang: str) -> dict[str, str]:
        translations = self.get_translations()
        localized = translations.get(lang, {})
        uz_fallback = translations.get("uz", {})
        return {
            "title": localized.get("title") or uz_fallback.get("title") or self.title,
            "content_html": localized.get("content_html") or uz_fallback.get("content_html") or self.content_html,
        }


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_identifier: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    message_content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ContactMessages(Base):
    __tablename__ = "contact_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    message_content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AdminSettings(Base):
    __tablename__ = "admin_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)


def get_db_session():
    return SessionLocal()


def close_db_session() -> None:
    SessionLocal.remove()


def ensure_site_content_schema() -> None:
    inspector = inspect(engine)
    if "site_content" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("site_content")}
    if "translations_json" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE site_content ADD COLUMN translations_json TEXT NOT NULL DEFAULT '{}'")
            )


def seed_admin_settings(db_session) -> None:
    settings = db_session.query(AdminSettings).first()
    if settings:
        return

    settings = AdminSettings(username=ADMIN_USERNAME, password_hash="")
    settings.set_password(ADMIN_PASSWORD)
    db_session.add(settings)
    db_session.flush()


def default_translations_for(section_id: str, title: str, content_html: str) -> dict:
    if section_id in DEFAULT_SECTION_TRANSLATIONS:
        return DEFAULT_SECTION_TRANSLATIONS[section_id]["translations"]
    return {
        "uz": {"title": title, "content_html": content_html},
        "en": {"title": title, "content_html": content_html},
        "ru": {"title": title, "content_html": content_html},
    }


def sync_default_site_content(db_session) -> None:
    for section_id, config in DEFAULT_SECTION_TRANSLATIONS.items():
        translations = config["translations"]
        uz_data = translations["uz"]
        section = db_session.query(SiteContent).filter(SiteContent.section_id == section_id).first()

        if not section:
            section = SiteContent(
                section_id=section_id,
                page_name=config["page_name"],
                title=uz_data["title"],
                content_html=uz_data["content_html"],
                sort_order=config["sort_order"],
                is_active=True,
            )
            section.set_translations(translations)
            db_session.add(section)
            continue

        existing_translations = section.get_translations()
        if not existing_translations:
            section.set_translations(translations)
        else:
            merged = translations | existing_translations
            section.set_translations(merged)

        legacy_titles = {item["title"] for item in translations.values()}
        legacy_contents = {item["content_html"] for item in translations.values()}
        if section.title in legacy_titles or section.content_html in legacy_contents:
            section.title = uz_data["title"]
            section.content_html = uz_data["content_html"]

        if not section.page_name:
            section.page_name = config["page_name"]
        if section.sort_order is None:
            section.sort_order = config["sort_order"]

    db_session.flush()


def ensure_all_sections_have_translations(db_session) -> None:
    sections = db_session.query(SiteContent).all()
    for section in sections:
        translations = section.get_translations()
        if not translations:
            section.set_translations(
                default_translations_for(section.section_id, section.title, section.content_html)
            )
        elif "uz" not in translations:
            translations["uz"] = {"title": section.title, "content_html": section.content_html}
            translations.setdefault("en", translations["uz"])
            translations.setdefault("ru", translations["uz"])
            section.set_translations(translations)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_site_content_schema()
    Base.metadata.create_all(bind=engine)

    db_session = get_db_session()
    try:
        seed_admin_settings(db_session)
        sync_default_site_content(db_session)
        ensure_all_sections_have_translations(db_session)
        db_session.commit()
    finally:
        db_session.close()
        close_db_session()


def get_admin_settings(db_session) -> AdminSettings:
    settings = db_session.query(AdminSettings).first()
    if not settings:
        settings = AdminSettings(username=ADMIN_USERNAME, password_hash="")
        settings.set_password(ADMIN_PASSWORD)
        db_session.add(settings)
        db_session.flush()
    return settings
