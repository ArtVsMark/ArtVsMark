<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/header-dark.svg?v=4fc1fdaf">
  <source media="(prefers-color-scheme: light)" srcset="./assets/header-light.svg?v=a4f0ba52">
  <img src="./assets/header-dark.svg?v=4fc1fdaf" alt="Artem Markitanov — Python grading, benchmarking, testing and CI automation" width="100%">
</picture>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/typing-dark.svg?v=4d29b67d">
  <source media="(prefers-color-scheme: light)" srcset="./assets/typing-light.svg?v=98c7f710">
  <img src="./assets/typing-dark.svg?v=4d29b67d" alt="Open-source Python maintainer; Grading · benchmarking · CI automation; Quality held by mechanism, not memory" width="82%">
</picture>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/metrics-dark.svg?v=990269d3">
  <source media="(prefers-color-scheme: light)" srcset="./assets/metrics-light.svg?v=eeab3dfe">
  <img src="./assets/metrics-dark.svg?v=990269d3" alt="Stepik-Python-Grader: 4000+ tests, 227 test modules, 17 checks per PR" width="92%">
</picture>

<br><br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/divider-dark.svg?v=1c137c57">
  <source media="(prefers-color-scheme: light)" srcset="./assets/divider-light.svg?v=e01c573a">
  <img src="./assets/divider-dark.svg?v=1c137c57" alt="" width="100%">
</picture>

</div>

## What I maintain

<div align="center">
<a href="https://github.com/ArtVsMark?tab=repositories">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/featured-dark.svg?v=cebda6a9">
  <source media="(prefers-color-scheme: light)" srcset="./assets/featured-light.svg?v=e671cfbe">
  <img src="./assets/featured-dark.svg?v=cebda6a9" alt="Stepik-Python-Grader — Offline Python autograder: unlimited local checks, honest side-by-side comparison of solutions. release v1.11.0, CI success, coverage 91.8%, pypi 1.11.0. 2 stars, 1679 commits, 39 issues, 12 releases, 669 prs. CLI · web UI · GUI · pytest plugin · OS sandbox · claude-code-playbook — Rules for agent sessions and a GitHub pipeline — each one carrying the incident it grew from. release v1.0.0, CI success, coverage 53%, pypi none. 1 stars, 210 commits, 3 issues, 2 releases, 96 prs. docs · RU/EN · claude-code-usage — Turns a three-step limit indicator into a number. Early: the spec is written, the tool is not. release none, CI none, coverage none, pypi 2.0.0. 0 stars, 6 commits, 19 issues, 0 releases, 1 prs. Python · JSONL over git · Glossary-Python — The RU/EN glossary the grader links into when a run fails. release none, CI none, coverage none, pypi none. 2 stars, 3 commits, 3 issues, 0 releases, 0 prs. content · tooling" width="100%">
</picture>
</a>
</div>

<!--m:projects-->
<div align="center">

<a href="https://github.com/ArtVsMark/Stepik-Python-Grader"><picture><source media="(prefers-color-scheme: dark)" srcset="./assets/tile-stepik-python-grader-dark.svg?v=c11f5616"><source media="(prefers-color-scheme: light)" srcset="./assets/tile-stepik-python-grader-light.svg?v=28539d07"><img src="./assets/tile-stepik-python-grader-dark.svg?v=c11f5616" alt="Open Stepik-Python-Grader on GitHub" width="23%"></picture></a>
<a href="https://github.com/ArtVsMark/claude-code-playbook"><picture><source media="(prefers-color-scheme: dark)" srcset="./assets/tile-claude-code-playbook-dark.svg?v=9f8a32b5"><source media="(prefers-color-scheme: light)" srcset="./assets/tile-claude-code-playbook-light.svg?v=edf662b3"><img src="./assets/tile-claude-code-playbook-dark.svg?v=9f8a32b5" alt="Open claude-code-playbook on GitHub" width="23%"></picture></a>
<a href="https://github.com/ArtVsMark/claude-code-usage"><picture><source media="(prefers-color-scheme: dark)" srcset="./assets/tile-claude-code-usage-dark.svg?v=58ff0736"><source media="(prefers-color-scheme: light)" srcset="./assets/tile-claude-code-usage-light.svg?v=933998b2"><img src="./assets/tile-claude-code-usage-dark.svg?v=58ff0736" alt="Open claude-code-usage on GitHub" width="23%"></picture></a>
<a href="https://github.com/ArtVsMark/Glossary-Python"><picture><source media="(prefers-color-scheme: dark)" srcset="./assets/tile-glossary-python-dark.svg?v=c3e901f8"><source media="(prefers-color-scheme: light)" srcset="./assets/tile-glossary-python-light.svg?v=7db11f01"><img src="./assets/tile-glossary-python-dark.svg?v=c3e901f8" alt="Open Glossary-Python on GitHub" width="23%"></picture></a>

