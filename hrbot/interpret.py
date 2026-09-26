"""Conservative extraction; uncertain input is returned for human correction."""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime

from .config import Settings


NAME = r"[A-Za-z\u0600-\u06ff][A-Za-z\u0600-\u06ff'\-]*"
MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7,
    "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
QUERY_WORDS = ("kitne", "kitni", "kya", "kon", "kaun", "count", "total", "how many", "what", "who", "کتنے", "کتنی", "کیا", "کون")


@dataclass
class Entry:
    name: str
    field_name: str
    registration_date: str
    extras: dict[str, str] = field(default_factory=dict)


@dataclass
class Interpretation:
    kind: str
    entries: list[Entry] = field(default_factory=list)
    compensation: tuple[str, str, int] | None = None
    question: str = ""
    reason: str = ""


def clean_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z\u0600-\u06ff'\-\s]", " ", value)
    words = value.strip().split()
    drop = {"aaj", "aj", "today", "student", "students", "register", "registered", "hue", "hain", "hai", "aur", "and", "ki", "ka", "ke", "ne", "نے", "آج", "طالب", "علم", "طلبہ", "رجسٹر", "ہوئے", "ہوئی", "کا", "کی", "ہے", "ہیں", "اور"}
    words = [w for w in words if w.casefold() not in drop]
    return " ".join(words[-3:]).strip()


def parse_date(text: str, now: datetime) -> str:
    low = text.casefold()
    if any(token in low for token in ("yesterday", "kal", "کل")):
        from datetime import timedelta
        return (now - timedelta(days=1)).date().isoformat()
    match = re.search(r"\b(\d{1,2})\s+([a-z]+)(?:\s+(\d{4}))?\b", low)
    if match and match.group(2) in MONTHS:
        day, month = int(match.group(1)), MONTHS[match.group(2)]
        year = int(match.group(3)) if match.group(3) else now.year
        try:
            return now.replace(year=year, month=month, day=day).date().isoformat()
        except ValueError:
            pass
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso:
        try:
            return datetime.fromisoformat(iso.group(1)).date().isoformat()
        except ValueError:
            pass
    return now.date().isoformat()


def _ollama(text: str, settings: Settings, now: datetime) -> Interpretation | None:
    if not settings.ollama_url or not settings.ollama_model:
        return None
    fields = list(settings.supervisors)
    prompt = (
        "Extract HR data from Urdu/Roman Urdu/English. Respond ONLY with JSON object: "
        '{"kind":"entry|compensation|query|unknown", "entries":[{"name":"",'
        '"field_name":"", "registration_date":"YYYY-MM-DD", "extras":{}}], '
        '"compensation":{"name":"", "type":"salary|commission", "amount":0}, "question":""}. '
        "Only extract explicitly stated facts. Never invent names, fields, salaries, or counts. "
        "If a field is unknown keep its spoken name. Dates without year use current year. "
        f"Today: {now.date().isoformat()}. Known fields: {fields}. Text: {text}"
    )
    body = json.dumps({"model": settings.ollama_model, "prompt": prompt, "stream": False, "format": "json"}).encode()
    request = urllib.request.Request(settings.ollama_url + "/api/generate", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = json.loads(response.read().decode())
        result = json.loads(raw["response"])
        kind = result.get("kind")
        if kind == "entry":
            entries = []
            for item in result.get("entries", []):
                name = clean_name(str(item.get("name", "")))
                field_name = str(item.get("field_name", "")).strip()[:80]
                date = str(item.get("registration_date", ""))
                datetime.fromisoformat(date)
                extras = {str(k)[:50]: str(v)[:200] for k, v in item.get("extras", {}).items() if k and v is not None}
                if name and field_name:
                    entries.append(Entry(name, settings.field_aliases.get(field_name.casefold(), field_name), date, extras))
            if entries:
                return Interpretation("entry", entries=entries)
        if kind == "compensation":
            item = result.get("compensation", {})
            name = clean_name(str(item.get("name", "")))
            comp_type = str(item.get("type", ""))
            amount = int(item.get("amount", 0))
            if name and comp_type in {"salary", "commission"} and amount > 0:
                return Interpretation("compensation", compensation=(name, comp_type, amount))
        if kind == "query":
            return Interpretation("query", question=text)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return None


def interpret(text: str, settings: Settings, now: datetime) -> Interpretation:
    text = " ".join(text.split()).strip()
    if not text:
        return Interpretation("unknown", reason="Khali message mila.")
    low = text.casefold()
    if "?" in text or "؟" in text or any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", low) for w in QUERY_WORDS):
        return Interpretation("query", question=text)
    model_result = _ollama(text, settings, now)
    if model_result:
        return model_result
    comp = re.search(rf"\b({NAME}(?:\s+{NAME})?)\s+(?:ki|ka|ke|کی|کا)?\s*(salary|commission|تنخواہ|کمیشن)\s+(?:is|hai|he|ہے|rs|pkr|روپے)?\s*([\d,]+)", text, re.I)
    if comp:
        kind = "salary" if comp.group(2).casefold() in {"salary", "تنخواہ"} else "commission"
        return Interpretation("compensation", compensation=(clean_name(comp.group(1)), kind, int(comp.group(3).replace(",", ""))))
    aliases = sorted(settings.field_aliases, key=len, reverse=True)
    if not aliases:
        return Interpretation("unknown", reason="Fields config mein define karein.")
    field_re = re.compile("|".join(re.escape(alias) for alias in aliases), re.I)
    matches = list(field_re.finditer(text))
    entries = []
    preceding = 0
    for match in matches:
        before = text[preceding:match.start()]
        segment = re.split(r"[,،.;]|\b(?:aur|and)\b|اور", before, flags=re.I)[-1]
        name = clean_name(segment)
        if not name:
            return Interpretation("unknown", reason=f"'{match.group()}' ke student ka naam clear nahin. Naam aur field dobara bhejein.")
        following = text[match.end():]
        date_match = re.search(r"(?:joining date|join date|شمولیت کی تاریخ)\s+(\d{1,2}\s+[A-Za-z]+(?:\s+\d{4})?|\d{4}-\d{2}-\d{2})", following, re.I)
        extras = {"Joining Date": parse_date(date_match.group(1), now)} if date_match else {}
        registration_match = re.search(r"(?:registration date|register date)\s+(\d{1,2}\s+[A-Za-z]+(?:\s+\d{4})?|\d{4}-\d{2}-\d{2})", following, re.I)
        registration_date = parse_date(registration_match.group(1), now) if registration_match else now.date().isoformat()
        entries.append(Entry(name, settings.field_aliases[match.group().casefold()], registration_date, extras))
        preceding = match.end()
    if entries:
        announced = re.search(r"\b(\d+)\s+(?:students?|log|افراد|طلبہ)\b", low)
        if announced and int(announced.group(1)) != len(entries):
            return Interpretation("unknown", reason=f"Message mein {announced.group(1)} students bole gaye, lekin {len(entries)} names samajh aaye. Dobara clear details bhejein.")
        return Interpretation("entry", entries=entries)
    return Interpretation("unknown", reason="Message samajh nahin aaya. Misal: 'Bilal web development, Sara data science'.")
