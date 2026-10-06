# Roadmap

This roadmap describes the planned features and the quarterly milestones.
All work is tracked in [GitHub Issues](https://github.com/Bahasa-Ibu/baibu-community/issues). Plans may change; the
issues are the current source of truth.

## Feature stages

Features are delivered in stages. Each stage builds on the previous one.

| Stage | Features | Issues | Status |
| --- | --- | --- | --- |
| 0. Skeleton | Docker Compose stack (Django, PostgreSQL, Valkey, Celery worker and beat), email sign-in, profile, append-only consent history, account deletion requests, white-label settings | [#7](https://github.com/Bahasa-Ibu/baibu-community/issues/7) | In progress |
| 1. Submissions | Text submissions and a cleaning pipeline; storage adapters for the local filesystem and S3-compatible object storage | [#13](https://github.com/Bahasa-Ibu/baibu-community/issues/13), [#14](https://github.com/Bahasa-Ibu/baibu-community/issues/14) | Planned |
| 2. Chat and review | Assistant chat with model configuration through LiteLLM; pluggable web search; staff review queue; notifications; translation workflow | [#15](https://github.com/Bahasa-Ibu/baibu-community/issues/15), [#16](https://github.com/Bahasa-Ibu/baibu-community/issues/16), [#17](https://github.com/Bahasa-Ibu/baibu-community/issues/17), [#18](https://github.com/Bahasa-Ibu/baibu-community/issues/18), [#19](https://github.com/Bahasa-Ibu/baibu-community/issues/19) | Planned |
| 3. Extensions | Voice input through a speech-to-text adapter; usage and chat metrics; conversation topic tagging; phone sign-in with one-time codes through a messaging adapter | [#20](https://github.com/Bahasa-Ibu/baibu-community/issues/20), [#21](https://github.com/Bahasa-Ibu/baibu-community/issues/21), [#22](https://github.com/Bahasa-Ibu/baibu-community/issues/22), [#23](https://github.com/Bahasa-Ibu/baibu-community/issues/23) | Planned |

## Milestones

Open-source and community work is grouped into four quarterly milestones.
Feature stages run alongside them.

| Milestone | Focus |
| --- | --- |
| [Q1: Foundation and licensing](https://github.com/Bahasa-Ibu/baibu-community/milestone/1) | Licence, charter, README, documentation site, test plan, code of conduct, pull request workflow, application skeleton |
| [Q2: Contribution and transparency](https://github.com/Bahasa-Ibu/baibu-community/milestone/2) | Public repository, contributing guide, public project board, developer documentation, CI with status badge, 15% test coverage |
| [Q3: Community](https://github.com/Bahasa-Ibu/baibu-community/milestone/3) | 45% test coverage, issue templates, good first issues, public discussion channel, user documentation, governance |
| [Q4: Sustainability](https://github.com/Bahasa-Ibu/baibu-community/milestone/4) | Documentation 1.0, 80% test coverage, Digital Public Goods review |

See [open-source compliance](compliance.md) for the status of each
milestone requirement.

## Bringing features across from the reference deployment

Some features already exist in the production Baibu deployment. Maintainers
bring them across by hand, generalised and in English, in public pull
requests labelled
[`upstream-sync`](https://github.com/Bahasa-Ibu/baibu-community/pulls?q=label%3Aupstream-sync). There is no fixed
schedule.
