from __future__ import annotations

import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group
from django.http import Http404
from django.shortcuts import redirect, render

from hrbot.config import load_settings
from hrbot.interpret import Entry
from hrbot.sheets import sync
from hrbot.storage import Store

from .forms import RegistrationForm, TeamMemberForm


def _can_edit(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name="HR").exists())


def _is_admin(user):
    return user.is_authenticated and user.is_superuser


@contextmanager
def _store():
    store = Store(load_settings().db_file)
    try:
        yield store
    finally:
        store.close()


def _sync_or_warn(request, store):
    settings = load_settings()
    if settings.sheet_id:
        try:
            sync(store, settings)
        except Exception:
            messages.warning(request, "Saved locally, but Google Sheet sync is pending. Run main.py sync later.")


@login_required
def home(request):
    with _store() as store:
        rows = store.records()
    today = datetime.now(load_settings().timezone).date().isoformat()
    return render(request, "home.html", {
        "total": len(rows), "today_count": sum(row["registration_date"] == today for row in rows),
        "field_count": len({row["field"] for row in rows}), "recent": list(reversed(rows[-6:])),
    })


@login_required
def registrations(request):
    with _store() as store:
        rows = list(reversed(store.records()))
    query = request.GET.get("q", "").strip()[:100]
    if query:
        needle = query.casefold()
        rows = [row for row in rows if any(needle in str(row[key]).casefold() for key in ("name", "field", "supervisor", "registration_date"))]
    return render(request, "registrations.html", {"rows": rows[:200], "query": query, "total_matches": len(rows)})


@user_passes_test(_can_edit, login_url="home")
def registration_new(request):
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        settings = load_settings()
        data = form.cleaned_data
        extras = {"Joining Date": data["joining_date"].isoformat()} if data["joining_date"] else {}
        entry = Entry(data["name"], data["field_name"], data["registration_date"].isoformat(), extras)
        with _store() as store:
            added, updated = store.upsert_entries([entry], settings.supervisors)
            _sync_or_warn(request, store)
        messages.success(request, "Registration added." if added else "Existing registration updated.")
        return redirect("registrations")
    return render(request, "registration_form.html", {"form": form, "title": "New registration"})


@user_passes_test(_can_edit, login_url="home")
def registration_edit(request, record_id: UUID):
    with _store() as store:
        row = next((item for item in store.records() if item["id"] == str(record_id)), None)
    if row is None:
        raise Http404("Registration not found")
    initial = {"name": row["name"], "field_name": row["field"], "registration_date": row["registration_date"],
               "joining_date": row["extras"].get("Joining Date")}
    form = RegistrationForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        extras = dict(row["extras"])
        if data["joining_date"]:
            extras["Joining Date"] = data["joining_date"].isoformat()
        else:
            extras.pop("Joining Date", None)
        entry = Entry(data["name"], data["field_name"], data["registration_date"].isoformat(), extras)
        try:
            with _store() as store:
                if not store.update_record(str(record_id), entry, load_settings().supervisors):
                    raise Http404("Registration not found")
                _sync_or_warn(request, store)
        except sqlite3.IntegrityError:
            form.add_error(None, "A registration with this name, field and date already exists.")
        else:
            messages.success(request, "Registration updated.")
            return redirect("registrations")
    return render(request, "registration_form.html", {"form": form, "title": "Edit registration"})


@login_required
def reports(request):
    with _store() as store:
        rows = store.records()
    by_field = sorted(Counter(row["field"] for row in rows).items())
    by_supervisor = sorted(Counter(row["supervisor"] for row in rows).items())
    return render(request, "reports.html", {"by_field": by_field, "by_supervisor": by_supervisor, "total": len(rows)})


@user_passes_test(_is_admin, login_url="home")
def team(request):
    users = get_user_model().objects.prefetch_related("groups").order_by("username")
    return render(request, "team.html", {"users": users})


@user_passes_test(_is_admin, login_url="home")
def team_new(request):
    form = TeamMemberForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        user = get_user_model().objects.create_user(
            username=data["phone"], email=data["email"], password=data["password1"], first_name=data["name"])
        group, _ = Group.objects.get_or_create(name=data["role"])
        user.groups.add(group)
        messages.success(request, "Team member added. WhatsApp access still needs separate approval in .env.")
        return redirect("team")
    return render(request, "team_form.html", {"form": form})
