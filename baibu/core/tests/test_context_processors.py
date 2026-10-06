import pytest
from django.test import RequestFactory

from baibu.core.context_processors import platform


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("#7c3aed", "#7c3aed"),
        ("rebeccapurple", "rebeccapurple"),
        ("oklch(0.6 0.2 300)", "oklch(0.6 0.2 300)"),
        ("red;}</style><script>", ""),
        ("", ""),
    ],
)
def test_brand_color_only_passes_plain_colours(settings, configured, expected):
    settings.PLATFORM_BRAND_COLOR = configured
    context = platform(RequestFactory().get("/"))
    assert context["platform"]["brand_color"] == expected


def test_platform_settings_reach_templates(settings):
    settings.PLATFORM_NAME = "Lugha Yetu"
    settings.PLATFORM_CONTACT_EMAIL = "hello@example.org"
    context = platform(RequestFactory().get("/"))["platform"]
    assert context["name"] == "Lugha Yetu"
    assert context["contact_email"] == "hello@example.org"
