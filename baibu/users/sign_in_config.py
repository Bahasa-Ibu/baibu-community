"""Build django-allauth's sign-in settings from the environment.

Kept free of Django imports so the settings module can call it. Phone
sign-in adds "phone" as a sign-in method and a phone field at sign-up;
email stays required either way.
"""


def login_methods(*, phone: bool) -> set[str]:
    return {"email", "phone"} if phone else {"email"}


def signup_fields(*, phone: bool, phone_required: bool) -> list[str]:
    fields = ["email*", "password1*", "password2*"]
    if phone:
        fields.insert(1, "phone*" if phone_required else "phone")
    return fields
