<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/header-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/header-light.svg">
  <img src="./assets/header-dark.svg" alt="Artem Markitanov — Python grading, benchmarking, testing and CI automation" width="100%">
</picture>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/typing-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/typing-light.svg">
  <img src="./assets/typing-dark.svg" alt="Open-source Python maintainer · Grading, benchmarking, CI automation · Quality held by mechanism, not memory" width="82%">
</picture>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/metrics-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/metrics-light.svg">
  <img src="./assets/metrics-dark.svg" alt="4000+ tests · 32 checks per PR · branch protection bypass list is empty" width="92%">
</picture>

<br><br>

<a href="https://github.com/ArtVsMark/Stepik-Python-Grader"><img src="https://img.shields.io/badge/main_project-Stepik--Python--Grader-1F6FEB?style=for-the-badge&logo=github&logoColor=white" alt="Main project"></a>
<a href="https://pypi.org/project/stepik-python-grader/"><img src="https://img.shields.io/pypi/v/stepik-python-grader?style=for-the-badge&logo=pypi&logoColor=white&label=pypi&color=3775A9" alt="PyPI"></a>
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/ArtVsMark/Stepik-Python-Grader/ci.yml?style=for-the-badge&logo=githubactions&logoColor=white&label=CI" alt="CI"></a>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/divider-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/divider-light.svg">
  <img src="./assets/divider-dark.svg" alt="" width="100%">
</picture>

</div>

## What I maintain

<table>
<thead>
<tr><th align="left">Project</th><th align="left">What it does</th><th align="left">Stack</th></tr>
</thead>
<tbody>
<tr>
<td valign="top">
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader"><b>Stepik-Python-Grader</b></a><br>
<sub><a href="https://pypi.org/project/stepik-python-grader/">PyPI</a> · <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/blob/main/README.en.md">Quick start</a> · <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/blob/main/HISTORY.md">History</a></sub>
</td>
<td valign="top">
A local offline autograder for Python. Downloads task data from Stepik, runs correctness checks without a submit limit, and <b>compares several solutions honestly</b> — correctness first, benchmark metrics second.
</td>
<td valign="top"><sub>CLI · web UI · GUI<br>pytest plugin<br>OS sandbox</sub></td>
</tr>
<tr>
<td valign="top"><a href="https://github.com/ArtVsMark/Glossary-Python"><b>Glossary-Python</b></a></td>
<td valign="top">Supporting layer: the glossary the grader links into when a run fails.</td>
<td valign="top"><sub>content · tooling</sub></td>
</tr>
</tbody>
</table>

<sub><b>Quick start</b></sub>

```bash
pipx install stepik-python-grader && stepik-grader
```

<details>
<summary><b>Beyond basic test execution</b></summary>

<br>

| Capability | What it does |
|---|---|
| 🔍 **Offline glossary** | Bilingual RU/EN Python glossary, reachable straight from the error you just hit |
| 🧭 **Trace-based debugging** | Step-by-step tracer with a memory graph |
| ⏱️ **Subprocess benchmarking** | `timeit` microbenchmarks plus time and memory ranking across solutions |
| 🛡️ **OS-level sandboxing** | Optional execution boundary for Linux, macOS and Windows |
| 🤖 **AI failure explanations** | Opt-in, bring-your-own-key — never on by default |
| 📈 **Progress & history** | Tracks your recurring mistakes so they can be revisited |
| 📚 **Layered docs** | Split by audience: `use` · `dev` · `agent` · `audit` · `archive` |

</details>

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/divider-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/divider-light.svg">
  <img src="./assets/divider-dark.svg" alt="" width="100%">
</picture>
</div>

## What holds the quality

<table>
<tr>
<td align="center" width="25%"><h3><!--m:tests-->4000+<!--/m:tests--></h3><sub>tests across a<br>197-module suite</sub></td>
<td align="center" width="25%"><h3><!--m:checks-->16<!--/m:checks--></h3><sub>checks per PR,<br>11 of them required</sub></td>
<td align="center" width="25%"><h3>3 × 2</h3><sub>OS × Python versions,<br>3.14 experimental</sub></td>
<td align="center" width="25%"><h3><!--m:releases-->12<!--/m:releases--></h3><sub>releases shipped,<br>latest <code>v1.11.0</code></sub></td>
</tr>
</table>

- **Gates instead of memory** — `preflight.py` before a commit, `check_pr_ready.py` before a merge. Things you cannot forget, because they are enforced rather than remembered.
- **The rule applies to the owner too** — the branch-protection bypass list is empty. Not a policy, a mechanism.
- **Every rule cites its incident** — each convention in the docs carries the issue number it grew from, so half a year later it is clear not only *what* the rule is, but *why*.
- **A changelog assembled from fragments**, not written after the fact — entries land with the change that caused them.

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/divider-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/divider-light.svg">
  <img src="./assets/divider-dark.svg" alt="" width="100%">
</picture>
</div>

## Current focus

