<p align="left">
  <img src="./header.svg" alt="Artem Markitanov — Python grading, benchmarking, testing and CI automation" width="100%" />
</p>

<h3 align="left">Open-source Python maintainer building grading, testing, benchmarking and CI automation tools.</h3>

<p align="left">
  I build practical developer tooling for checking, comparing, debugging and shipping Python code with more confidence.
</p>

<p align="left">
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader"><img src="https://img.shields.io/badge/main%20project-Stepik--Python--Grader-1f6feb?style=flat-square&logo=github&logoColor=white" alt="Main project: Stepik-Python-Grader" /></a>
  <a href="https://pypi.org/project/stepik-python-grader/"><img src="https://img.shields.io/pypi/v/stepik-python-grader?style=flat-square&logo=pypi&logoColor=white&label=pypi&color=3775A9" alt="Latest version on PyPI" /></a>
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/blob/main/LICENSE"><img src="https://img.shields.io/github/license/ArtVsMark/Stepik-Python-Grader?style=flat-square&color=57606a" alt="MIT licensed" /></a>
  <a href="https://github.com/ArtVsMark?tab=followers"><img src="https://img.shields.io/github/followers/ArtVsMark?style=flat-square&logo=github&logoColor=white&label=followers&color=57606a" alt="GitHub followers" /></a>
</p>

---

## Engineering profile

I maintain tools for workflows that need more than a simple “works / doesn’t work” result.

My focus sits at the intersection of:

`Python tooling` · `local grading & test orchestration` · `benchmark-driven comparison` · `CI/CD automation` · `contributor experience` · `documentation systems that stay usable as the codebase grows`

---

## What I maintain

### 🎓 Stepik-Python-Grader

> Local offline autograder for Python: run, benchmark and compare solutions, with an optional OS sandbox and web UI.

<p align="left">
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/releases"><img src="https://img.shields.io/github/v/release/ArtVsMark/Stepik-Python-Grader?style=flat-square&logo=github&logoColor=white&label=release&color=238636" alt="Latest release" /></a>
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/ArtVsMark/Stepik-Python-Grader/ci.yml?style=flat-square&logo=githubactions&logoColor=white&label=CI" alt="CI status" /></a>
  <img src="https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14%20(exp)-3776AB?style=flat-square&logo=python&logoColor=white" alt="Supported Python versions" />
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/commits/main"><img src="https://img.shields.io/github/last-commit/ArtVsMark/Stepik-Python-Grader?style=flat-square&color=8957e5&label=last%20commit" alt="Last commit" /></a>
</p>

A local grader for Stepik Python courses — and for any folder of solutions and test cases. It can:

- download task data automatically,
- run correctness checks locally, without a submit limit,
- compare multiple solutions more honestly — correctness first, benchmark metrics second,
- and expose the whole workflow through **CLI**, **local web UI**, **GUI launcher** and a **pytest plugin**.

<details>
<summary><b>Beyond basic test execution</b></summary>

<br />

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

<p align="left">
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader">Repository</a> ·
  <a href="https://pypi.org/project/stepik-python-grader/">PyPI package</a> ·
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/blob/main/README.en.md">English quick start</a> ·
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/blob/main/HISTORY.md">Project history</a>
</p>

```bash
pipx install stepik-python-grader && stepik-grader
```

### 📖 Glossary-Python

A glossary project for people learning Python — the vocabulary layer the grader links into when a run fails.

<p align="left">
  <a href="https://github.com/ArtVsMark/Glossary-Python">Repository</a>
</p>

---

## Selected signal

<p align="left">
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/pulls?q=is%3Apr+is%3Aclosed"><img src="https://img.shields.io/github/issues-pr-closed/ArtVsMark/Stepik-Python-Grader?style=flat-square&label=pull%20requests&color=f78166" alt="Closed pull requests" /></a>
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/graphs/commit-activity"><img src="https://img.shields.io/github/commit-activity/m/ArtVsMark/Stepik-Python-Grader?style=flat-square&label=commits%2Fmonth&color=1f6feb" alt="Commits per month" /></a>
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/graphs/contributors"><img src="https://img.shields.io/github/contributors/ArtVsMark/Stepik-Python-Grader?style=flat-square&label=contributors&color=238636" alt="Contributors" /></a>
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/issues"><img src="https://img.shields.io/github/issues/ArtVsMark/Stepik-Python-Grader?style=flat-square&label=open%20issues&color=57606a" alt="Open issues" /></a>
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/network/members"><img src="https://img.shields.io/github/forks/ArtVsMark/Stepik-Python-Grader?style=flat-square&label=forks&color=8957e5" alt="Forks" /></a>
</p>

