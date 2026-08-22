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


def main() -> int:
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