<table>
<tr><td align="center">🏗️</td><td><b>Architecture refinement</b></td><td>keeping module boundaries honest as surface area grows</td></tr>
<tr><td align="center">⚙️</td><td><b>CI &amp; merge automation</b></td><td>stronger gates, less manual shepherding</td></tr>
<tr><td align="center">🧪</td><td><b>Regression coverage</b></td><td>every fixed bug leaves a test behind</td></tr>
<tr><td align="center">🌍</td><td><b>English documentation</b></td><td>full parity with the Russian docs tree</td></tr>
<tr><td align="center">🖥️</td><td><b>Local web UX</b></td><td>making <code>--serve</code> the primary workflow, not the fallback</td></tr>
<tr><td align="center">🔒</td><td><b>Safer execution</b></td><td>tighter boundaries for untrusted code paths</td></tr>
</table>

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/divider-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/divider-light.svg">
  <img src="./assets/divider-dark.svg" alt="" width="100%">
</picture>
</div>

## Stack

<div align="center">

`Python` · `pytest` · `Hypothesis` · `Ruff` · `mypy` · `GitHub Actions` · `PyPI` · `Playwright`

<sub>CLI tooling · local web UI · benchmarking · OS sandboxing · docs architecture · release automation · typed boundaries · property-based testing</sub>

</div>

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/divider-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/divider-light.svg">
  <img src="./assets/divider-dark.svg" alt="" width="100%">
</picture>
</div>

## Contributions welcome

The grader has a **"First contribution in 15 minutes"** onramp, and every `good first issue` is written in **both Russian and English** — a bilingual body is enforced by a dedicated check, not by good intentions.

<div align="center">

<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/labels/good%20first%20issue"><img src="https://img.shields.io/badge/start_here-good_first_issue-7057FF?style=for-the-badge&logo=github&logoColor=white" alt="Good first issues"></a>
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/discussions"><img src="https://img.shields.io/badge/discussions-ask_anything-1F6FEB?style=for-the-badge&logo=github&logoColor=white" alt="Discussions"></a>
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/issues/new/choose"><img src="https://img.shields.io/badge/issues-report_a_bug-F78166?style=for-the-badge&logo=github&logoColor=white" alt="Report a bug"></a>

</div>

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/divider-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/divider-light.svg">
  <img src="./assets/divider-dark.svg" alt="" width="100%">
</picture>
</div>

<details>
<summary><h3>🇷🇺&nbsp; Читать по-русски &nbsp;·&nbsp; <sub>развернуть</sub></h3></summary>

<br>

### Привет 👋

**Мейнтейнер open-source на Python.** Делаю инструменты для тех, кто проверяет, сравнивает, отлаживает и выпускает код, — и стараюсь, чтобы качество держалось механикой, а не памятью и добрыми намерениями.

### Stepik-Python-Grader

**Локальный грейдер для курсов «Поколение Python» на Stepik** — и для любой папки с решениями и тест-кейсами.

Скачивает данные задачи с сайта, проверяет решение локально без лимита попыток и — главное, что отличает его от обычного прогона тестов — **сравнивает несколько решений честно**: сначала по корректности, потом по benchmark-метрикам. Весь сценарий доступен через **CLI**, **локальный веб-интерфейс**, **GUI-лаунчер** и **плагин pytest**.

Сверх прогона тестов: офлайн-глоссарий Python с переходом прямо из ошибки, пошаговый трассировщик с memory-graph, микробенчмарк `timeit`, OS-песочница для Linux / macOS / Windows и AI-объяснение падений (opt-in, свой ключ).

```bash
pipx install stepik-python-grader && stepik-grader
```

[Репозиторий](https://github.com/ArtVsMark/Stepik-Python-Grader) ·
[PyPI](https://pypi.org/project/stepik-python-grader/) ·
[История проекта](https://github.com/ArtVsMark/Stepik-Python-Grader/blob/main/HISTORY.md)

### Glossary-Python

[Glossary-Python](https://github.com/ArtVsMark/Glossary-Python) — словарный слой, в который грейдер уводит из упавшего прогона.

### Чем держится качество

Проект — заодно полигон инженерной дисциплины. Что стоит за зелёной галочкой:

- **более 4000 тестов** в наборе из 197 модулей;
- **32 проверки на каждый PR**, из них 11 обязательных;
- матрица CI: **три ОС × Python 3.12 / 3.13**, плюс 3.14 экспериментально;
- **11 выпусков**, от `v1.0.0` до `v1.10.0`.

- **Гейты вместо памяти** — `preflight.py` перед коммитом, `check_pr_ready.py` перед мержем. То, что нельзя забыть, потому что оно исполняется.
- **Правило действует и на владельца** — список обходов защиты ветки пуст. Это механика, а не обещание.
- **Каждое правило подписано инцидентом** — рядом стоит номер issue, из которого оно выросло: через полгода видно не только «что», но и «почему именно так».
- **CHANGELOG собирается из фрагментов**, а не пишется задним числом: запись приезжает вместе с изменением.

### Открыт для вклада

В грейдере есть онрамп **«Первый вклад за 15 минут»**, а задачи с меткой `good first issue` заводятся сразу на двух языках — двуязычие проверяет отдельный скрипт, а не добрая воля.

</details>

<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/ArtVsMark/ArtVsMark/output/snake-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/ArtVsMark/ArtVsMark/output/snake-light.svg">
  <img src="https://raw.githubusercontent.com/ArtVsMark/ArtVsMark/output/snake-dark.svg" alt="Contribution graph consumed by a snake" width="100%">
</picture>

</div>
