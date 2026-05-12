"""Telegram bot for motor nameplate intake.

Conversation flow:
  1. User sends /start - bot explains it expects a photo of the nameplate.
  2. User uploads a photo.
  3. Bot runs Claude Vision -> extracts every field it can read.
  4. Bot loops through the field queue (unreadable fields first, then the
     fields that never appear on a nameplate like CLIENT/REQ/PO/TAG/work
     types) and asks the operator one question at a time.
  5. Bot renders the PDF and sends it back.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from pdf_form import (
    CHECKBOX_WORK_ROW1,
    CHECKBOX_WORK_ROW2,
    ENCLOSURES,
    FormData,
    render,
)
from vision import FORM_FIELDS, extract_nameplate

load_dotenv()

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
log = logging.getLogger("bot")

ASKING = 1
WORK_TYPES = 2
ENCLOSURE = 3

# Order of supplemental questions that never appear on a nameplate.
SUPPLEMENTAL_QUESTIONS: list[tuple[str, str]] = [
    ("bon_de_travail", "Номер бону (наприклад A 31703)"),
    ("date_j", "Дата прийому — день (DD)"),
    ("date_m", "Місяць (MM)"),
    ("date_a", "Рік (YY)"),
    ("client", "Клієнт (CLIENT)"),
    ("req", "REQ"),
    ("po", "PO"),
    ("tag", "TAG"),
    ("spec", "SPEC"),
    ("special", "SPECIAL (особливі примітки, або '-' якщо немає)"),
    ("autorise_par", "Autorise par (підпис / ім'я)"),
    ("exigence", "EXIGENCE DU CLIENT (наприклад 'Estimation')"),
]


@dataclass
class Session:
    extracted: dict = field(default_factory=dict)
    form: FormData = field(default_factory=FormData)
    queue: list[tuple[str, str]] = field(default_factory=list)  # (field_name, prompt)
    current: tuple[str, str] | None = None


def _build_question_queue(extracted: dict) -> list[tuple[str, str]]:
    """Decide what to ask the operator and in what order."""
    queue: list[tuple[str, str]] = []
    unreadable = {u["field"]: u.get("reason", "") for u in extracted.get("unreadable_fields", [])}

    for key, label in FORM_FIELDS:
        val = extracted.get(key)
        if key == "enclosure":
            continue  # handled with inline keyboard
        if not val or key in unreadable:
            reason = unreadable.get(key, "не видно на фото")
            queue.append((key, f"{label} — {reason}. Введіть значення вручну (або '-' якщо порожнє):"))
    return queue


def _summary(extracted: dict) -> str:
    lines = ["Розпізнав з шильдіка:"]
    for key, label in FORM_FIELDS:
        val = extracted.get(key)
        if val:
            lines.append(f"• {label}: {val}")
    unreadable = extracted.get("unreadable_fields", [])
    if unreadable:
        lines.append("\nНе вдалося прочитати:")
        for u in unreadable:
            lines.append(f"• {u['field']}: {u.get('reason', '?')}")
    return "\n".join(lines)


def _apply_extracted_to_form(form: FormData, extracted: dict) -> None:
    """Copy clean nameplate fields into the FormData object."""
    mapping = {
        "marque": "marque",
        "hp": "hp",
        "rpm": "rpm",
        "volts": "volts",
        "hz": "cy",
        "phase": "phase",
        "amps": "amps",
        "frame": "bati",
        "model": "modele",
        "serial": "serie",
        "type": "type",
    }
    for src, dst in mapping.items():
        val = extracted.get(src)
        if val:
            setattr(form, dst, str(val))
    enc = extracted.get("enclosure")
    if enc:
        # Normalise common variants
        e = enc.upper().replace(".", "").strip()
        if e in {"ODP"}:
            e = "DP"
        if e in ENCLOSURES:
            form.enclosure = e


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Привіт! Я допоможу заповнити бон прийому двигуна.\n"
        "Надішліть фото шильдіка двигуна, я розпізнаю поля і допитаюсь "
        "решту перед генерацією PDF.\n\n"
        "Команди: /cancel — почати спочатку."
    )
    ctx.user_data["session"] = Session()
    return ConversationHandler.END


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.pop("session", None)
    await update.message.reply_text("Скасовано. Надішліть нове фото шильдіка, коли будете готові.")
    return ConversationHandler.END


async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    photo = msg.photo[-1] if msg.photo else None
    document = msg.document if not photo and msg.document else None
    if not photo and not document:
        await msg.reply_text("Будь ласка, надішліть фото або зображення-документ.")
        return ConversationHandler.END

    await msg.reply_text("Розпізнаю шильдік... це займає 5-15 секунд.")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "nameplate.jpg"
        tg_file = await (photo.get_file() if photo else document.get_file())
        await tg_file.download_to_drive(str(path))
        try:
            extracted = await asyncio.to_thread(extract_nameplate, path)
        except Exception as exc:  # noqa: BLE001
            log.exception("vision failed")
            await msg.reply_text(f"Помилка розпізнавання: {exc}")
            return ConversationHandler.END

    session = Session(extracted=extracted)
    _apply_extracted_to_form(session.form, extracted)
    ctx.user_data["session"] = session

    await msg.reply_text(_summary(extracted))

    # Build queue: unreadable nameplate fields, then enclosure (if missing), then
    # supplemental fields, then work types.
    session.queue = _build_question_queue(extracted)
    if not session.form.enclosure:
        session.queue.append(("__enclosure__", "Оберіть тип корпусу:"))
    session.queue.extend(SUPPLEMENTAL_QUESTIONS)
    session.queue.append(("__work_types__", "Оберіть типи робіт (множинний вибір):"))

    return await _ask_next(update, ctx)


async def _ask_next(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    session: Session = ctx.user_data["session"]
    if not session.queue:
        return await _finish(update, ctx)

    session.current = session.queue.pop(0)
    field_name, prompt = session.current

    if field_name == "__enclosure__":
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(name, callback_data=f"enc:{name}") for name in ENCLOSURES]]
        )
        await _reply(update, prompt, reply_markup=kb)
        return ENCLOSURE
    if field_name == "__work_types__":
        return await _ask_work_types(update, ctx)

    await _reply(update, prompt)
    return ASKING


async def _reply(update: Update, text: str, **kwargs) -> None:
    if update.callback_query:
        await update.callback_query.message.reply_text(text, **kwargs)
    else:
        await update.message.reply_text(text, **kwargs)


async def on_text_answer(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    session: Session = ctx.user_data["session"]
    answer = (update.message.text or "").strip()
    if answer == "-":
        answer = ""
    field_name, _ = session.current
    # map vision keys onto form attrs
    target = {
        "marque": "marque", "hp": "hp", "rpm": "rpm", "volts": "volts", "hz": "cy",
        "phase": "phase", "amps": "amps", "frame": "bati", "model": "modele",
        "serial": "serie", "type": "type",
    }.get(field_name, field_name)
    if hasattr(session.form, target):
        setattr(session.form, target, answer)
    return await _ask_next(update, ctx)


async def on_enclosure(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    session: Session = ctx.user_data["session"]
    q = update.callback_query
    await q.answer()
    _, name = q.data.split(":", 1)
    session.form.enclosure = name
    await q.edit_message_text(f"Корпус: {name}")
    return await _ask_next(update, ctx)


async def _ask_work_types(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    session: Session = ctx.user_data["session"]
    rows = []
    for items in (CHECKBOX_WORK_ROW1, CHECKBOX_WORK_ROW2):
        row = []
        for label, key in items:
            marker = "✅" if key in session.form.work_types else "⬜"
            row.append(InlineKeyboardButton(f"{marker} {label}", callback_data=f"wt:{key}"))
            if len(row) == 4:
                rows.append(row); row = []
        if row:
            rows.append(row)
    rows.append([InlineKeyboardButton("✔ Готово", callback_data="wt:__done__")])

    text = "Оберіть типи робіт (натискайте щоб додати/прибрати, потім натисніть «Готово»):"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows))
    return WORK_TYPES


async def on_work_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    session: Session = ctx.user_data["session"]
    q = update.callback_query
    await q.answer()
    _, key = q.data.split(":", 1)
    if key == "__done__":
        await q.edit_message_text(
            "Типи робіт: " + (", ".join(sorted(session.form.work_types)) or "—")
        )
        return await _finish(update, ctx)
    if key in session.form.work_types:
        session.form.work_types.remove(key)
    else:
        session.form.work_types.add(key)
    return await _ask_work_types(update, ctx)


async def _finish(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    session: Session = ctx.user_data["session"]
    await _reply(update, "Генерую PDF...")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / f"bon_{session.form.bon_de_travail or 'travail'}.pdf"
        await asyncio.to_thread(render, session.form, out)
        with out.open("rb") as fh:
            if update.callback_query:
                await update.callback_query.message.reply_document(fh, filename=out.name)
            else:
                await update.message.reply_document(fh, filename=out.name)
    await _reply(update, "Готово. Надішліть нове фото щоб почати знову, або /cancel.")
    ctx.user_data.pop("session", None)
    return ConversationHandler.END


def build_app() -> Application:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_photo),
        ],
        states={
            ASKING: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_answer)],
            ENCLOSURE: [CallbackQueryHandler(on_enclosure, pattern=r"^enc:")],
            WORK_TYPES: [CallbackQueryHandler(on_work_type, pattern=r"^wt:")],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(conv)
    return app


if __name__ == "__main__":
    build_app().run_polling()
