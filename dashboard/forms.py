from __future__ import annotations

import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import UserDashboard


User = get_user_model()


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = "w-full rounded-md border border-[#2F3336] bg-[#050505] px-3 py-2 text-sm text-[#E7E9EA]"
        for name in ("username", "email", "password1", "password2"):
            self.fields[name].widget.attrs.update({"class": field_class})


class UserDashboardForm(forms.ModelForm):
    class Meta:
        model = UserDashboard
        fields = ("name", "selected_accounts", "x_api_key", "fetch_window_days", "fetch_posts_per_account")
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. US Politics Watch"}),
            "selected_accounts": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "One per line: account|L or account|C (e.g. nytimes|L)",
                }
            ),
            "x_api_key": forms.PasswordInput(render_value=False),
            "fetch_window_days": forms.NumberInput(attrs={"min": 1, "max": 30, "placeholder": "7"}),
            "fetch_posts_per_account": forms.NumberInput(attrs={"min": 5, "max": 100, "placeholder": "30"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs.update(
            {
                "class": "w-full rounded-md border border-[#2F3336] bg-[#050505] px-3 py-2 text-sm text-[#E7E9EA]"
            }
        )
        self.fields["selected_accounts"].widget.attrs.update(
            {
                "class": "w-full rounded-md border border-[#2F3336] bg-[#050505] px-3 py-2 text-sm text-[#E7E9EA]"
            }
        )
        self.fields["x_api_key"].widget.attrs.update(
            {
                "class": "w-full rounded-md border border-[#2F3336] bg-[#050505] px-3 py-2 text-sm text-[#E7E9EA]"
            }
        )
        self.fields["fetch_window_days"].widget.attrs.update(
            {
                "class": "w-full rounded-md border border-[#2F3336] bg-[#050505] px-3 py-2 text-sm text-[#E7E9EA]"
            }
        )
        self.fields["fetch_posts_per_account"].widget.attrs.update(
            {
                "class": "w-full rounded-md border border-[#2F3336] bg-[#050505] px-3 py-2 text-sm text-[#E7E9EA]"
            }
        )

    def clean_fetch_window_days(self):
        value = int(self.cleaned_data.get("fetch_window_days") or 7)
        return min(max(value, 1), 30)

    def clean_fetch_posts_per_account(self):
        value = int(self.cleaned_data.get("fetch_posts_per_account") or 30)
        return min(max(value, 5), 100)

    def clean_selected_accounts(self):
        raw = (self.cleaned_data.get("selected_accounts") or "").strip()
        if not raw:
            return raw

        entries = [part.strip() for part in re.split(r"[\n,]+", raw) if part.strip()]
        normalized_entries: list[str] = []

        for entry in entries:
            if "|" in entry:
                account, aff = [part.strip() for part in entry.split("|", 1)]
            elif ":" in entry:
                account, aff = [part.strip() for part in entry.split(":", 1)]
            else:
                raise forms.ValidationError(
                    f"Invalid entry '{entry}'. Use 'account|L' or 'account|C'."
                )

            account = account.lstrip("@").strip()
            aff_norm = aff.upper()
            if not account:
                raise forms.ValidationError("Account value cannot be empty.")
            if aff_norm not in {"L", "C"}:
                raise forms.ValidationError(
                    f"Invalid affiliation '{aff}' for '{account}'. Use L or C."
                )

            normalized_entries.append(f"{account}|{aff_norm}")

        return "\n".join(normalized_entries)
