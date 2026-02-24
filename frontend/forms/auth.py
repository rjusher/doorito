"""
Authentication forms for the frontend app.
"""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

User = get_user_model()

INPUT_CLASS = (
    "w-full px-3 py-2 border border-neutral-300 rounded-lg text-sm "
    "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 "
    "placeholder-neutral-400"
)
ERROR_INPUT_CLASS = (
    "w-full px-3 py-2 border border-danger-500 rounded-lg text-sm "
    "focus:ring-2 focus:ring-danger-500 focus:border-danger-500 "
    "placeholder-neutral-400"
)


class FrontendLoginForm(AuthenticationForm):
    """Login form with Tailwind styling and remember-me option."""

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": INPUT_CLASS,
                "placeholder": "you@example.com",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": INPUT_CLASS,
                "placeholder": "Enter your password",
            }
        ),
    )
    remember_me = forms.BooleanField(
        required=False,
        initial=False,
        label="Remember me",
        widget=forms.CheckboxInput(
            attrs={"class": "rounded border-neutral-300 text-primary-600"}
        ),
    )

    def clean(self):
        # Resolve email to username so ModelBackend can authenticate.
        email = self.cleaned_data.get("username")
        if email:
            try:
                user = User.objects.get(email=email)
                self.cleaned_data["username"] = user.username
            except User.DoesNotExist:
                pass  # Let parent handle the invalid-credentials error
        return super().clean()


class FrontendRegisterForm(UserCreationForm):
    """Registration form with Tailwind styling."""

    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": INPUT_CLASS,
                "placeholder": "you@example.com",
                "autofocus": True,
            }
        ),
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": INPUT_CLASS,
                "placeholder": "Create a password",
            }
        ),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(
            attrs={
                "class": INPUT_CLASS,
                "placeholder": "Confirm your password",
            }
        ),
    )

    class Meta:
        model = User
        fields = ("email",)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user
