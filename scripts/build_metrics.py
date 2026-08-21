#!/usr/bin/env python3
"""Собирает метрики витрины из живых источников и рисует assets/metrics-*.svg.

Числа на странице профиля устаревают молча: релиз v1.11.0 вышел через четыре
часа после того, как в README было вписано «11 releases shipped». Поэтому они
не вписываются руками, а измеряются — раз в сутки, из репозиториев, которые их
и порождают.

Что откуда берётся:

* число тестов и число тест-модулей — из клона грейдера (подсчёт ``def test_``
  и файлов ``test_*.py``; грубее, чем ``pytest --collect-only``, зато без
  установки зависимостей — на витрине всё равно показывается порядок «4000+»);
* проверок на PR — сколько РАЗНЫХ check-runs создано на последних смерженных
  PR (медиана, см. ``checks_per_pr``);
* обязательные проверки, число ОС и версий Python — из ruleset защиты ветки
  ``main``. Список правил ветки (``/rules/branches/main``) читается **без прав
  admin**, в отличие от самого объекта ruleset: имена обязательных контекстов
  там есть, и «11 обязательных» больше не приходится держать в памяти;
* экспериментальные версии Python — из матрицы ``ci.yml`` грейдера: они под
  ``continue-on-error`` и в ruleset намеренно не входят, поэтому в API их нет;
* релизов — длиной списка релизов. Номер последней версии витрина не
  повторяет: его показывает живой бейдж PyPI, а два места для одного числа —
  это два места, где оно может разойтись;
* покрытие и карточки глоссария — из ветки ``badges`` грейдера: его CI уже
  публикует эти числа как shields-endpoint JSON, и иначе их не получить —
  нужен прогон тестов и установленный пакет;
* пул ``good first issue`` — прямым запросом к трекеру, а НЕ из бейджа рядом с
  предыдущими двумя: бейдж обновляет CI грейдера, и между его прогонами число
  отстаёт. Витрина показывала 3, когда открытых было 4;
* правил в каталоге — числом файлов ``rules/ru/*.md`` в клоне playbook.

Чего здесь НЕТ и почему: пустой список обходов защиты ветки. GitHub отдаёт
``bypass_actors`` только админу репозитория, у ``GITHUB_TOKEN`` витрины таких
прав нет. Непроверяемое число на плитке выглядит как измеренное, поэтому оно
снято с картинки: утверждение живёт в тексте витрины как утверждение, а не как
метрика.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import statistics
import sys
import urllib.parse
import urllib.request

REPO = "ArtVsMark/Stepik-Python-Grader"
API = "https://api.github.com"
ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT = "Inter,Segoe UI,Helvetica,Arial,sans-serif"


def _get(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {t}"} if (t := os.environ.get("GH_TOKEN")) else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _api(path: str) -> object:
    return json.loads(_get(f"{API}{path}"))


def badge(name: str) -> str:
    """Значение живого бейджа грейдера из ветки ``badges``.

    Бейджи публикуются отдельной веткой (issue #1235 грейдера), а не в ``main``,
    поэтому берутся не из клона рабочего дерева, а по ссылке на ветку.

    Читается через contents-API, а НЕ через ``raw.githubusercontent.com``:
    raw отвечает 404 на запрос с заголовком ``Authorization`` — токен для него
    чужой, и вместо содержимого приходит «нет такого файла». Отладка этого
    стоит дорого: URL в браузере открывается, а сборка падает. Заодно contents
    отдаёт свежий файл, тогда как raw держит свой кэш.
    """
    payload = _api(f"/repos/{REPO}/contents/.github/badges/{name}.json?ref=badges")
    return json.loads(base64.b64decode(payload["content"]))["message"]


def good_first_issues() -> int:
    """Сколько задач для новичка открыто прямо сейчас.

    Грейдер публикует это число бейджем, но бейдж пишет его CI — между
    прогонами значение отстаёт, и витрина однажды показывала три открытые
    задачи против четырёх настоящих. Покрытие и глоссарий иначе не достать,
    а это обычный запрос к трекеру: делать его самим дешевле, чем показывать
    вчерашнее.

    Из выдачи убираются PR: endpoint ``issues`` отдаёт и их тоже.
    """
    label = urllib.parse.quote("good first issue")
    issues = _api(f"/repos/{REPO}/issues?state=open&labels={label}&per_page=100")
    return len([issue for issue in issues if "pull_request" not in issue])


def count_tests(grader: pathlib.Path) -> int:
    """Число тест-функций в клоне грейдера."""
    total = 0
    for path in (grader / "tests").rglob("*.py"):
        total += len(re.findall(r"^\s*def test_", path.read_text(encoding="utf-8"), re.M))
    return total


def count_test_modules(grader: pathlib.Path) -> int:
    """Число тест-модулей.

    Считаются файлы ``test_*.py``, а не всё дерево ``tests/``: conftest и хелперы
    тестами не являются. Прежняя витрина говорила «197-module suite» — число
    было вписано руками и разошлось с деревом на дюжину файлов.
    """
    return len(list((grader / "tests").rglob("test_*.py")))


def checks_per_pr(sample: int = 7) -> int:
    """Сколько РАЗНЫХ проверок создаётся на PR.

    Считаются уникальные имена, а не ``total_count``: после ``update-branch``
    GitHub создаёт второй комплект check-runs, а первый остаётся висеть на
    коммите. Сумма тогда удваивается — так на витрине и появилось «32 checks
    per PR» вместо действительных шестнадцати.

    Берётся медиана по нескольким последним PR, а не максимум: у отдельно
    взятого PR часть джобов могла не стартовать (конфликт, отменённый прогон) —
    и такая выборка занизила бы число; а один разовый лишний workflow, наоборот,
    задрал бы максимум навсегда. Медиана переживает и то, и другое.
    """
    counts = []
    for pull in _api(f"/repos/{REPO}/pulls?state=closed&per_page=30"):
        if not pull.get("merged_at"):
            continue
        runs = _api(f"/repos/{REPO}/commits/{pull['head']['sha']}/check-runs?per_page=100")
        counts.append(len({run["name"] for run in runs["check_runs"]}))
        if len(counts) >= sample:
            break
    return int(statistics.median(counts)) if counts else 0


def protection_facts() -> tuple[int, int, int]:
    """Обязательные проверки на ``main``: сколько их, сколько ОС и версий Python.

    Источник — правила ветки, а не объект ruleset: ``/rules/branches/main``
    отдаёт имена обязательных контекстов любому, кто видит репозиторий, тогда
    как ``/rulesets/{id}`` без прав admin молчит про ``bypass_actors``.

    Имена матричных джобов входят в ruleset дословно
    (``test (ubuntu-latest, 3.12, false)``), поэтому размерность матрицы
    вынимается из них же: это ровно те комбинации, без которых мерж не
    состоится.
    """
    contexts = []
    for rule in _api(f"/repos/{REPO}/rules/branches/main"):
        if rule.get("type") == "required_status_checks":
            contexts = [c["context"] for c in rule["parameters"]["required_status_checks"]]
    matrix = [re.match(r"test \(([^,]+), ([^,)]+)", context) for context in contexts]
    systems = {m.group(1) for m in matrix if m}
    versions = {m.group(2) for m in matrix if m}
    return len(contexts), len(systems), len(versions)


def experimental_versions(grader: pathlib.Path) -> str:
    """Версии Python, помеченные в матрице грейдера экспериментальными.

    В ruleset их нет по устройству: комбинации идут под ``continue-on-error`` и
    блокировать мерж не должны. Значит единственный источник — сама матрица.
    """
    ci = (grader / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    found = re.findall(r'python-version:\s*"([^"]+)",\s*experimental:\s*true', ci)
    return " · ".join(sorted(set(found)))


def release_count() -> int:
    return len(_api(f"/repos/{REPO}/releases?per_page=100"))


def count_rules(playbook: pathlib.Path) -> int:
    """Число правил в каталоге: один файл — одно правило."""
    return len(list((playbook / "rules/ru").glob("[0-9]*.md")))


def render(tiles: list[tuple[str, str]], dark: bool) -> str:
    width, height, gap = 1000, 118, 18
    tile_w = (width - gap * (len(tiles) - 1)) // len(tiles)
    if dark:
        card, stroke, num, lab = "#0D1117", "#30363D", "#F0F6FC", "#7D8590"
    else:
        card, stroke, num, lab = "#FFFFFF", "#D0D7DE", "#1F2328", "#636C76"

    label = ", ".join(f"{value} {name}" for value, name in tiles)
    out = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{label}">',
        '<defs><linearGradient id="a" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%" stop-color="#58A6FF"/><stop offset="100%" stop-color="#7EE787"/>'
        "</linearGradient></defs>",
    ]
    for index, (value, name) in enumerate(tiles):
        x = index * (tile_w + gap)
        font_size = 46 if len(value) <= 3 else 40
        out.append(
            f"  <g>\n"
            f'    <rect x="{x + 0.5}" y="0.5" width="{tile_w - 1}" height="{height - 1}" '
            f'rx="14" fill="{card}" stroke="{stroke}"/>\n'
            f'    <rect x="{x + 22}" y="22" width="44" height="4" rx="2" fill="url(#a)"/>\n'
            f'    <text x="{x + tile_w / 2:.0f}" y="73" fill="{num}" '
            f'font-family="{FONT}" font-size="{font_size}" font-weight="800" '
            f'text-anchor="middle" letter-spacing="-1">{value}</text>\n'
            f'    <text x="{x + tile_w / 2:.0f}" y="98" fill="{lab}" font-family="{FONT}" '
            f'font-size="15.5" font-weight="600" text-anchor="middle">{name}</text>\n'
            f"  </g>"
        )
    return "\n".join(out) + "\n</svg>\n"


def aria_label(svg: pathlib.Path) -> str:
    """Подпись картинки, как её объявляет сама картинка.

    У разделителей ``aria-label`` нет намеренно — это декорация, и alt у неё
    пустой.
    """
    match = re.search(r'aria-label="([^"]*)"', svg.read_text(encoding="utf-8"))
    return match.group(1) if match else ""


def sync_alt(text: str) -> tuple[str, int]:
    """Приводит alt каждой картинки витрины к её же ``aria-label``.

    Alt правится вместе с картинкой не для порядка: он невидим глазу, но именно
    его читают скринридеры и текстовые выгрузки страницы. Разошедшись с
    картинкой, он врёт тише всех — «32 checks per PR» прожили в alt на мерж
    дольше, чем на самом изображении. Поэтому подпись у картинки одна, и
    хранится она внутри SVG.
    """
    def replace(match: re.Match[str]) -> str:
        label = aria_label(ROOT / "assets" / f"{match.group('name')}.svg").replace('"', "'")
        return f"{match.group('head')}{label}{match.group('tail')}"

    return re.subn(
        r'(?P<head><img src="\./assets/(?P<name>[a-z-]+)\.svg" alt=")[^"]*(?P<tail>")',
        replace,
        text,
    )


def patch_readme(values: dict[str, object]) -> None:
    """Обновляет числа между маркерами ``<!--m:key-->`` … ``<!--/m:key-->``.

    Если маркер не нашёлся, скрипт падает, а не проходит молча: ``re.sub`` без
    совпадения ничего не делает и возвращает тот же текст — витрина замерла бы,
    workflow отчитался бы «числа не изменились», и отказ выглядел бы как
    отсутствие изменений. Ровно от этого молчания скрипт и написан.
    """
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")

    missing = []
    for key, value in values.items():
        text, count = re.subn(
            rf"(<!--m:{key}-->).*?(<!--/m:{key}-->)",
            lambda m, v=value: f"{m.group(1)}{v}{m.group(2)}",
            text,
            flags=re.S,
        )
        if not count:
            missing.append(key)
    if missing:
        raise SystemExit(f"в README нет маркеров: {', '.join(missing)}")

    # Сначала считаем картинки грубым выражением («любой <img> на assets/»),
    # потом строгим проставляем alt — и сверяем счётчики. Иначе защита
    # проверяет саму себя: строгое выражение не видит поехавшую разметку, не
    # находит её — и молча докладывает, что всё проставлено.
    expected = len(re.findall(r"<img[^>]*assets/[a-z-]+\.svg", text))
    text, patched = sync_alt(text)
    if patched != expected:
        raise SystemExit(f"alt проставлен у {patched} картинок из {expected} — разметка изменилась")

    readme.write_text(text, encoding="utf-8")


def main() -> int:
    grader = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "grader")
    playbook = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "playbook")
    for path, marker in ((grader, "tests"), (playbook, "rules/ru")):
        if not (path / marker).is_dir():
            print(f"нет клона в {path}/ — ожидается каталог {marker}/", file=sys.stderr)
            return 1

    tests = count_tests(grader)
    modules = count_test_modules(grader)
    checks = checks_per_pr()
    required, systems, versions = protection_facts()
    experimental = experimental_versions(grader)
    releases = release_count()
    coverage = badge("coverage-combined")
    glossary = badge("glossary").split()[0]
    open_for_newcomers = good_first_issues()
    rules = count_rules(playbook)

    # Числа с плитки (tests, coverage, checks) в тексте README не повторяются:
    # одно число — одно место. Текстовому читателю они достаются через alt
    # картинки, а его тоже проставляет этот скрипт — см. sync_alt.
    plate = [(f"{tests // 1000}000+", "tests"), (coverage, "coverage (all OS)"), (str(checks), "checks per PR")]
    values = {
        "modules": modules,
        "required": required,
        "os": systems,
        "py": versions,
        "exp": experimental,
        "releases": releases,
        "glossary": glossary,
        "gfi": open_for_newcomers,
        "rules": rules,
    }
    print(" · ".join(f"{name}: {value}" for value, name in plate))
    print(" · ".join(f"{key}: {value}" for key, value in values.items()))

    # Ноль допустим ровно у одной метрики: пустой пул задач для новичка — это
    # состояние трекера, а не сбой сборки. У остальных ноль означает, что
    # источник не ответил, и переписывать витрину по нему нельзя.
    empty = [
        key
        for key, value in {**values, **{name: value for value, name in plate}}.items()
        if not str(value).strip() or (str(value) == "0" and key != "gfi")
    ]
    if empty:
        print(f"метрика не собралась ({', '.join(empty)}) — ничего не переписываю", file=sys.stderr)
        return 1

    for theme, dark in (("dark", True), ("light", False)):
        (ROOT / f"assets/metrics-{theme}.svg").write_text(render(plate, dark), encoding="utf-8")
    patch_readme(values)
    print("assets/metrics-*.svg и README обновлены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
