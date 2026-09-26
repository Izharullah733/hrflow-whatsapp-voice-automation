from __future__ import annotations

import re
from datetime import date

from django import forms
from django.contrib.auth import get_user_model, password_validation

from hrbot.config import load_settings


class RegistrationForm(forms.Form):
    name = forms.CharField(max_length=100, label="Student name")
    field_name = forms.ChoiceField(label="Field")
    registration_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), initial=date.today)
    joining_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["field_name"].choices = [(field, field) for field in load_settings().supervisors]

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if len(name) < 2:
            raise forms.ValidationError("Please enter a clear name.")
        return name


class TeamMemberForm(forms.Form):
    name = forms.CharField(max_length=100, label="Team member name")
    phone = forms.CharField(max_length=16, label="WhatsApp phone (international digits)")
    email = forms.EmailField(required=False)
    role = forms.ChoiceField(choices=[("HR", "HR — add and edit"), ("Viewer", "Viewer — read only")])
    password1 = forms.CharField(widget=forms.PasswordInput, label="Temporary password")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    def clean_phone(self):
        phone = re.sub(r"[\s+()-]", "", self.cleaned_data["phone"])
        if not re.fullmatch(r"[1-9]\d{8,14}", phone):
            raise forms.ValidationError("Use 9–15 digits with country code, e.g. 923001234567.")
        if get_user_model().objects.filter(username=phone).exists():
            raise forms.ValidationError("This phone is already registered.")
        return phone

    def clean(self):
        data = super().clean()
        if data.get("password1") and data.get("password2"):
            if data["password1"] != data["password2"]:
                self.add_error("password2", "Passwords do not match.")
            else:
                password_validation.validate_password(data["password1"])
        return data
