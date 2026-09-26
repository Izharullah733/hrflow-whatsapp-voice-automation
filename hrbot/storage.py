"""SQLite is the durable source of truth; Google Sheets is a synchronized view."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from .interpret import Entry


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                name_key TEXT NOT NULL,
                field TEXT NOT NULL,
                field_key TEXT NOT NULL,
                supervisor TEXT NOT NULL,
                registration_date TEXT NOT NULL,
                extras_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                UNIQUE(name_key, field_key, registration_date)
            );
            CREATE TABLE IF NOT EXISTS compensation (
                name_key TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('salary','commission')),
                amount INTEGER NOT NULL CHECK(amount >= 0),
                updated_at TEXT NOT NULL,
                PRIMARY KEY(name_key, type)
            );
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id TEXT PRIMARY KEY,
                reply TEXT NOT NULL,
                processed_at TEXT NOT NULL,
                sent INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS initialized_chats (
                phone TEXT PRIMARY KEY,
                initialized_at TEXT NOT NULL
            );
        """)

    @staticmethod
    def key(value: str) -> str:
        return " ".join(value.casefold().split())

    def previous_reply(self, message_id: str) -> str | None:
        row = self.connection.execute("SELECT reply FROM processed_messages WHERE message_id=?", (message_id,)).fetchone()
        return row["reply"] if row else None

    def save_reply(self, message_id: str, reply: str) -> None:
        with self.connection:
            self.connection.execute("INSERT OR IGNORE INTO processed_messages(message_id,reply,processed_at) VALUES (?,?,?)", (message_id, reply, datetime.now().isoformat()))

    def is_sent(self, message_id: str) -> bool:
        row = self.connection.execute("SELECT sent FROM processed_messages WHERE message_id=?", (message_id,)).fetchone()
        return bool(row and row["sent"])

    def mark_sent(self, message_id: str) -> None:
        with self.connection:
            self.connection.execute("UPDATE processed_messages SET sent=1 WHERE message_id=?", (message_id,))

    def mark_existing(self, message_id: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO processed_messages(message_id,reply,processed_at,sent) VALUES (?,?,?,1)",
                (message_id, "", datetime.now().isoformat()),
            )

    def chat_initialized(self, phone: str) -> bool:
        return self.connection.execute("SELECT 1 FROM initialized_chats WHERE phone=?", (phone,)).fetchone() is not None

    def mark_chat_initialized(self, phone: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO initialized_chats VALUES (?,?)",
                (phone, datetime.now().isoformat()),
            )

    def upsert_entries(self, entries: list[Entry], supervisors: dict[str, str]) -> tuple[int, int]:
        added = updated = 0
        with self.connection:
            for entry in entries:
                name_key, field_key = self.key(entry.name), self.key(entry.field_name)
                row = self.connection.execute(
                    "SELECT id, extras_json FROM records WHERE name_key=? AND field_key=? AND registration_date=?",
                    (name_key, field_key, entry.registration_date),
                ).fetchone()
                supervisor = supervisors.get(entry.field_name, "Unassigned")
                if row:
                    extras = json.loads(row["extras_json"])
                    extras.update(entry.extras)
                    self.connection.execute(
                        "UPDATE records SET name=?, field=?, supervisor=?, extras_json=? WHERE id=?",
                        (entry.name, entry.field_name, supervisor, json.dumps(extras, ensure_ascii=False), row["id"]),
                    )
                    updated += 1
                else:
                    self.connection.execute(
                        "INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?)",
                        (str(uuid.uuid4()), entry.name, name_key, entry.field_name, field_key,
                         supervisor, entry.registration_date, json.dumps(entry.extras, ensure_ascii=False), datetime.now().isoformat()),
                    )
                    added += 1
        return added, updated

    def set_compensation(self, name: str, kind: str, amount: int) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO compensation VALUES (?,?,?,?,?) ON CONFLICT(name_key,type) DO UPDATE SET name=excluded.name, amount=excluded.amount, updated_at=excluded.updated_at",
                (self.key(name), name, kind, amount, datetime.now().isoformat()),
            )

    def records(self) -> list[dict]:
        rows = self.connection.execute("SELECT * FROM records ORDER BY created_at, id").fetchall()
        return [{**dict(row), "extras": json.loads(row["extras_json"])} for row in rows]

    def update_record(self, record_id: str, entry: Entry, supervisors: dict[str, str]) -> bool:
        """Correct an existing registration without creating a new row."""
        with self.connection:
            cursor = self.connection.execute(
                """UPDATE records SET name=?,name_key=?,field=?,field_key=?,supervisor=?,
                   registration_date=?,extras_json=? WHERE id=?""",
                (entry.name, self.key(entry.name), entry.field_name, self.key(entry.field_name),
                 supervisors.get(entry.field_name, "Unassigned"), entry.registration_date,
                 json.dumps(entry.extras, ensure_ascii=False), record_id),
            )
        return cursor.rowcount == 1

    def compensation(self, name: str, kind: str) -> int | None:
        row = self.connection.execute("SELECT amount FROM compensation WHERE name_key=? AND type=?", (self.key(name), kind)).fetchone()
        return row["amount"] if row else None

    def names_for_compensation(self, kind: str) -> list[str]:
        return [row["name"] for row in self.connection.execute("SELECT name FROM compensation WHERE type=?", (kind,))]

    def close(self) -> None:
        self.connection.close()
