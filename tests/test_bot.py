from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from hrbot.config import load_settings
from hrbot.interpret import interpret
from hrbot.reports import answer
from hrbot.storage import Store


class BotLanguageTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = replace(load_settings(), db_file=Path(self.temp.name) / "bot.sqlite3", sheet_id="")
        self.now = datetime(2026, 9, 26, 12, 0, tzinfo=self.settings.timezone)

    def test_urdu_count_query(self):
        parsed = interpret("آج کتنی رجسٹریشن ہوئی؟", self.settings, self.now)
        self.assertEqual(parsed.kind, "query")
        store = Store(self.settings.db_file)
        try:
            self.assertIn("0", answer(parsed.question, store, self.settings, self.now))
        finally:
            store.close()

    def test_urdu_field_registration(self):
        parsed = interpret("علی ویب ڈویلپمنٹ", self.settings, self.now)
        self.assertEqual(parsed.kind, "entry")
        self.assertEqual(parsed.entries[0].name, "علی")
        self.assertEqual(parsed.entries[0].field_name, "Web Development")

    def test_repeat_registration_is_update(self):
        parsed = interpret("Ali web development", self.settings, self.now)
        self.assertEqual(parsed.kind, "entry")
        store = Store(self.settings.db_file)
        try:
            self.assertEqual(store.upsert_entries(parsed.entries, self.settings.supervisors), (1, 0))
            self.assertEqual(store.upsert_entries(parsed.entries, self.settings.supervisors), (0, 1))
            self.assertEqual(len(store.records()), 1)
        finally:
            store.close()
