import re

from django.conf import settings

# Only plain colour values reach the inline style in base.html.
_SAFE_COLOR = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]+|(rgb|hsl|oklch)a?\([0-9.,%\s/]+\))$")


def platform(request):
    brand_color = (settings.PLATFORM_BRAND_COLOR or "").strip()
    return {
        "platform": {
            "name": settings.PLATFORM_NAME,
            "tagline": settings.PLATFORM_TAGLINE,
            "contact_email": settings.PLATFORM_CONTACT_EMAIL,
            "logo_path": settings.PLATFORM_LOGO_PATH,
            "brand_color": brand_color if _SAFE_COLOR.match(brand_color) else "",
            "languages": settings.LANGUAGES,
            "allow_registration": settings.ACCOUNT_ALLOW_REGISTRATION,
        },
    }
