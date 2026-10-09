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

ПЛЮС ФОРМА ЗАДАЧ (028). Открытая задача, которая ведёт три и более пункта
прозой и ни одной галочки, названа отдельной строкой: её состояние приходится
вычитывать, а не считать. Это счёт, а не приказ — перевести пункты в
галочки решает человек. Приём перенят у Engineering-Pipeline-Mechanisms
(``scripts/task_shape.py::without_a_checklist``) вместе с его границами:
задача с галочками, эпик с подзадачами и задача, которую ведёт механизм, —
не кандидаты. Звать его нельзя: он держится на внутренних модулях соседа.

Исходы: 0 — план напечатан; 1 — не бывает: план не находка, красить нечем;
2 — источник не ответил, и это названо: план без трекера — не «трекер пуст».
"""

import json
import re
import sys
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass

import check_bindings
import checks

#: Источники работы по порядку — копия CLAUDE.md § Открытая работа (071).
SOURCES = ("долг по правилам", "задачи трекера", "названные пробелы")

#: Названные пробелы — документы, а не счётчик: их читают, а не считают.
GAPS = ".rules/README.md, .rules/roles.md"


#: Пункт перечисления, который НЕ галочка, и сама галочка. Три знака списка:
#: все три законны в Markdown. Нумерованный список не считается — так же, как
#: у соседа: в задачах витрины им пишут шаги рассуждения, а не единицы работы.
BULLET = re.compile(r"^\s{0,3}[-*+]\s+(?!\[[ xX]\])\S")
CHECKBOX = re.compile(r"^\s{0,3}[-*+]\s+\[[ xX]\]")
#: С какого числа пунктов проза перестаёт быть описанием — из буквы правила.
FROM_ITEMS = 3
#: Задачу ведёт механизм: её тело пересобирается заходом, и галочка, поставленная
#: рукой, исчезнет на следующем. Сторожа витрины открывают её от бота и ставят
#: первой строкой метку, по которой находят её снова.
KEPT_MARK = re.compile(r"\A<!-- [\w-]+: не удаляйте")


@dataclass(frozen=True, slots=True)
class Task:
    """Открытая задача трекера: номер, заголовок, тело, кто её ведёт."""

    number: int
    title: str
    body: str = ""
    machine: bool = False
    children: int = 0


def prose_items(task: Task) -> int:
    """Пункты прозой у задачи, которая чек-листа не ведёт; 0 — не кандидат (028)."""
    lines = task.body.splitlines()
    if (task.machine or task.children or KEPT_MARK.match(task.body)
            or any(CHECKBOX.match(line) for line in lines)):
        return 0
    counted = sum(1 for line in lines if BULLET.match(line))
    return counted if counted >= FROM_ITEMS else 0


def plan(unreviewed: int, unheld: int, issues: list[Task] | None) -> list[str]:
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
        head = ", ".join(f"#{task.number} {checks.clip(task.title, 48)}" for task in issues[:3])
        more = f" и ещё {len(issues) - 3}" if len(issues) > 3 else ""
        lines.append(f"  {mark} {SOURCES[1]}: открыто {len(issues)}" + (f" — {head}{more}" if issues else ""))
        prose = sorted(((prose_items(task), task.number) for task in issues), reverse=True)
        named = [f"#{number} ({count})" for count, number in prose if count]
        if named:
            lines.append(f"      пункты прозой, а не галочками (028): {', '.join(named)} — "
                         f"состояние вычитывается, а не считается")

    mark = "→" if first == "gaps" else " "
    lines.append(f"  {mark} {SOURCES[2]}: {GAPS}")
    return lines


def open_issues() -> list[Task]:
    """Открытые задачи витрины, без изменений: площадка отдаёт их тем же списком."""
    items = checks.rest_list("/repos/ArtVsMark/ArtVsMark/issues?state=open&per_page=100")
    return sorted((Task(int(item["number"]), str(item.get("title") or ""),
                        str(item.get("body") or ""),
                        checks.machine_made(str((item.get("user") or {}).get("login") or "")),
                        int((item.get("sub_issues_summary") or {}).get("total") or 0))
                   for item in items if isinstance(item, dict) and "pull_request" not in item),
                  key=lambda task: task.number)


def main(argv: list[str] | None = None,
         fetch: Callable[[], list[Task]] = open_issues) -> int:
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
        issues: list[Task] | None = fetch()
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
        ("долг есть — он первый, даже при задачах", (1, 0, [Task(5, "a")]), SOURCES[0]),
        ("долга нет, задачи есть", (0, 0, [Task(5, "a")]), SOURCES[1]),
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

    # Форма задач (028) — обе стороны: проза от трёх пунктов названа; галочки,
    # эпик, задача механизма, два пункта и нумерованный список — нет.
    prose = "- a\n- b\n* c\n"
    shape_cases = [
        ("три пункта прозой — кандидат", Task(1, "x", prose), 3),
        ("два пункта — чек-лист дороже предмета", Task(1, "x", "- a\n- b\n"), 0),
        ("есть галочка — чек-лист уже ведётся", Task(1, "x", prose + "- [x] d\n"), 0),
        ("эпик с подзадачами — счёт ведёт трекер", Task(1, "x", prose, children=2), 0),
        ("задачу открыл бот", Task(1, "x", prose, machine=True), 0),
        ("задача с меткой сторожа", Task(1, "x", "<!-- main-red: не удаляйте -->\n" + prose), 0),
        ("нумерованный список — не пункты", Task(1, "x", "1. a\n2. b\n3. c\n"), 0),
    ]
    for name, task, expected in shape_cases:
        got = prose_items(task)
        if got != expected:
            broken.append(f"форма задачи, {name}: ждали {expected}, вышло {got}")
        print(f"  {'верно' if got == expected else 'СБОЙ '} — форма задачи: {name}")
    said = plan(0, 0, [Task(7, "x", prose), Task(8, "y", "- [ ] a\n")])
    if not any("(028): #7 (3)" in line for line in said) or any("#8 (" in line for line in said):
        broken.append(f"план не назвал задачу с прозой или назвал лишнюю: {said}")

    # Исходы прогоняются вызовом main, а не только функцией (186).
    def silent() -> list[Task]:
        raise urllib.error.URLError("подделка: сеть закрыта")

    if main([], fetch=silent) != 2:
        broken.append("трекер не ответил, а main вернул не 2")
    if main([], fetch=lambda: [Task(1, "x")]) != 0:
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
