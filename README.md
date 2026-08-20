<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/header-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/header-light.svg">
  <img src="./assets/header-dark.svg" alt="Artem Markitanov — Python grading, benchmarking, testing and CI automation" width="100%">
</picture>

<br><br>

**Open-source Python maintainer.** I build practical developer tooling for checking,<br>comparing, debugging and shipping Python code with more confidence.

<br>

<a href="https://github.com/ArtVsMark/Stepik-Python-Grader"><img src="https://img.shields.io/badge/main_project-Stepik--Python--Grader-1F6FEB?style=for-the-badge&logo=github&logoColor=white" alt="Main project"></a>
<a href="https://pypi.org/project/stepik-python-grader/"><img src="https://img.shields.io/pypi/v/stepik-python-grader?style=for-the-badge&logo=pypi&logoColor=white&label=pypi&color=3775A9" alt="PyPI"></a>
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/ArtVsMark/Stepik-Python-Grader/ci.yml?style=for-the-badge&logo=githubactions&logoColor=white&label=CI" alt="CI"></a>
<a href="https://github.com/ArtVsMark?tab=followers"><img src="https://img.shields.io/github/followers/ArtVsMark?style=for-the-badge&logo=github&logoColor=white&label=followers&color=57606A" alt="Followers"></a>

</div>

<br>

---

<div align="center">

### 🎓 Stepik-Python-Grader

**A local offline autograder for Python** — run, benchmark and compare solutions,<br>with an optional OS sandbox, a local web UI and a GUI launcher.

<a href="https://github.com/ArtVsMark/Stepik-Python-Grader">
  <img src="https://raw.githubusercontent.com/ArtVsMark/Stepik-Python-Grader/main/docs/assets/hero-serve.gif" alt="Web UI: grading a folder of solutions against test cases" width="88%">
</a>

<br><br>

```bash
pipx install stepik-python-grader && stepik-grader
```

<a href="https://github.com/ArtVsMark/Stepik-Python-Grader"><b>Repository</b></a> ·
<a href="https://pypi.org/project/stepik-python-grader/">PyPI</a> ·
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/blob/main/README.en.md">Quick start</a> ·
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/blob/main/HISTORY.md">Project history</a>

</div>

<br>

It downloads task data from Stepik automatically, runs correctness checks locally without a submit limit, and — the part that makes it more than a test runner — **compares several solutions honestly**: correctness first, benchmark metrics second. The whole workflow is exposed through **CLI**, **local web UI**, **GUI launcher** and a **pytest plugin**.

<table>
<tr>
<td width="50%" valign="top">
<img src="https://raw.githubusercontent.com/ArtVsMark/Stepik-Python-Grader/main/docs/assets/serve-results.png" alt="Results table: 5 of 5 test cases passed, verdict OK, time and memory" width="100%">
<p align="center"><sub><b>Verdicts with time and memory</b> — ranking, not just pass/fail</sub></p>
</td>
<td width="50%" valign="top">
<img src="https://raw.githubusercontent.com/ArtVsMark/Stepik-Python-Grader/main/docs/assets/serve-glossary.png" alt="Glossary section: card list and an open card for the % operator" width="100%">
<p align="center"><sub><b>Offline glossary</b> — reachable straight from the error you just hit</sub></p>
</td>
</tr>
</table>

<details>
<summary><b>⚙️ Beyond basic test execution</b></summary>

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

<br>

---

## 🛠 What holds the quality

The project doubles as a proving ground for engineering discipline. What sits behind the green check:

<table>
<tr>
<td align="center" width="25%"><h3>4000+</h3><sub>tests across a<br>197-module suite</sub></td>
<td align="center" width="25%"><h3>32</h3><sub>checks per PR,<br>11 of them required</sub></td>
<td align="center" width="25%"><h3>3 × 2</h3><sub>OS × Python versions,<br>3.14 experimental</sub></td>
<td align="center" width="25%"><h3>11</h3><sub>releases shipped,<br><code>v1.0.0</code> → <code>v1.10.0</code></sub></td>
</tr>
</table>

- **Gates instead of memory** — `preflight.py` before a commit, `check_pr_ready.py` before a merge. Things you cannot forget, because they are enforced rather than remembered.
- **The rule applies to the owner too** — the branch-protection bypass list is empty. Not a policy, a mechanism.
- **Every rule cites its incident** — each convention in the docs carries the issue number it grew from, so half a year later it is clear not only *what* the rule is, but *why*.
- **A changelog assembled from fragments**, not written after the fact — entries land with the change that caused them.

<br>

---

## 📊 Activity

<div align="center">

<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/pulls?q=is%3Apr+is%3Aclosed"><img src="https://img.shields.io/github/issues-pr-closed/ArtVsMark/Stepik-Python-Grader?style=flat-square&label=merged%20pull%20requests&color=8957E5" alt="Merged PRs"></a>
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/graphs/commit-activity"><img src="https://img.shields.io/github/commit-activity/m/ArtVsMark/Stepik-Python-Grader?style=flat-square&label=commits%2Fmonth&color=1F6FEB" alt="Commits per month"></a>
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/graphs/contributors"><img src="https://img.shields.io/github/contributors/ArtVsMark/Stepik-Python-Grader?style=flat-square&label=contributors&color=238636" alt="Contributors"></a>
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/issues"><img src="https://img.shields.io/github/issues/ArtVsMark/Stepik-Python-Grader?style=flat-square&label=open%20issues&color=57606A" alt="Open issues"></a>
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/labels/good%20first%20issue"><img src="https://img.shields.io/github/issues/ArtVsMark/Stepik-Python-Grader/good%20first%20issue?style=flat-square&label=good%20first%20issues&color=7057FF" alt="Good first issues"></a>

