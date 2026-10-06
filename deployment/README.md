# Deployment directory

Files here override the platform defaults without changing the code:

- `templates/`: any template with the same path as one in `baibu/templates/`
  replaces it. Replace `pages/privacy.html` and `pages/terms.html` before
  inviting anyone.
- `locale/`: your translations as files (`<code>/LC_MESSAGES/django.po`).
  Translators can also translate and publish on the site, at
  `/translations/`; those translations win where both exist.
- `static/`: your logo and other files.

This directory is empty in the repository. Keep your own deployment directory
in your own repository and point `DEPLOYMENT_DIR` at it.

See the white-label guide:
https://bahasa-ibu.github.io/baibu-community/developer/white-label/
