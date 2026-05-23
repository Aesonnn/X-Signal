from __future__ import annotations

import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import UserDashboard


User = get_user_model()
DASHBOARD_NAME_MAX_LENGTH = 20
FETCH_WINDOW_DAYS_MIN = 7
FETCH_POSTS_PER_ACCOUNT_MIN = 20


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_class = "w-full rounded-md border border-[#EFF3F4] bg-[#FFFFFF] px-3 py-2 text-sm text-[#000000]"
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
            "fetch_window_days": forms.NumberInput(
                attrs={
                    "min": FETCH_WINDOW_DAYS_MIN,
                    "max": 30,
                    "placeholder": "7",
                }
            ),
            "fetch_posts_per_account": forms.NumberInput(
                attrs={
                    "min": FETCH_POSTS_PER_ACCOUNT_MIN,
                    "max": 100,
                    "placeholder": "30",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        self._enforce_name_limit = kwargs.pop("enforce_name_limit", False)
        super().__init__(*args, **kwargs)

        if self._enforce_name_limit:
            self.fields["name"].max_length = DASHBOARD_NAME_MAX_LENGTH
        self.fields["name"].widget.attrs.update(
            {
                "class": "w-full rounded-md border border-[#EFF3F4] bg-[#FFFFFF] px-3 py-2 text-sm text-[#000000]",
                **({"maxlength": str(DASHBOARD_NAME_MAX_LENGTH)} if self._enforce_name_limit else {}),
            }
        )
        self.fields["selected_accounts"].widget.attrs.update(
            {
                "class": "w-full rounded-md border border-[#EFF3F4] bg-[#FFFFFF] px-3 py-2 text-sm text-[#000000]"
            }
        )
        self.fields["x_api_key"].widget.attrs.update(
            {
                "class": "w-full rounded-md border border-[#EFF3F4] bg-[#FFFFFF] px-3 py-2 text-sm text-[#000000]"
            }
        )
        self.fields["fetch_window_days"].widget.attrs.update(
            {
                "class": "w-full rounded-md border border-[#EFF3F4] bg-[#FFFFFF] px-3 py-2 text-sm text-[#000000]",
                "min": str(FETCH_WINDOW_DAYS_MIN),
                "oninput": f"if(this.value!=='' && Number(this.value)<{FETCH_WINDOW_DAYS_MIN})this.value={FETCH_WINDOW_DAYS_MIN};",
            }
        )
        self.fields["fetch_posts_per_account"].widget.attrs.update(
            {
                "class": "w-full rounded-md border border-[#EFF3F4] bg-[#FFFFFF] px-3 py-2 text-sm text-[#000000]",
                "min": str(FETCH_POSTS_PER_ACCOUNT_MIN),
                "oninput": f"if(this.value!=='' && Number(this.value)<{FETCH_POSTS_PER_ACCOUNT_MIN})this.value={FETCH_POSTS_PER_ACCOUNT_MIN};",
            }
        )

    def clean_fetch_window_days(self):
        value = int(self.cleaned_data.get("fetch_window_days") or FETCH_WINDOW_DAYS_MIN)
        return min(max(value, FETCH_WINDOW_DAYS_MIN), 30)

    def clean_name(self):
        value = (self.cleaned_data.get("name") or "").strip()
        if self._enforce_name_limit and len(value) > DASHBOARD_NAME_MAX_LENGTH:
            raise forms.ValidationError(
                f"Dashboard name must be {DASHBOARD_NAME_MAX_LENGTH} characters or fewer."
            )
        return value

    def clean_fetch_posts_per_account(self):
        value = int(self.cleaned_data.get("fetch_posts_per_account") or 30)
        return min(max(value, FETCH_POSTS_PER_ACCOUNT_MIN), 100)

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
