#!/usr/bin/env python3
"""Воскресшая ветка изменения не открывает (правило 202).

ИНЦИДЕНТ РОДИЛСЯ ЗДЕСЬ. 8 сентября изменение #180 слилось с уплотнением, пока
окно писало починку в ту же ветку ``agent/neighbours-gate``. Площадка удалила
ветку при слиянии, пуш воссоздал её с тремя коммитами — двумя уже слитыми и
одним новым, — и ``agent-pr`` открыл #181 на все три. С его стороны это была
обычная ветка, разошедшаяся с ``main``: отличить «работа новая» от «работа
слита, ветка воскресла» ему было нечем. Вывод пуша не различает тоже —
``* [new branch]`` печатается в обоих случаях.

ПРИЗНАК — ГОЛОВА СЛИТОГО ИЗМЕНЕНИЯ ТОЙ ЖЕ ВЕТКИ ЛЕЖИТ В ИСТОРИИ НЫНЕШНЕЙ,
А В ИСТОРИИ ``main`` — НЕТ.
Спрашивается площадка, а не память: слитые изменения с этой головной веткой
и их головы. Воскрешение везёт старые коммиты целиком, и голова слитого
оказывается предком новой головы. Проверено на самом инциденте, а не
рассуждением: голова #180 (``1a34f7c57f``) — предок головы #181
(``597aa8b5b5``), то есть #181 здесь бы не открылось.

ПОЧЕМУ НЕ «ВЕТКА С ТАКИМ ИМЕНЕМ УЖЕ СЛИВАЛАСЬ». Ветку, начатую заново от
свежего ``main`` под тем же именем, так отвергли бы зря (051): её история
голову слитого изменения не содержит — после уплотнения та предком ``main``
не является. Признак разводит оба случая, имя — нет.

СЛИТОЕ БЕЗ УПЛОТНЕНИЯ — НЕ ВОСКРЕШЕНИЕ. Ранние изменения витрины (#4–#9 и
#33–#41) слиты коммитом слияния, и их головы лежат в ``main`` как есть:
ветка, начатая от ``main`` под тем же именем, содержит такую голову законно.
Поэтому признак — голова слитого в истории ветки И НЕ в истории ``main``.
Правило выводит этот случай из применимости само: без уплотнения диапазон
после слияния пуст. Первый черновик признака сужения не имел и отверг бы
такую ветку — нашлось перебором соседей, а не прогоном.

ПОЧЕМУ НЕ «КОММИТЫ УЖЕ ЛЕЖАТ В MAIN СОДЕРЖИМЫМ». После уплотнения коммиты
ветки в ``main`` не лежат вовсе — лежит один чужой коммит с их суммой, и
сравнивать пришлось бы содержимое. Продолжение, правящее те же строки,
сделало бы такое сравнение неверным в обе стороны.

ЧЕГО ЗДЕСЬ НЕТ, И ЭТО НАЗВАНО. Вторая половина правила — сторож у пушущего:
спросить до пуша, жива ли ветка на площадке. Это хук окна, а хуков у витрины
нет ни одного; первый заводится решением владельца, а не попутно. Конвейерная
половина правилом названа надёжнее: она стоит там, где принимается решение,
и не зависит от того, запустил ли автор проверку. Изменение, открытое мимо
``agent-pr`` руками, этот прогон тоже не видит.

Запуск::

    python scripts/resurrected.py <ветка> <голова>

Исходы: 0 — ветка не воскресла; 1 — воскресла, изменение не открывать;
2 — проверка не отработала (площадка или git не ответили).
"""

import os
import subprocess
import sys
import urllib.error
import urllib.parse
from collections.abc import Callable

import checks

REPO = os.environ.get("GITHUB_REPOSITORY", "ArtVsMark/ArtVsMark")

#: Общая ветка, как её видит прогон: agent-pr забирает её шагом раньше.
BASE = "origin/main"


def merged_heads(branch: str, repo: str = REPO) -> list[tuple[int, str]]:
    """Слитые изменения с этой головной веткой: (номер, голова).

    Площадка находит их и по УДАЛЁННОЙ ветке — имя головы хранится в самом
    изменении. Проверено 29 сентября: для ``agent/neighbours-gate`` она
    отдаёт и слитое #180, и воскресшее #181.
    """
    owner = repo.split("/", 1)[0]
    head = urllib.parse.quote(f"{owner}:{branch}", safe=":/")
    pulls = checks.rest_list(f"/repos/{repo}/pulls?state=closed&head={head}&per_page=100")
    return [(pull["number"], pull["head"]["sha"]) for pull in pulls if pull.get("merged_at")]


