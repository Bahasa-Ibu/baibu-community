# Project Charter

This charter describes what Baibu Community Edition is for, who it serves,
how it is licensed, and how it relates to the wider Baibu project. It is a
living document. Changes are proposed through pull requests like any other
change to the repository.

## Vision

Every community can build digital services in its own language, and can
help shape the language technology that serves it.

## Mission

Provide a free, open-source, self-hostable platform that lets an
organisation:

- collect language contributions from its community, with explicit and
  recorded consent; and
- run an assistant chat for that community in the languages it uses.

The platform is white-label. An organisation can stand up its own
deployment, in its own country and languages, under its own name, without
depending on any proprietary, paid or restricted-licence component.

## Background

Baibu is a platform built by PT Ibu Punya Mimpi in Indonesia. The production
deployment at [baibu.id](https://baibu.id) serves Indonesian mothers in
Indonesian, Javanese and Sundanese. It is run from a separate codebase.

Baibu Community Edition is the open-source version of the platform's core,
generalised so that other organisations can reuse it. Its development is
funded by the UNICEF Venture Fund.

## Scope

### In scope

- A Django web application and the services it needs, packaged with Docker
  Compose: PostgreSQL, Valkey (a BSD-licensed, Redis-compatible
  broker and cache), a Celery worker and Celery beat.
- Accounts: sign-in, profiles, an append-only consent history and account
  deletion requests.
- Text submissions from contributors, with a cleaning pipeline and storage
  on the local filesystem or any S3-compatible object storage.
- An assistant chat. Models are reached through LiteLLM, so each deployment
  brings its own model endpoint.
- Staff tools: a review queue for chats and submissions, usage metrics and
  conversation topic tagging.
- Notifications, a translation workflow, and voice input.
- White-label settings: name, branding, prompts, topics and languages are
  configured per deployment.
- Adapter interfaces for third-party services (search, SMS and messaging,
  email, error reporting, speech-to-text), each with a mock or console
  implementation for development and testing.
- English source strings and the tooling for deployments to add their own
  languages.
- Documentation, tests and a published test coverage report.

### Out of scope

- Hosting a service for other organisations. Each deployment runs and is
  responsible for its own instance, its own data and its own legal
  obligations.
- Adapters for specific commercial vendors. Deployments write the adapters
  they need against the published interfaces.
- Recommending a particular language model or model provider. The project
  makes no model recommendation.
- Languages other than English in this repository. Deployments own their
  translations, prompts and content.
- Content, prompts or branding from the reference deployment.
- Datasets, models or any contributor data. The repository contains code and
  synthetic test fixtures only.

## Community

### Who it is for

- Organisations (non-profits, public bodies, research groups and companies)
  that want to run a language-contribution or assistant-chat platform for a
  community they serve.
- Developers who deploy, adapt or extend the platform.
- Contributors who want to improve the code, documentation, tests or
  translation tooling.

### How to participate

- Read the [contributing guide](https://github.com/Bahasa-Ibu/baibu-community/blob/main/CONTRIBUTING.md) and the
  [code of conduct](https://github.com/Bahasa-Ibu/baibu-community/blob/main/CODE_OF_CONDUCT.md).
- Report bugs and propose features in
  [GitHub Issues](https://github.com/Bahasa-Ibu/baibu-community/issues).
  All planned work is tracked there, grouped into quarterly milestones.
- Send changes as pull requests. Every change, including changes by
  maintainers, lands through a reviewed pull request.
- Report security problems privately, as described in
  [SECURITY.md](https://github.com/Bahasa-Ibu/baibu-community/blob/main/SECURITY.md).

A governance document describing roles and decision-making will be published
in the third quarter of the project. Until then, maintainers at PT Ibu Punya
Mimpi review and merge pull requests and set the roadmap, in public.

## Licence

The code and documentation in this repository are licensed under the
[Apache License, Version 2.0](https://github.com/Bahasa-Ibu/baibu-community/blob/main/LICENSE). PT Ibu Punya Mimpi is the primary
licensor; see [NOTICE](https://github.com/Bahasa-Ibu/baibu-community/blob/main/NOTICE).

### Why a permissive licence

We chose Apache-2.0, a permissive licence, over a copyleft licence such as
the GPL or AGPL. The reasons:

- **Adoption.** The aim is for organisations in other countries to reuse the
  platform. Many of them are NGOs, governments and companies that need to run
  it alongside proprietary systems, or to integrate it with internal tools
  they cannot publish. A permissive licence removes that barrier. A copyleft
  licence, and the AGPL in particular, would lead some of them to not adopt
  it at all.
- **Ecosystem fit.** The platform is built on Python and Django, which are
  themselves permissively licensed, as are most of the libraries we use.
  Apache-2.0 fits that ecosystem without licence-compatibility questions.
- **Patent grant.** Apache-2.0 includes an explicit patent licence from
  contributors and a patent-retaliation clause. This gives adopters more
  legal certainty than shorter permissive licences such as MIT or BSD.
- **Funder and standards requirements.** The funder requires an appropriate
  open licence, and the Digital Public Goods Standard requires an
  OSI-approved licence. Apache-2.0 meets both.

The trade-off is that someone can build a closed product on this code
without sharing their changes. We accept that. We think wider reuse does
more good for the communities this platform is meant to serve than forcing
changes back. We encourage, but do not require, deployments to contribute
improvements upstream.

### Contributions

Contributions are accepted under the same licence, as set out in section 5
of Apache-2.0. We do not ask for a separate contributor licence agreement.

## Trademarks

The Apache licence covers the code. It does not grant rights to trademarks
(section 6 of the licence). The names "Baibu" and "Bahasa Ibu", and their
logos, are not licensed for use by deployments.

- **Do** run your deployment under your own name, logo and branding. The
  platform is white-label by design, and the white-label settings exist for
  this.
- **Do** say that your deployment is "built on Baibu Community Edition", and
  link to this repository.
- **Do not** call your deployment "Baibu" or "Bahasa Ibu", use those names
  as part of your product or domain name, or use their logos.
- **Do not** suggest that PT Ibu Punya Mimpi, the Baibu project or the
  funder operates, endorses or is responsible for your deployment.

If you are unsure whether a use is acceptable, ask at
[contact@baibu.id](mailto:contact@baibu.id).

## Relationship to the reference deployment

The production Baibu deployment is the reference deployment. It is run by PT
Ibu Punya Mimpi from a separate, private codebase that includes
deployment-specific content, languages, vendor integrations and
configuration.

- This repository does not depend on the reference deployment, and the
  reference deployment is not a required part of running the Community
  Edition.
- From time to time, maintainers bring core features across from the
  reference deployment by hand. They do this in public pull requests
  labelled `upstream-sync`, reviewed like any other change. There is no
  fixed sync schedule.
- Changes made here may also be adopted by the reference deployment.
- Nothing from the reference deployment's content, prompts, branding or
  data is brought into this repository.

## Funding

Development of Baibu Community Edition is supported by the UNICEF Venture
Fund. The funder does not operate or endorse any particular deployment.

## Contacts

- General questions, trademark questions and code of conduct reports:
  [contact@baibu.id](mailto:contact@baibu.id)
- Security vulnerabilities: [contact@baibu.id](mailto:contact@baibu.id),
  following [SECURITY.md](https://github.com/Bahasa-Ibu/baibu-community/blob/main/SECURITY.md)
- Bugs and feature requests:
  [GitHub Issues](https://github.com/Bahasa-Ibu/baibu-community/issues)
