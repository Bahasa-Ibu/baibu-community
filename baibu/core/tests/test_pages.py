import pytest
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("name", ["home", "privacy", "terms"])
def test_public_pages_render_with_platform_name(client, settings, name):
    settings.PLATFORM_NAME = "Lugha Yetu"
    response = client.get(reverse(name))
    assert response.status_code == 200
    assert "Lugha Yetu" in response.text


def test_brand_colour_is_injected(client, settings):
    settings.PLATFORM_BRAND_COLOR = "#7c3aed"
    assert "--color-brand: #7c3aed" in client.get(reverse("home")).text


def test_deployment_template_overrides_default(client, settings, tmp_path):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "privacy.html").write_text("Our own privacy notice")
    settings.TEMPLATES = [
        {**settings.TEMPLATES[0], "DIRS": [str(tmp_path), *settings.TEMPLATES[0]["DIRS"]]},
    ]
    assert client.get(reverse("privacy")).text == "Our own privacy notice"


def test_signed_in_home_links_to_account(client, user):
    client.force_login(user)
    assert reverse("users:account") in client.get(reverse("home")).text


def test_language_switcher_hidden_for_single_language(client):
    assert "language-switcher" not in client.get(reverse("home")).text


def test_migrate_syncs_site_from_settings(settings):
    settings.PLATFORM_NAME = "Lugha Yetu"
    settings.PLATFORM_DOMAIN = "lugha.example.org"
    call_command("migrate", verbosity=0)
    site = Site.objects.get(id=settings.SITE_ID)
    assert (site.name, site.domain) == ("Lugha Yetu", "lugha.example.org")


def test_404_page_renders(client):
    response = client.get("/no-such-page/")
    assert response.status_code == 404