</div>
<!--/m:projects-->

<sub><b>Quick start</b></sub>

```bash
pipx install stepik-python-grader && stepik-grader
```

**Beyond running tests:** an offline RU/EN glossary of <!--m:glossary-->1349<!--/m:glossary--> ready cards, reachable straight from the error you just hit · a step-by-step tracer with a memory graph · `timeit` microbenchmarks with time and memory ranking · an optional OS-level sandbox, kernel-enforced on Linux and macOS and partial on Windows, where the missing network isolation is a [named gap](https://github.com/ArtVsMark/Stepik-Python-Grader/blob/main/SECURITY.md#гарантии-по-ос-асимметрия--не-баг-задокументированный-компромисс), not an oversight · opt-in AI failure explanations, bring-your-own-key.

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/divider-dark.svg?v=1c137c57">
  <source media="(prefers-color-scheme: light)" srcset="./assets/divider-light.svg?v=e01c573a">
  <img src="./assets/divider-dark.svg?v=1c137c57" alt="" width="100%">
</picture>
</div>

## What holds the quality

<!--m:required-->11<!--/m:required--> required checks on `main` · <!--m:os-->3<!--/m:os--> OS × <!--m:py-->2<!--/m:py--> Python versions, <!--m:exp-->3.14<!--/m:exp--> experimental · <!--m:releases-->12<!--/m:releases--> releases shipped

- **Gates instead of memory** — `preflight.py` before a commit, `check_pr_ready.py` before a merge. Things you cannot forget, because they are enforced rather than remembered.
- **The gate is a ruleset, not an agreement** — what protects `main` is public, and you can read it without taking my word: every required check green, on a branch already up to date with `main`, force-push and deletion refused. [See for yourself](https://api.github.com/repos/ArtVsMark/Stepik-Python-Grader/rules/branches/main).
- **Every rule cites its incident** — each convention carries the issue number it grew from, and the incidents themselves live in a [public catalogue](https://github.com/ArtVsMark/claude-code-playbook). This page answers for every rule in it — adopted and by what, rejected and why, no subject here — in [`.rules/bindings.json`](./.rules/bindings.json).
- **A changelog assembled from fragments**, not written after the fact — entries land with the change that caused them.
- **The numbers above are measured, not typed** — a [daily job](./.github/workflows/metrics.yml) reads them from the repositories that produce them and rewrites this page. A number nobody measures is a number that rots.

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/divider-dark.svg?v=1c137c57">
  <source media="(prefers-color-scheme: light)" srcset="./assets/divider-light.svg?v=e01c573a">
  <img src="./assets/divider-dark.svg?v=1c137c57" alt="" width="100%">
</picture>
</div>

## Current focus

<!--focus-->
| | |
|---|---|
| **CI & merge automation** | stronger gates, less manual shepherding |
| **Regression coverage** | every fixed bug leaves a test behind |
| **English documentation** | full parity with the Russian docs tree |
| **Local web UX** | making `--serve` the primary workflow, not the fallback |
<!--/focus-->

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/divider-dark.svg?v=1c137c57">
  <source media="(prefers-color-scheme: light)" srcset="./assets/divider-light.svg?v=e01c573a">
  <img src="./assets/divider-dark.svg?v=1c137c57" alt="" width="100%">
</picture>
</div>

## Stack

<div align="center">

`Python` · `pytest` · `Hypothesis` · `Ruff` · `mypy` · `GitHub Actions` · `PyPI` · `Playwright`

<sub>CLI tooling · local web UI · benchmarking · OS sandboxing · docs architecture · release automation · typed boundaries · property-based testing</sub>

</div>

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/divider-dark.svg?v=1c137c57">
  <source media="(prefers-color-scheme: light)" srcset="./assets/divider-light.svg?v=e01c573a">
  <img src="./assets/divider-dark.svg?v=1c137c57" alt="" width="100%">
</picture>
</div>

## Contributions welcome

The grader has a **"First contribution in 15 minutes"** onramp, and every `good first issue` is written in **both Russian and English** — a bilingual body is enforced by a dedicated check, not by good intentions. Open right now: **<!--m:gfi-->3<!--/m:gfi-->** — the count is rebuilt from the tracker daily, and an empty pool means none are waiting this minute, not that the door is closed.

<div align="center">

<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/labels/good%20first%20issue"><img src="https://img.shields.io/badge/start_here-good_first_issue-7057FF?style=for-the-badge&logo=github&logoColor=white" alt="Good first issues"></a>
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/discussions"><img src="https://img.shields.io/badge/discussions-ask_anything-1F6FEB?style=for-the-badge&logo=github&logoColor=white" alt="Discussions"></a>
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/issues/new/choose"><img src="https://img.shields.io/badge/issues-report_a_bug-F78166?style=for-the-badge&logo=github&logoColor=white" alt="Report a bug"></a>

</div>

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/divider-dark.svg?v=1c137c57">
  <source media="(prefers-color-scheme: light)" srcset="./assets/divider-light.svg?v=e01c573a">
  <img src="./assets/divider-dark.svg?v=1c137c57" alt="" width="100%">
</picture>
</div>

### 🇷🇺 По-русски

**Мейнтейнер open-source на Python.** Флагман — [Stepik-Python-Grader](https://github.com/ArtVsMark/Stepik-Python-Grader):
локальный грейдер, который не просто прогоняет тесты, а **сравнивает решения честно** — сначала по
корректности, потом по benchmark-метрикам. Рядом — [claude-code-playbook](https://github.com/ArtVsMark/claude-code-playbook),
каталог из <!--m:rules-->147<!--/m:rules--> правил, каждое с историей поломки, из которой выросло, и [claude-code-usage](https://github.com/ArtVsMark/claude-code-usage) —
остаток лимитов Claude Code в цифрах вместо трёхступенчатого светофора; пока спецификация.

Качество держится механикой, а не памятью: гейты перед коммитом и мержем, зелёный CI на актуальной
ветке как условие мержа, числа на этой странице пересобирает
[отдельный workflow](./.github/workflows/metrics.yml), а не автор.

Подробности — в самих проектах: [README грейдера](https://github.com/ArtVsMark/Stepik-Python-Grader#readme) (на русском) · [история](https://github.com/ArtVsMark/Stepik-Python-Grader/blob/main/HISTORY.md) · [как включиться](https://github.com/ArtVsMark/Stepik-Python-Grader/blob/main/CONTRIBUTING.md)

<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/ArtVsMark/ArtVsMark/output/snake-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/ArtVsMark/ArtVsMark/output/snake-light.svg">
  <img src="https://raw.githubusercontent.com/ArtVsMark/ArtVsMark/output/snake-dark.svg" alt="Contribution graph consumed by a snake" width="100%">
</picture>

</div>
