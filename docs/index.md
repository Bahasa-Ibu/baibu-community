# Baibu Community Edition

Baibu Community Edition is an open-source, self-hostable, white-label
platform for collecting community language contributions and running an
assistant chat in local languages.

An organisation can use it to stand up its own platform, in its own country
and languages, under its own name. The platform ships in English. Each
deployment adds its own languages, branding, prompts and topics.

!!! note "Status: early"
    The application skeleton runs (accounts, consent, deletion requests,
    white-label settings, on Docker Compose with tests). Feature stages
    follow. Expect breaking changes until a 1.0 release. See the [roadmap](project/roadmap.md).

## What it does

When the planned stages are complete, a deployment will be able to:

- let people sign up, manage their profile and give or withdraw consent,
  with every consent change kept in an append-only history;
- accept text contributions, clean them and store them on the local
  filesystem or in S3-compatible object storage;
- run an assistant chat in the deployment's languages, using any model
  endpoint the deployment chooses;
- give staff a review queue for chats and submissions, usage metrics and
  conversation topic tagging;
- handle account deletion requests.

## Built on open components

- Django 5.2 on Python 3.14
- PostgreSQL
- Valkey, a BSD-licensed, Redis-compatible broker and cache
- Celery worker and Celery beat
- Local filesystem or any S3-compatible object storage
- [LiteLLM](https://github.com/BerriAI/litellm) to reach the language model
  endpoint of the deployment's choice. The project makes no model
  recommendation.
- Docker Compose to run it all

Search, SMS and messaging, email, error reporting and speech-to-text sit
behind adapter interfaces. The project ships mock or console
implementations only. Deployments add adapters for the vendors they use.

## Where to go next

- [Getting started](getting-started.md): run the platform locally.
- [Test plan](qa/test-plan.md): how the project is tested.
- [Contributing](community/contributing.md): how to take part.
- [Project charter](project/charter.md): scope, licence and trademarks.
- [Roadmap](project/roadmap.md): planned stages and milestones.

## About the project

Baibu is a platform built by PT Ibu Punya Mimpi in Indonesia. Its production
deployment, [baibu.id](https://baibu.id), serves Indonesian mothers in
Indonesian, Javanese and Sundanese. The Community Edition is the
open-source, reusable core of that platform. Its development is supported by
the UNICEF Venture Fund.

The code is licensed under the
[Apache License 2.0](https://github.com/Bahasa-Ibu/baibu-community/blob/main/LICENSE).
The "Baibu" and "Bahasa Ibu" names and logos are not licensed; deployments
use their own name and branding. See
[trademarks](project/charter.md#trademarks).
