from django.conf import settings


def sync_site_from_settings(**kwargs) -> None:
    """Keep the Site record (used in allauth emails) in line with the platform settings.

    Runs after every ``migrate``, so changing PLATFORM_NAME or PLATFORM_DOMAIN
    and redeploying is enough.
    """
    from django.contrib.sites.models import Site

    Site.objects.update_or_create(
        id=settings.SITE_ID,
        defaults={"domain": settings.PLATFORM_DOMAIN, "name": settings.PLATFORM_NAME},
    )