def is_ancestor(sha: str, head: str) -> bool:
    """Коммит ``sha`` лежит в истории ``head``.

    Коммита нет локально — значит, и в истории головы его нет: прогон берёт
    историю целиком (``fetch-depth: 0``), и всё, что достижимо из головы,
    приехало вместе с ней. Прочие отказы git не глотаются — это третий исход.
    """
    present = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                             capture_output=True).returncode == 0
    if not present:
        return False
    answer = subprocess.run(["git", "merge-base", "--is-ancestor", sha, head],
                            capture_output=True, text=True, encoding="utf-8")
    if answer.returncode not in (0, 1):
        raise subprocess.CalledProcessError(answer.returncode, answer.args,
                                            answer.stdout, answer.stderr)
    return answer.returncode == 0


def resurrected(merged: list[tuple[int, str]], in_head: Callable[[str], bool],
                in_base: Callable[[str], bool]) -> list[int]:
    """Номера слитых изменений, чья голова в истории ветки и не в истории ``main``."""
    return sorted(number for number, sha in merged if in_head(sha) and not in_base(sha))


def selftest() -> int:
    """Признак отвергает воскрешение и пропускает ветку, начатую заново."""
    history = {"old", "older", "merged-as-is"}
    main_history = {"merged-as-is"}
    cases = [
        ("ветка воскресла со слитыми коммитами", [(180, "old")], [180]),
        ("ветку начали заново от main — голова слитого не в истории", [(180, "gone")], []),
        ("слитых изменений у ветки не было", [], []),
        ("из двух слитых в истории одно", [(90, "gone"), (180, "old")], [180]),
        ("оба слитых в истории — названы оба", [(180, "old"), (170, "older")], [170, 180]),
        # Сосед, найденный перебором (#4–#9, #33–#41): слито без уплотнения,
        # голова лежит в main как есть — ветка от main содержит её законно.
        ("слито без уплотнения — голова и в main", [(9, "merged-as-is")], []),
        ("старое слияние без уплотнения и свежее воскрешение",
         [(9, "merged-as-is"), (180, "old")], [180]),
    ]
    broken: list[str] = []
    for name, merged, expected in cases:
        got = resurrected(merged, lambda sha: sha in history, lambda sha: sha in main_history)
        if got != expected:
            broken.append(f"{name}: ожидалось {expected}, вышло {got}")
        print(f"  {'отвергнута' if got else 'пропущена '} — {name}")

    # Отказ называет номер слитого изменения и путь починки (158): «ветка
    # воскресла» без того и другого отправляет искать самому.
    said = refusal("agent/x", [180])
    if not ("#180" in said and "origin/main" in said and "cherry-pick" in said):
        broken.append(f"отказ не называет слитое изменение или путь починки: {said}")

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: воскрешение отвергается, ветка, начатая заново, — нет")
    return 0


def refusal(branch: str, numbers: list[int]) -> str:
    """Текст отказа: что случилось и как продолжить."""
    merged = ", ".join(f"#{n}" for n in numbers)
    return (f"ветка {branch} воскресла: в её истории голова уже слитого изменения "
            f"{merged}. Изменение не открывается — оно повезло бы слитое второй раз "
            f"(202). Продолжение — новой веткой от свежей общей: git fetch origin main "
            f"&& git checkout -b agent/<новый-слаг> origin/main && git cherry-pick "
            f"<новые коммиты>. Воскресшую ветку удаляет владелец — окну площадка "
            f"отвечает 403")


def main() -> int:
    argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    if len(argv) != 2:
        print("проверка не отработала: нужны ветка и голова", file=sys.stderr)
        return 2
    branch, head = argv
    try:
        hits = resurrected(merged_heads(branch), lambda sha: is_ancestor(sha, head),
                           lambda sha: is_ancestor(sha, BASE))
    except (urllib.error.URLError, OSError, ValueError, KeyError,
            subprocess.SubprocessError) as e:
        print(checks.annotate("error", f"проверка воскрешения не отработала: {e}"))
        return 2
    if hits:
        print(checks.annotate("error", refusal(branch, hits)))
        return 1
    print(f"{branch}: не воскресла — слитых изменений в её истории нет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
