# Deployment directory

Files here override the platform defaults without changing the code:

- `templates/`: any template with the same path as one in `baibu/templates/`
  replaces it. Replace `pages/privacy.html` and `pages/terms.html` before
  inviting anyone.
- `locale/`: your translations (`<code>/LC_MESSAGES/django.po`).
- `static/`: your logo and other files.

This directory is empty in the repository. Keep your own deployment directory
in your own repository and point `DEPLOYMENT_DIR` at it.

See the white-label guide:
https://bahasa-ibu.github.io/baibu-community/developer/white-label/
