# Contributing to Baibu Community Edition

Thank you for your interest in contributing. This guide explains how to set
up a development environment, how we work, and what we expect in a pull
request.

By taking part you agree to follow the
[code of conduct](https://github.com/Bahasa-Ibu/baibu-community/blob/main/CODE_OF_CONDUCT.md).

The project is at an early stage: the application skeleton runs and feature
stages follow, so expect larger changes until a 1.0 release.

## Ways to contribute

- Report a bug or propose a feature in
  [GitHub Issues](https://github.com/Bahasa-Ibu/baibu-community/issues).
- Pick up an open issue. Issues labelled `good first issue` are a good place
  to start. Comment on the issue before you start, so that work is not
  duplicated.
- Improve the documentation. Documentation changes follow the same process
  as code changes.

Report security problems privately to
[contact@baibu.id](mailto:contact@baibu.id), as described in
[SECURITY.md](https://github.com/Bahasa-Ibu/baibu-community/blob/main/SECURITY.md).
Do not open a public issue for a security problem.

## Development setup

You need Git and Docker with Docker Compose. Everything else runs in
containers.

```sh
git clone https://github.com/Bahasa-Ibu/baibu-community.git
cd baibu-community
cp .env.example .env
docker compose up --build        # app on http://localhost:8000
docker compose run --rm django python manage.py createsuperuser
```

If you plan to send a pull request, fork the repository on GitHub first and
clone your fork instead.

### Project layout

- `baibu/`: the Python package. Django apps live here: `users`, `core` and
  `theme` now; `submissions`, `chat`, `staff`, `notifications`,
  `localization` and `analytics` as later stages land.
- `config/settings/`: Django settings, split into `base`, `local`, `test`
  and `production`.
- `docs/`: the documentation site source (MkDocs).

### Language models and third-party services

Tests and local development do not need a model endpoint or any external
account. LLM calls are mocked in tests. Third-party services (search, SMS
and messaging, email, error reporting, speech-to-text) use mock or console
adapters by default. Do not add a dependency on a proprietary, paid or
restricted-licence service. If you need a vendor integration for your own
deployment, write an adapter against the published interface in your
deployment. This repository ships mock and console adapters only.

## Tests, coverage and lint

```sh
docker compose run --rm django pytest
docker compose run --rm django coverage run -m pytest && docker compose run --rm django coverage report
docker compose run --rm django ruff check .
```

Tests use pytest, pytest-django and factory-boy. The
[test plan](https://bahasa-ibu.github.io/baibu-community/qa/test-plan/)
describes the testing strategy, coverage targets and sample test cases.

Rules:

- New features and bug fixes come with tests. A bug fix should include a
  test that fails without the fix.
- A pull request must not lower total test coverage.
- `ruff check .` must pass.
- Tests must not make network calls. Mock LLM calls and use the mock
  adapters for other services.

## Data rule

Never commit real personal data or real contributor text. This includes
names, email addresses, phone numbers, chat transcripts, submissions and
anything copied from a running deployment, even if it seems harmless or
anonymised.

Use synthetic fixtures: factory-boy factories, or short text you wrote
yourself for the test. Do not commit secrets, API keys or `.env` files
either.

If you commit personal data or a secret by mistake, do not try to hide it
with a follow-up commit. Email [contact@baibu.id](mailto:contact@baibu.id)
so maintainers can remove it from history and rotate any exposed
credentials.

## Branches and commits

Create a branch from `main` named for the kind of change and the issue:

| Prefix | Use for | Example |
| --- | --- | --- |
| `feat/` | New features | `feat/13-submission-cleaning` |
| `fix/` | Bug fixes | `fix/42-consent-timestamp` |
| `docs/` | Documentation only | `docs/8-contributing-guide` |
| `chore/` | Tooling, CI, dependencies | `chore/9-ci-workflow` |
| `sync/` | `upstream-sync` changes | `sync/chat-run-retry` |

Commit messages:

- Use the imperative mood in a short first line, ideally under 72
  characters: "Add consent history model", not "Added" or "Adds".
- Reference the issue in the first line or the body: "Add consent history
  model (#7)".
- Explain why in the body when the reason is not obvious from the change.

Pull requests are squash-merged, so the pull request title becomes the
commit on `main`. Write it in the same style.

## Pull request process

1. Make sure an issue exists for the change. For small fixes such as typos
   you can skip this.
2. Create a branch, make your change, and add or update tests and
   documentation.
3. Run tests and lint locally.
4. Open a pull request against `main`. Fill in the pull request template and
   link the issue with `Closes #<number>`.
5. CI must pass.
6. One maintainer reviews and approves. Address review comments by pushing
   more commits to the branch.
7. A maintainer squash-merges the pull request.

`main` is protected. All changes, including changes by maintainers, land
through a pull request.

## Documentation

Update the documentation in the same pull request as the change it
describes. The documentation site is built from `docs/` with MkDocs. To
preview it locally:

```sh
pip install -r docs/requirements.txt
mkdocs serve
```

With [uv](https://docs.astral.sh/uv/), you can run
`uvx --with mkdocs-material mkdocs serve` instead. Before you push, check
that `mkdocs build --strict` passes.

## Translations

The repository contains English source strings only.

- Write user-facing strings in plain English.
- Mark every user-facing string for translation: `gettext` /
  `gettext_lazy` in Python, `{% translate %}` or `{% blocktranslate %}` in
  templates.
- Do not add translations for other languages to this repository.
  Deployments own their languages, translations, prompts and content.

Improvements to the translation tooling itself are welcome.

## `upstream-sync` pull requests

Maintainers occasionally bring core features across from the reference
deployment by hand. These pull requests:

- carry the `upstream-sync` label;
- go through the same review, tests and CI as any other change;
- contain only general-purpose code, with English strings and no
  deployment-specific content, branding, prompts, vendor integrations or
  data;
- record the change in `SYNC.md`.

## Labels

| Label | Meaning |
| --- | --- |
| `bug`, `enhancement`, `documentation` | Type of issue |
| `good first issue` | Suitable for a first contribution |
| `compliance` | Required by the project's open-source commitments to its funder |
| `upstream-sync` | Brought across from the reference deployment |
| `area: users`, `area: submissions`, `area: chat`, `area: staff`, `area: localization`, `area: infra`, `area: docs` | Part of the system affected |

## Licence

By contributing, you agree that your contributions are licensed under the
[Apache License 2.0](https://github.com/Bahasa-Ibu/baibu-community/blob/main/LICENSE),
as set out in section 5 of the licence.