**Eleven releases**, `v1.0.0` → `v1.10.0`, shipped since the first stable cut — on the back of **close to six hundred merged pull requests**, a **197-module test suite**, a merge-queue-gated CI matrix across Linux, macOS and Windows, and a changelog assembled from fragments rather than written after the fact.

I like shipping systems that are visible in the repo history: tests, release flow, changelog discipline, security posture, docs structure and merge automation.

---

## How I work

- Build around repeatable workflows, not one-off fixes.
- Prefer measurable quality: tests, benchmarks, typed boundaries and explicit invariants.
- Keep docs close to the code and split by audience.
- Treat repository operations as product surface, not maintenance noise.
- Optimize for maintainability, reviewability and long-term project clarity.

---

## Current focus

Pushing Stepik-Python-Grader further in these directions:

<table>
<tr><td>🏗️</td><td><b>Architecture refinement</b></td><td>keeping module boundaries honest as surface area grows</td></tr>
<tr><td>⚙️</td><td><b>CI &amp; merge automation</b></td><td>stronger gates, less manual shepherding</td></tr>
<tr><td>🧪</td><td><b>Regression coverage</b></td><td>every fixed bug leaves a test behind</td></tr>
<tr><td>🌍</td><td><b>English documentation</b></td><td>full parity with the Russian docs tree</td></tr>
<tr><td>🖥️</td><td><b>Local web UX</b></td><td>making <code>--serve</code> the primary workflow, not the fallback</td></tr>
<tr><td>🔒</td><td><b>Safer execution</b></td><td>tighter boundaries for untrusted code paths</td></tr>
</table>

---

## Stack

<p align="left">
  <img src="https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white" alt="pytest" />
  <img src="https://img.shields.io/badge/Hypothesis-4B32C3?style=flat-square" alt="Hypothesis" />
  <img src="https://img.shields.io/badge/Ruff-D7FF64?style=flat-square&logo=ruff&logoColor=black" alt="Ruff" />
  <img src="https://img.shields.io/badge/mypy-2A6DB2?style=flat-square" alt="mypy" />
  <img src="https://img.shields.io/badge/GitHub%20Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white" alt="GitHub Actions" />
  <img src="https://img.shields.io/badge/PyPI-3775A9?style=flat-square&logo=pypi&logoColor=white" alt="PyPI publishing" />
  <img src="https://img.shields.io/badge/Playwright-2EAD33?style=flat-square&logo=playwright&logoColor=white" alt="Playwright" />
  <img src="https://img.shields.io/badge/Rich-1f6feb?style=flat-square" alt="Rich" />
  <img src="https://img.shields.io/badge/pre--commit-FAB040?style=flat-square&logo=precommit&logoColor=black" alt="pre-commit" />
</p>

```text
CLI tooling · local web UI · benchmarking · OS sandboxing · docs architecture
release automation · merge queues · typed boundaries · property-based testing
```

---

## Contact surface

<p align="left">
  <a href="https://github.com/ArtVsMark"><img src="https://img.shields.io/badge/GitHub-ArtVsMark-181717?style=flat-square&logo=github&logoColor=white" alt="GitHub profile" /></a>
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/discussions"><img src="https://img.shields.io/badge/Discussions-ask%20anything-1f6feb?style=flat-square&logo=github&logoColor=white" alt="GitHub Discussions" /></a>
  <a href="https://github.com/ArtVsMark/Stepik-Python-Grader/issues/new/choose"><img src="https://img.shields.io/badge/Issues-report%20a%20bug-f78166?style=flat-square&logo=github&logoColor=white" alt="Open an issue" /></a>
</p>

<p align="left">
  <sub>Practical Python tooling for checking, comparing, debugging and shipping code with more confidence.</sub>
</p>
