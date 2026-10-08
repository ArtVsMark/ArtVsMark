#!/usr/bin/env python3
"""План окна: источники открытой работы по порядку, первый непустой отмечен.

ЗАЧЕМ (091). Свод называет три источника работы и порядок между ними —
CLAUDE.md § Открытая работа: долг по правилам, затем задачи трекера, затем
названные пробелы. Первый непустой и есть план. До сих пор порядок держался
чтением: окно открывало трекер и брало верхнюю задачу, а долг по правилам
печатался отдельной командой, которую надо было вспомнить.

Здесь порядок собирает машина, а выбирает по-прежнему окно: скрипт не
решает, ЧТО делать внутри источника, — он показывает, какой источник сейчас
первый непустой. Зовёт его хук старта окна (.claude/hooks/session-start.sh),
и строки плана — первое, что окно видит.

СВОЕГО ПОРЯДКА ЗДЕСЬ НЕТ. Три источника и их очерёдность — копия свода, и
она подписана: правка § Открытая работа меняет и SOURCES ниже, иначе план
разойдётся со сводом молча (071).

Исходы: 0 — план напечатан; 1 — не бывает: план не находка, красить нечем;
2 — источник не ответил, и это названо: план без трекера — не «трекер пуст».
"""

import json
import sys
import urllib.error
from collections.abc import Callable

import check_bindings
import checks

#: Источники работы по порядку — копия CLAUDE.md § Открытая работа (071).
SOURCES = ("долг по правилам", "задачи трекера", "названные пробелы")

#: Названные пробелы — документы, а не счётчик: их читают, а не считают.
GAPS = ".rules/README.md, .rules/roles.md"


def plan(unreviewed: int, unheld: int, issues: list[tuple[int, str]] | None) -> list[str]:
    """Строки плана. ``issues`` — None, если трекер не ответил.

    Первый непустой источник помечается стрелкой. Не ответивший трекер не
    считается пустым: стрелка тогда не уходит ниже него, а строка говорит,
    что источник не прочитан (039).
    """
    debt = unreviewed + unheld
    lines = [f"план окна — первый непустой источник и есть план ({' → '.join(SOURCES)}):"]
    first = "debt" if debt else ("issues" if issues is None or issues else "gaps")

    mark = "→" if first == "debt" else " "
    lines.append(f"  {mark} {SOURCES[0]}: не рассмотрено {unreviewed} · держится ничем {unheld}")

    mark = "→" if first == "issues" else " "
    if issues is None:
        lines.append(f"  {mark} {SOURCES[1]}: НЕ ПРОЧИТАНЫ — трекер не ответил, пустым он не считается")
    else:
        head = ", ".join(f"#{number} {checks.clip(title, 48)}" for number, title in issues[:3])
        more = f" и ещё {len(issues) - 3}" if len(issues) > 3 else ""
        lines.append(f"  {mark} {SOURCES[1]}: открыто {len(issues)}" + (f" — {head}{more}" if issues else ""))

    mark = "→" if first == "gaps" else " "
    lines.append(f"  {mark} {SOURCES[2]}: {GAPS}")
    return lines


def open_issues() -> list[tuple[int, str]]:
    """Открытые задачи витрины, без изменений: площадка отдаёт их тем же списком."""
    items = checks.rest_list("/repos/ArtVsMark/ArtVsMark/issues?state=open&per_page=100")
    return sorted((int(item["number"]), str(item.get("title", "")))
                  for item in items if isinstance(item, dict) and "pull_request" not in item)


def main(argv: list[str] | None = None,
         fetch: Callable[[], list[tuple[int, str]]] = open_issues) -> int:
    if "--selftest" in (sys.argv[1:] if argv is None else argv):
        return selftest()
    try:
        rules = json.loads(check_bindings.BINDINGS.read_text(encoding="utf-8"))["rules"]
    except (OSError, ValueError, KeyError) as e:
        print(checks.annotate("warning", f"план не собран: ответ каталогу не прочитан — {e}"),
              file=sys.stderr)
        return 2
    unreviewed, unheld = check_bindings.debt(rules)
    try:
        issues: list[tuple[int, str]] | None = fetch()
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        issues = None
        reason = str(e)
    for line in plan(unreviewed, unheld, issues):
        print(line)
    if issues is None:
        print(checks.annotate("warning", f"трекер не ответил: {checks.clip(reason, 120)}"),
              file=sys.stderr)
        return 2
    return 0


def selftest() -> int:
    """Двусторонний набор (140): стрелка у первого непустого, а не у первого."""
    broken: list[str] = []
    cases = [
        ("долг есть — он первый, даже при задачах", (1, 0, [(5, "a")]), SOURCES[0]),
        ("долга нет, задачи есть", (0, 0, [(5, "a")]), SOURCES[1]),
        ("долга нет, задач нет — пробелы", (0, 0, []), SOURCES[2]),
        ("трекер не ответил — пустым не считается", (0, 0, None), SOURCES[1]),
        ("держится ничем — тоже долг", (0, 2, []), SOURCES[0]),
    ]
    for name, args, expected in cases:
        marked = [line for line in plan(*args) if line.lstrip().startswith("→")]
        right = len(marked) == 1 and expected in marked[0]
        if not right:
            broken.append(f"{name}: ожидалась стрелка у «{expected}», вышло {marked}")
        print(f"  {'верно' if right else 'СБОЙ '} — {name}")

    # Исходы прогоняются вызовом main, а не только функцией (186).
    def silent() -> list[tuple[int, str]]:
        raise urllib.error.URLError("подделка: сеть закрыта")

    if main([], fetch=silent) != 2:
        broken.append("трекер не ответил, а main вернул не 2")
    if main([], fetch=lambda: [(1, "x")]) != 0:
        broken.append("трекер ответил, а main вернул не 0")

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: стрелка стоит у первого непустого источника")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
