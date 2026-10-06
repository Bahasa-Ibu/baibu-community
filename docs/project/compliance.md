# Open-source compliance

The project's funder sets open-source requirements for each quarter. This
page lists them, their status and where each one is met. Each requirement
is tracked as an issue with the `compliance` label
([all compliance issues](https://github.com/Bahasa-Ibu/baibu-community/issues?q=label%3Acompliance)).

Status values:

- **Done**: met, with the evidence linked.
- **In progress**: work has started.
- **Planned**: not started.

This page is updated in the pull request that changes a requirement's
status.

## Q1: Foundation and licensing

[Milestone](https://github.com/Bahasa-Ibu/baibu-community/milestone/1)

| Requirement | Status | Where it is met | Issue |
| --- | --- | --- | --- |
| Open-source licence | Done | [LICENSE](https://github.com/Bahasa-Ibu/baibu-community/blob/main/LICENSE) (Apache-2.0), [NOTICE](https://github.com/Bahasa-Ibu/baibu-community/blob/main/NOTICE), rationale in the [charter](charter.md#licence) | |
| Project charter | Done | [PROJECT_CHARTER.md](https://github.com/Bahasa-Ibu/baibu-community/blob/main/PROJECT_CHARTER.md), [charter page](charter.md) | [#1](https://github.com/Bahasa-Ibu/baibu-community/issues/1) |
| README | Done | [README.md](https://github.com/Bahasa-Ibu/baibu-community/blob/main/README.md) | [#2](https://github.com/Bahasa-Ibu/baibu-community/issues/2) |
| Public documentation site | Done | This site, built with MkDocs from [docs/](https://github.com/Bahasa-Ibu/baibu-community/tree/main/docs) and deployed to GitHub Pages on every merge to `main` by the [docs workflow](https://github.com/Bahasa-Ibu/baibu-community/blob/main/.github/workflows/docs.yml). | [#3](https://github.com/Bahasa-Ibu/baibu-community/issues/3) |
| Quality assurance document | Done | [Test plan](../qa/test-plan.md) | [#4](https://github.com/Bahasa-Ibu/baibu-community/issues/4) |
| Code of conduct | Done | [CODE_OF_CONDUCT.md](https://github.com/Bahasa-Ibu/baibu-community/blob/main/CODE_OF_CONDUCT.md) (Contributor Covenant 2.1), [reporting guide](../community/conduct-reporting.md) | [#5](https://github.com/Bahasa-Ibu/baibu-community/issues/5) |
| Pull request workflow | Done | [Pull request template](https://github.com/Bahasa-Ibu/baibu-community/blob/main/.github/PULL_REQUEST_TEMPLATE.md), [workflow in the test plan](../qa/test-plan.md#pull-request-workflow), [merged pull requests](https://github.com/Bahasa-Ibu/baibu-community/pulls?q=is%3Apr+is%3Amerged). `main` is protected: changes need a pull request with passing lint, tests and image build. | [#6](https://github.com/Bahasa-Ibu/baibu-community/issues/6) |

## Q2: Contribution and transparency

[Milestone](https://github.com/Bahasa-Ibu/baibu-community/milestone/2)

| Requirement | Status | Where it is met | Issue |
| --- | --- | --- | --- |
| Licence publicly visible | Done | [LICENSE](https://github.com/Bahasa-Ibu/baibu-community/blob/main/LICENSE) in the public repository | |
| Contributing guide | Done | [CONTRIBUTING.md](https://github.com/Bahasa-Ibu/baibu-community/blob/main/CONTRIBUTING.md), [contributing page](../community/contributing.md) | [#8](https://github.com/Bahasa-Ibu/baibu-community/issues/8) |
| Public issues board | Planned | [Issues](https://github.com/Bahasa-Ibu/baibu-community/issues) and a public project board | [#12](https://github.com/Bahasa-Ibu/baibu-community/issues/12) |
| Developer documentation | Done | [Architecture](../developer/architecture.md), [configuration reference](../developer/configuration.md), [white-label guide](../developer/white-label.md) | [#11](https://github.com/Bahasa-Ibu/baibu-community/issues/11) |
| CI with status badge | Done | [CI workflow](https://github.com/Bahasa-Ibu/baibu-community/blob/main/.github/workflows/ci.yml) (lint, tests with coverage, migration check, image build); badge in the [README](https://github.com/Bahasa-Ibu/baibu-community/blob/main/README.md) | [#9](https://github.com/Bahasa-Ibu/baibu-community/issues/9) |
| 15% test coverage | Done | [Coverage report](https://bahasa-ibu.github.io/baibu-community/coverage/), rebuilt on every merge to `main` | [#10](https://github.com/Bahasa-Ibu/baibu-community/issues/10) |

## Q3: Community

[Milestone](https://github.com/Bahasa-Ibu/baibu-community/milestone/3)

| Requirement | Status | Where it is met | Issue |
| --- | --- | --- | --- |
| 45% test coverage | Planned | [Coverage report](https://bahasa-ibu.github.io/baibu-community/coverage/) | |
| Issue templates | Done | [Issue templates](https://github.com/Bahasa-Ibu/baibu-community/tree/main/.github/ISSUE_TEMPLATE) for bugs and feature requests | [#24](https://github.com/Bahasa-Ibu/baibu-community/issues/24) |
| At least 3 good first issues | Planned | [`good first issue` label](https://github.com/Bahasa-Ibu/baibu-community/issues?q=label%3A%22good+first+issue%22) | |
| Public discussion channel | Planned | GitHub Discussions | [#26](https://github.com/Bahasa-Ibu/baibu-community/issues/26) |
| User documentation | Planned | Guides for people running a deployment, on this site | [#27](https://github.com/Bahasa-Ibu/baibu-community/issues/27) |
| Governance document | Planned | `GOVERNANCE.md` | [#25](https://github.com/Bahasa-Ibu/baibu-community/issues/25) |

## Q4: Sustainability

[Milestone](https://github.com/Bahasa-Ibu/baibu-community/milestone/4)

| Requirement | Status | Where it is met | Issue |
| --- | --- | --- | --- |
| Documentation 1.0 | Planned | This site | |
| 80% test coverage | Planned | [Coverage report](https://bahasa-ibu.github.io/baibu-community/coverage/) | |
| Digital Public Goods review | Planned | DPG Standard self-assessment, with evidence kept in the repository | [#28](https://github.com/Bahasa-Ibu/baibu-community/issues/28) |
