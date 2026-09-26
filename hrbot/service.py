"""One pipeline for CLI and WhatsApp input."""

from __future__ import annotations

from datetime import datetime

from .config import Settings
from .interpret import interpret
from .reports import answer
from .sheets import sync
from .storage import Store


def process(text: str, store: Store, settings: Settings, *, message_id: str = "") -> str:
    if message_id:
        previous = store.previous_reply(message_id)
        if previous is not None:
            return previous
    now = datetime.now(settings.timezone)
    parsed = interpret(text, settings, now)
    if parsed.kind == "query":
        reply = answer(parsed.question, store, settings, now)
    elif parsed.kind == "entry":
        added, updated = store.upsert_entries(parsed.entries, settings.supervisors)
        names = ", ".join(entry.name for entry in parsed.entries)
        reply = f"Saved: {names}. New: {added}; existing updated: {updated}."
        unassigned = [entry.field_name for entry in parsed.entries if entry.field_name not in settings.supervisors]
        if unassigned:
            reply += " Supervisor mapping missing: " + ", ".join(sorted(set(unassigned))) + "."
        if settings.sheet_id:
            try:
                sync(store, settings)
            except Exception as exc:
                reply += f" Google Sheets sync pending ({type(exc).__name__}); local data saved."
    elif parsed.kind == "compensation":
        name, kind, amount = parsed.compensation
        store.set_compensation(name, kind, amount)
        reply = f"{name} ki {kind} {amount:,} PKR save ho gayi."
        if settings.sheet_id:
            try:
                sync(store, settings)
            except Exception as exc:
                reply += f" Google Sheets sync pending ({type(exc).__name__}); local data saved."
    else:
        reply = parsed.reason
    if message_id:
        store.save_reply(message_id, reply)
    return reply
