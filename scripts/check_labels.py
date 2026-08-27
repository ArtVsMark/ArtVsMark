#!/usr/bin/env python3
"""Проверяет, что у PR есть классификация — метка содержания.

Замер, из-за которого проверка появилась: у всех шести PR витрины меток не было
ни одной, притом что у задач, заведённых владельцем, они стояли. Это дословно
признак из правила 064: метки исправно стоят там, где их ставит машина, и
отсутствуют там, где их ставит человек.

Метки здесь двух разных природ, и смешивать их нельзя:

* **содержания** — что за работа: ``bug``, ``enhancement``, ``documentation``,
  ``github_actions``, ``dependencies``. Ставит автор, и хотя бы одна обязательна;
* **конвейера** — что с ней делать: ``hold`` останавливает слияние. Ставит
  человек или автоматика по ходу дела, и требовать её от автора нельзя.

Список содержания — ``CONTENT`` ниже, и проверка читает именно его. Первая
редакция перечисляла те же пять меток здесь, в докстроке, а в коде считала
классификацией **всё, что не** ``hold``. Разрешительный список был написан и не
стал кодом: из двенадцати меток репозитория гейт пропускал семь, включая
``question``, ``wontfix`` и ``invalid``, — и пять из них умолчания GitHub, то
есть дыра стояла открытой с первого дня (правило 068).

Вторая половина проверки — полнота, а не непустота (правило 128). Метка
содержания это обязательное поле, чей предмет **множество**: изменение трогает и
конвейер, и документацию. Зона, выводимая из списка изменённых файлов, требует
своей метки; всё, что из диффа не выводится, остаётся решением автора, потому
что проверка полноты по воображаемому множеству вырождается в шум.

Для чужого участника правило мягкое: он не обязан знать местную систему меток,
поэтому ему предупреждение, а недостающее проставляет принимающий.

Запуск::

    python scripts/check_labels.py 20
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

REPO = os.environ.get("SHOWCASE_REPO", "ArtVsMark/ArtVsMark")
OWNER = REPO.split("/")[0]
API = "https://api.github.com"

# Разрешительный список: классификацией считается только то, что здесь.
# Запретительный («всё, кроме hold») не знает о метках, которые появятся
# завтра, — и не знал о семи, которые уже были.
CONTENT = frozenset({"bug", "enhancement", "documentation", "github_actions", "dependencies"})
# Метки конвейера классификацией не считаются: они говорят, что делать с
# изменением, а не что это за изменение. Список нужен, чтобы не жаловаться на
# них как на постороннее.
PIPELINE = frozenset({"hold"})

#: Тип коммита по Conventional Commits — метка содержания. Нужна прогону
#: `open-pr.yml`: изменение открывается пушем, и без метки классификация красная
#: с первой секунды, а красное как фон обесценивает красное настоящее.
#:
#: Таблица живёт здесь, а не выражением в шаге прогона, по той же причине, по
#: которой там же оказался разбор исходов: шаг нельзя прогнать тем, что он
#: обязан отвергнуть, а функцию можно. Предмет тот же, что у гейта, — метки
#: содержания, и второй копии списка не заводится (правило 090).
SUBJECT_LABEL: tuple[tuple[str, str], ...] = (
    ("fix", "bug"),
    ("feat", "enhancement"),
    ("docs", "documentation"),
    ("ci", "github_actions"),
    ("build", "github_actions"),
    ("deps", "dependencies"),
)


def label_for_subject(subject: str) -> str:
    """Метка содержания по заголовку коммита, либо пустая строка.

    Пустая строка — не «нет метки», а «не разобрано»: вызывающий обязан сказать
    это вслух, а не поставить метку наугад. Неверная метка хуже отсутствующей —
    по ней зону работы читают до диффа (правило 064).
    """
    head = subject.strip().split(":", 1)[0].strip().lower()
    # Область в скобках и восклицательный знак ломающего изменения к типу не
    # относятся: `feat(profile)!` — это `feat`.
    kind = re.split(r"[(!]", head, maxsplit=1)[0].strip()
    return next((label for prefix, label in SUBJECT_LABEL if kind == prefix), "")

# Зоны, выводимые из диффа: предикат по пути — метка, без которой изменение в
# этой зоне классифицировано не полностью.
#
# Список короткий намеренно. «Правка *.md требует documentation» сюда не входит:
# журнал пополняется тем же заходом, что и правка, поэтому такое требование
# срабатывало бы почти на каждом PR и перестало бы что-либо значить. Вместо
# этого documentation требуется, когда изменение целиком документарное, — см.
# derive_zones.
ZONES = (
    (lambda path: path.startswith(".github/workflows/"), "github_actions"),
    (lambda path: path == ".github/dependabot.yml", "dependencies"),
)


def _api(path: str) -> object:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    request = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def changed_files(number: int) -> list[str]:
    """Все изменённые файлы, а не первая страница.

    Страница берётся по сотне, и остановиться на первой значило бы считать
    полноту по обрезанной выдаче, не сказав об этом (правило 016). Здесь обрыв
    невозможен: страницы читаются до пустой.
    """
    files: list[str] = []
    page = 1
    while True:
        batch = _api(f"/repos/{REPO}/pulls/{number}/files?per_page=100&page={page}")
        files += [entry["filename"] for entry in batch]
        if len(batch) < 100:
            return files
        page += 1


def is_doc(path: str) -> bool:
    return path.endswith(".md") or path.startswith(".rules/")


def derive_zones(paths: list[str]) -> set[str]:
    """Метки, которых требует сам дифф.

    Пустой список файлов зон не даёт — но это «дифф не прочитан», а не «зон
    нет»: решение по пустому множеству принимать нельзя (правило 010). Пустоту
    разбирает вызывающий, здесь она честно даёт пустой ответ.
    """
    zones = {label for path in paths for matches, label in ZONES if matches(path)}
    if paths and all(is_doc(path) for path in paths):
        zones.add("documentation")
    return zones


def verdict(labels: set[str], files: list[str]) -> tuple[list[str], set[str], set[str]]:
    """Претензии к классификации, а также найденные метки и зоны.

    Вынесено из ``main``, чтобы проверять на подставных наборах, не ходя в API.
    """
    content = labels & CONTENT
    unknown = labels - CONTENT - PIPELINE
    zones = derive_zones(files)
    missing = zones - labels

    complaints = []
    if not content:
        stray = (f" Стоят посторонние: {', '.join(sorted(unknown))} —"
                 " классификацией они не считаются." if unknown else "")
        complaints.append(
            f"нет метки содержания. Допустимые: {', '.join(sorted(CONTENT))}.{stray}"
        )
    if missing:
        complaints.append(
            f"изменение трогает зону, для которой не проставлена метка: {', '.join(sorted(missing))}."
            f" Выведено из диффа ({len(files)} файлов), а не из общих соображений."
        )
    if not files:
        complaints.append(
            "список изменённых файлов пуст — проверять полноту не по чему."
            " Пустой ответ это «не прочитано», а не «зон нет»."
        )
    return complaints, content, zones


def selftest() -> int:
    """Прогоняет через гейт то, что он обязан отвергнуть и обязан пропустить.

    Правило 140. Здесь оно особенно к месту: этот гейт уже один раз оказался
    обещанием — в докстроке стоял разрешительный список меток, а в коде
    «всё, кроме hold», и семь меток из двенадцати проходили классификацию.
    Читалось при этом правильно с обеих сторон: неверна была только связь.

    Набор двусторонний. Ложный отказ здесь дороже пропуска: гейт, требующий
    метку там, где она не нужна, приучает ставить метки наугад.
    """
    # Файл-нейтраль: правка скрипта своей зоны не требует, поэтому на таких
    # случаях проверяется ровно метка и ничего кроме неё. README.md сюда не
    # годится — изменение целиком из документации требует documentation, и
    # случай начал бы проверять две вещи разом. Первый черновик набора на этом
    # и упал.
    plain = ["scripts/checks.py"]
    cases = [
        ("метка вне списка", {"question"}, plain, True),
        ("hold в одиночку", {"hold"}, plain, True),
        ("умолчание площадки вместо содержания", {"good first issue"}, plain, True),
        ("меток нет вовсе", set(), plain, True),
        ("правка прогона без github_actions", {"bug"}, [".github/workflows/pr-check.yml"], True),
        ("правка dependabot без dependencies", {"bug"}, [".github/dependabot.yml"], True),
        ("изменение целиком из документации без documentation", {"bug"},
         ["HISTORY.md", ".rules/roles.md"], True),
        ("дифф не прочитан — пустой список файлов", {"bug"}, [], True),
        ("метка содержания и зона совпали", {"bug", "github_actions"},
         [".github/workflows/pr-check.yml"], False),
        ("изменение целиком из документации", {"documentation"}, ["HISTORY.md", ".rules/roles.md"], False),
        ("hold рядом с содержанием не мешает", {"bug", "hold"}, plain, False),
        ("правка скрипта своей зоны не требует", {"bug"}, plain, False),
        ("смешанный дифф: документация не требуется", {"bug"},
         ["HISTORY.md", "scripts/checks.py"], False),
    ]
    broken = []
    for name, labels, files, must_reject in cases:
        complaints, _, _ = verdict(labels, files)
        if bool(complaints) is not must_reject:
            broken.append(f"{name}: ожидалось {'отказ' if must_reject else 'пропуск'}, вышло наоборот")
        print(f"  {'отвергнут' if complaints else 'пропущен '} — {name}")

    # Отказ обязан НАЗЫВАТЬ предмет: «метка вне списка» без её имени и «не та
    # зона» без имени зоны — это отказ, по которому нечего чинить (правило 083).
    named, _, _ = verdict({"question"}, plain)
    if not any("question" in line for line in named):
        broken.append("отказ на посторонней метке не называет её поимённо")
    zoned, _, _ = verdict({"bug"}, [".github/workflows/pr-check.yml"])
    if not any("github_actions" in line for line in zoned):
        broken.append("отказ на непокрытой зоне не называет недостающую метку")

    # Вывод метки по заголовку — вход прогона `open-pr.yml`, и ошибка здесь
    # ставит НЕВЕРНУЮ метку, то есть врёт о зоне работы. Проверяется обеими
    # сторонами: что разбирается и что осознанно не разбирается.
    subjects = [
        ("fix(automerge): исчерпанный бюджет запросов", "bug"),
        ("feat(profile): плитка называет флагман", "enhancement"),
        ("docs(profile): подтверждение прогоном", "documentation"),
        ("ci: закрепить действия по SHA", "github_actions"),
        ("build(deps): поднять actions/checkout", "github_actions"),
        ("deps: поднять setup-python", "dependencies"),
        ("feat!: ломающее изменение", "enhancement"),
        ("fix(profile)!: и область, и восклицательный знак", "bug"),
        ("  FEAT(profile): регистр и отступы  ", "enhancement"),
        ("refactor(scripts): тип вне таблицы", ""),
        ("правка без типа вовсе", ""),
        ("", ""),
        ("fixture: не fix, а другое слово целиком", ""),
    ]
    for subject, expected in subjects:
        got = label_for_subject(subject)
        if got != expected:
            broken.append(f"заголовок {subject!r}: ожидалась метка {expected!r}, вышла {got!r}")
        print(f"  {got or '— не разобрано':<14} — {subject.strip()[:52] or '(пустой заголовок)'}")

    # Вывод обязан оставаться внутри списка меток содержания: разойдись он с
    # ним — прогон ставил бы метку, которую этот же гейт отвергает.
    stray = {label for _, label in SUBJECT_LABEL} - CONTENT
    if stray:
        broken.append(f"таблица заголовков выводит метки вне CONTENT: {sorted(stray)}")

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: гейт отвергает то, что обязан, называет предмет и выводит метку по заголовку")
    return 0


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()
    if "--label-for-subject" in sys.argv[1:]:
        # Вход прогона `open-pr.yml`. Печатается только метка: пусто значит
        # «не разобрано», и решение, что с этим делать, принимает вызывающий.
        i = sys.argv.index("--label-for-subject")
        print(label_for_subject(sys.argv[i + 1] if len(sys.argv) > i + 1 else ""))
        return 0
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    number = int(sys.argv[1])

    pull = _api(f"/repos/{REPO}/pulls/{number}")
    labels = {label["name"] for label in pull["labels"]}
    complaints, content, zones = verdict(labels, changed_files(number))

    if not complaints:
        covered = f"; зоны из диффа покрыты: {', '.join(sorted(zones))}" if zones else ""
        print(f"PR #{number}: классификация есть — {', '.join(sorted(content))}{covered}")
        return 0

    complaint = (
        f"PR #{number}: классификация неполна. Метка — вход механизма, а не украшение:\n"
        f"по ней видно зону работы до чтения различий.\n"
        + "\n".join(f"— {line}" for line in complaints)
        + f"\nМетки конвейера ({', '.join(sorted(PIPELINE))}) классификацией не считаются."
    )
    if pull["user"]["login"].lower() != OWNER.lower():
        print(f"::warning::{complaint}")
        print("Автор — не владелец репозитория: правило мягкое, метку проставит принимающий.")
        return 0
    print(f"::error::{complaint}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
