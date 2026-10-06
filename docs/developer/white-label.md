# White-label deployments

The platform has no fixed name, look or language. A deployment sets its own
through environment variables and a deployment directory, without changing
the code. That keeps your deployment easy to upgrade: pull the new version
and your files still apply.

## 1. Name, contact and colour

Set these in your environment (see the [configuration reference](configuration.md)):

```sh
PLATFORM_NAME="Lugha Yetu"
PLATFORM_TAGLINE="Share Swahili, with consent, and help build tools that speak it."
PLATFORM_CONTACT_EMAIL=hello@lugha.example.org
PLATFORM_DOMAIN=lugha.example.org
PLATFORM_BRAND_COLOR="#b45309"
```

The brand colour applies at once; you do not need to rebuild the stylesheet.
The name and domain are copied to the Site record on every `migrate`, so
emails from the sign-in system use them too.

## 2. Logo and other files

Put files in `deployment/static/` and point to them:

```sh
# deployment/static/images/lugha-logo.svg
PLATFORM_LOGO_PATH=images/lugha-logo.svg
```

Files in `deployment/static/` take precedence over the defaults with the same
path.

## 3. Pages and wording

Every template can be overridden by a file with the same path under
`deployment/templates/`. You **must** replace the two placeholder pages
before inviting anyone:

- `deployment/templates/pages/privacy.html`: your privacy notice;
- `deployment/templates/pages/terms.html`: your terms of use.

Start from the default file in `baibu/templates/` and keep its
`{% extends "base.html" %}` line. Other common overrides are
`pages/home.html` and `includes/footer.html`.

When you change the consent wording or your privacy notice, raise
`CONSENT_TEXT_VERSION`. Each consent decision stores the version the person
saw.

## 4. Languages

The code and templates are written in English. To offer more languages:

1. List them: `PLATFORM_LANGUAGES=sw,en` and `PLATFORM_DEFAULT_LANGUAGE=sw`.
2. If Django does not know a language, declare it:
   `PLATFORM_EXTRA_LANGUAGES="jv:Javanese:Basa Jawa;su:Sundanese:Basa Sunda"`.
3. Create the translation files. They are written to
   `deployment/locale/<code>/LC_MESSAGES/django.po`:

    ```sh
    docker compose run --rm django python manage.py makemessages -l sw \
      --ignore .venv --ignore node_modules --ignore docs
    ```

4. Translate the `.po` file (any PO editor works), then compile it:

    ```sh
    docker compose run --rm django python manage.py compilemessages --ignore .venv
    ```

The default language has no URL prefix; the others get one (`/en/...`). When
more than one language is enabled, a language switcher appears in the header.

## 5. Keep your deployment directory separate

`deployment/` in this repository holds only empty placeholders. Keep your own
deployment directory in your own repository and point `DEPLOYMENT_DIR` at it
(for example by mounting it into the containers), so upgrades never touch it.

## Trademarks

The Baibu name and logo are not part of the licence. Use your own name and
logo. You may say your platform is "built on Baibu Community Edition". See
the [project charter](../project/charter.md).
