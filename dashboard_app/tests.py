from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from hrbot.config import load_settings
from hrbot.storage import Store


class DashboardTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bot_settings = replace(load_settings(), db_file=Path(self.temp.name) / "bot.sqlite3", sheet_id="")
        mocked = patch("dashboard_app.views.load_settings", return_value=self.bot_settings)
        mocked.start()
        self.addCleanup(mocked.stop)
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser("admin", "admin@example.com", "StrongAdminPass123!")
        self.hr = user_model.objects.create_user("923001111111", password="StrongHrPass123!")
        self.viewer = user_model.objects.create_user("923002222222", password="StrongViewerPass123!")
        hr_group, _ = Group.objects.get_or_create(name="HR")
        viewer_group, _ = Group.objects.get_or_create(name="Viewer")
        self.hr.groups.add(hr_group)
        self.viewer.groups.add(viewer_group)

    def test_login_required(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_hr_can_add_and_viewer_cannot_edit(self):
        payload = {"name": "Ali", "field_name": "Web Development", "registration_date": "2026-09-26"}
        self.client.force_login(self.hr)
        self.assertEqual(self.client.post(reverse("registration_new"), payload).status_code, 302)
        store = Store(self.bot_settings.db_file)
        try:
            self.assertEqual(len(store.records()), 1)
        finally:
            store.close()
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.post(reverse("registration_new"), payload).status_code, 302)
        self.assertContains(self.client.get(reverse("reports")), "Web Development")
        store = Store(self.bot_settings.db_file)
        try:
            self.assertEqual(len(store.records()), 1)
        finally:
            store.close()

    def test_team_is_admin_only(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("team")).status_code, 302)
        self.client.force_login(self.admin)
        response = self.client.post(reverse("team_new"), {
            "name": "Fatima", "phone": "+923003333333", "email": "fatima@example.com", "role": "HR",
            "password1": "StrongTeamPass123!", "password2": "StrongTeamPass123!",
        })
        self.assertEqual(response.status_code, 302)
        member = get_user_model().objects.get(username="923003333333")
        self.assertTrue(member.groups.filter(name="HR").exists())
