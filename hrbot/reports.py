"""Deterministic answers calculated from stored data, never guessed by a model."""

from __future__ import annotations

import re
from datetime import datetime

from .config import Settings
from .interpret import MONTHS
from .storage import Store


def mentioned(text: str, candidate: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(candidate.casefold()) + r"(?!\w)", text.casefold()))


def answer(question: str, store: Store, settings: Settings, now: datetime) -> str:
    q = question.casefold()
    rows = store.records()
    salary = any(word in q for word in ("salary", "تنخواہ"))
    commission = any(word in q for word in ("commission", "کمیشن"))
    if salary or commission:
        kind = "salary" if salary else "commission"
        names = store.names_for_compensation(kind)
        person = next((name for name in sorted(names, key=len, reverse=True) if mentioned(q, name)), None)
        if not person:
            return f"{kind.title()} ke liye naam clear nahin. Misal: 'Daniel ki {kind} kitni hai?'"
        amount = store.compensation(person, kind)
        return f"{person} ki {kind} {amount:,} PKR hai." if amount is not None else f"{person} ki {kind} ka record nahin mila."

    fields = sorted(set(settings.supervisors) | {row["field"] for row in rows}, key=len, reverse=True)
    field = next((value for value in fields if mentioned(q, value)), None)
    if field is None:
        field = next((canonical for alias, canonical in sorted(settings.field_aliases.items(), key=lambda x: -len(x[0])) if mentioned(q, alias)), None)
    supervisors = sorted(set(settings.supervisors.values()) | {row["supervisor"] for row in rows}, key=len, reverse=True)
    supervisor = next((value for value in supervisors if mentioned(q, value)), None)
    names = sorted({row["name"] for row in rows}, key=len, reverse=True)
    person = next((name for name in names if mentioned(q, name)), None)

    count_question = any(word in q for word in ("kitne", "kitni", "how many", "count", "total", "کتنے", "کتنی", "تعداد"))
    if person and not count_question and not (supervisor and mentioned(q, "under")):
        matches = [row for row in rows if row["name_key"] == Store.key(person)]
        if not matches:
            return f"{person} ka record nahin mila."
        lines = [f"{row['name']}: {row['field']}, supervisor {row['supervisor']}, registration {row['registration_date']}" for row in matches[:8]]
        return "\n".join(lines)

    filtered = rows
    labels = []
    if field:
        filtered = [row for row in filtered if row["field_key"] == Store.key(field)]
        labels.append(field)
    if supervisor:
        filtered = [row for row in filtered if Store.key(row["supervisor"]) == Store.key(supervisor)]
        labels.append(f"{supervisor} supervisor")
    if any(mentioned(q, token) for token in ("today", "aaj", "aj", "آج")):
        filtered = [row for row in filtered if row["registration_date"] == now.date().isoformat()]
        labels.append("aaj")
    else:
        month = next((number for name, number in MONTHS.items() if mentioned(q, name)), None)
        if month is not None:
            year_match = re.search(r"\b20\d{2}\b", q)
            year = int(year_match.group()) if year_match else now.year
            filtered = [row for row in filtered if row["registration_date"].startswith(f"{year}-{month:02d}")]
            labels.append(f"{year}-{month:02d}")
    if count_question or field or supervisor or labels:
        scope = ", ".join(labels) if labels else "total"
        return f"{scope} registrations: {len(filtered)}."
    return "Query clear nahin. Misal: 'Aaj kitne registrations hue?' ya 'Fatima ka supervisor kon hai?'"
