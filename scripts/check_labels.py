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
# Метки конвейера классификацией не считаются: они говорят, что делать с
# изменением, а не что это за изменение.
PIPELINE = {"hold"}


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


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    number = int(sys.argv[1])

    pull = _api(f"/repos/{REPO}/pulls/{number}")
    labels = {label["name"] for label in pull["labels"]}
    content = labels - PIPELINE
    if content:
        print(f"PR #{number}: классификация есть — {', '.join(sorted(content))}")
        return 0

    available = sorted({label["name"] for label in _api(f"/repos/{REPO}/labels?per_page=100")} - PIPELINE)
    complaint = (
        f"PR #{number} без метки содержания. Метка — вход механизма, а не украшение:\n"
        f"по ней видно зону работы до чтения различий.\n"
        f"Доступные: {', '.join(available)}\n"
        f"Метки конвейера ({', '.join(sorted(PIPELINE))}) классификацией не считаются."
    )
    if pull["user"]["login"].lower() != OWNER.lower():
        print(f"::warning::{complaint}")
        print("Автор — не владелец репозитория: правило мягкое, метку проставит принимающий.")
        return 0
    print(f"::error::{complaint}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