</div>

<br>

---

## 🧭 Current focus

<table>
<tr><td align="center">🏗️</td><td><b>Architecture refinement</b></td><td>keeping module boundaries honest as surface area grows</td></tr>
<tr><td align="center">⚙️</td><td><b>CI &amp; merge automation</b></td><td>stronger gates, less manual shepherding</td></tr>
<tr><td align="center">🧪</td><td><b>Regression coverage</b></td><td>every fixed bug leaves a test behind</td></tr>
<tr><td align="center">🌍</td><td><b>English documentation</b></td><td>full parity with the Russian docs tree</td></tr>
<tr><td align="center">🖥️</td><td><b>Local web UX</b></td><td>making <code>--serve</code> the primary workflow, not the fallback</td></tr>
<tr><td align="center">🔒</td><td><b>Safer execution</b></td><td>tighter boundaries for untrusted code paths</td></tr>
</table>

<br>

---

## 🧰 Stack

<div align="center">

<img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
<img src="https://img.shields.io/badge/pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white" alt="pytest">
<img src="https://img.shields.io/badge/Hypothesis-4B32C3?style=for-the-badge" alt="Hypothesis">
<img src="https://img.shields.io/badge/Ruff-D7FF64?style=for-the-badge&logo=ruff&logoColor=black" alt="Ruff">
<img src="https://img.shields.io/badge/mypy-2A6DB2?style=for-the-badge" alt="mypy">
<img src="https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white" alt="GitHub Actions">
<img src="https://img.shields.io/badge/PyPI-3775A9?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI">
<img src="https://img.shields.io/badge/Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white" alt="Playwright">

<br>

<sub><code>CLI tooling</code> · <code>local web UI</code> · <code>benchmarking</code> · <code>OS sandboxing</code> · <code>docs architecture</code> · <code>release automation</code> · <code>typed boundaries</code> · <code>property-based testing</code></sub>

</div>

<br>

---

## 📖 Also maintained

**[Glossary-Python](https://github.com/ArtVsMark/Glossary-Python)** — the vocabulary layer the grader links into when a run fails.

<br>

---

## 🤝 Contributions welcome

The grader has a **"First contribution in 15 minutes"** onramp, and every `good first issue` is written in **both Russian and English** — a bilingual body is enforced by a dedicated check, not by good intentions.

<div align="center">

<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/labels/good%20first%20issue"><img src="https://img.shields.io/badge/start_here-good_first_issue-7057FF?style=for-the-badge&logo=github&logoColor=white" alt="Good first issues"></a>
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/discussions"><img src="https://img.shields.io/badge/discussions-ask_anything-1F6FEB?style=for-the-badge&logo=github&logoColor=white" alt="Discussions"></a>
<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/issues/new/choose"><img src="https://img.shields.io/badge/issues-report_a_bug-F78166?style=for-the-badge&logo=github&logoColor=white" alt="Report a bug"></a>

</div>

<br>

---

<details>
<summary><b>🇷🇺 По-русски</b></summary>

<br>

### Привет 👋

**Мейнтейнер open-source на Python.** Делаю инструменты для тех, кто проверяет, сравнивает, отлаживает и выпускает код, — и стараюсь, чтобы качество держалось механикой, а не памятью и добрыми намерениями.

### 🎓 Stepik-Python-Grader

**Локальный грейдер для курсов «Поколение Python» на Stepik** — и для любой папки с решениями и тест-кейсами.

Скачивает данные задачи с сайта, проверяет решение локально без лимита попыток и — главное, что отличает его от обычного прогона тестов — **сравнивает несколько решений честно**: сначала по корректности, потом по benchmark-метрикам. Весь сценарий доступен через **CLI**, **локальный веб-интерфейс**, **GUI-лаунчер** и **плагин pytest**.

Сверх прогона тестов: офлайн-глоссарий Python с переходом прямо из ошибки, пошаговый трассировщик с memory-graph, микробенчмарк `timeit`, OS-песочница для Linux / macOS / Windows и AI-объяснение падений (opt-in, свой ключ).

```bash
pipx install stepik-python-grader && stepik-grader
```

[Репозиторий](https://github.com/ArtVsMark/Stepik-Python-Grader) ·
[PyPI](https://pypi.org/project/stepik-python-grader/) ·
[История проекта](https://github.com/ArtVsMark/Stepik-Python-Grader/blob/main/HISTORY.md)

### 🛠 Чем держится качество

Проект — заодно полигон инженерной дисциплины. Что стоит за зелёной галочкой:

- **более 4000 тестов** в наборе из 197 модулей;
- **32 проверки на каждый PR**, из них 11 обязательных;
- матрица CI: **три ОС × Python 3.12 / 3.13**, плюс 3.14 экспериментально;
- **11 выпусков**, от `v1.0.0` до `v1.10.0`.

- **Гейты вместо памяти** — `preflight.py` перед коммитом, `check_pr_ready.py` перед мержем. То, что нельзя забыть, потому что оно исполняется.
- **Правило действует и на владельца** — список обходов защиты ветки пуст. Это механика, а не обещание.
- **Каждое правило подписано инцидентом** — рядом стоит номер issue, из которого оно выросло: через полгода видно не только «что», но и «почему именно так».
- **CHANGELOG собирается из фрагментов**, а не пишется задним числом: запись приезжает вместе с изменением.

### 🤝 Открыт для вклада

В грейдере есть онрамп **«Первый вклад за 15 минут»**, а задачи с меткой `good first issue` заводятся сразу на двух языках — двуязычие проверяет отдельный скрипт, а не добрая воля.

</details>

<br>

<div align="center">
<sub>Practical Python tooling for checking, comparing, debugging and shipping code with more confidence.</sub>
</div>
