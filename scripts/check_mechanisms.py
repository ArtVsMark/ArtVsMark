#!/usr/bin/env python3
"""Механизмы витрины держат то, что объявили, — и объявляют то, чего не держат.

ЗАЧЕМ. Замер по всем действующим вердиктам показал: у десяти из семидесяти шести
не бежит ничего. Решение владельца — всё, что можно сделать механическим,
делается механическим. Этот гейт забирает четыре таких правила разом, потому что
у них общий предмет: **объявленное сверяется с сделанным**.

Что проверяется и какое правило этим закрывается:

* **039 — три исхода, а не два.** У каждого скрипта витрины в докстроке
  объявлены исходы, и объявлены все три. Скрипт, обещающий «0 чисто · 1 находки»
  и молчащий про «не отработало», склеивает находку с поломкой — а различать их
  и есть смысл правила;

* **057 — непроверяемое названо поимённо.** Вердикт со статусом `active` и
  механизмом `none` обязан СКАЗАТЬ, почему механизма нет. Без этого «нечем
  проверить» и «не дошли руки» выглядят одинаково, и очередь на гейты
  превращается в свалку. Здесь правило впервые применяется к самому ответу
  каталогу, а не к прозе витрины;

* **011 — расписание вместо опроса.** В шагах прогонов нет циклов ожидания:
  `sleep` в цикле означает, что прогон держит исполнителя и опрашивает чужой
  сервер вместо того, чтобы дождаться события или расписания;

* **147 — у отменяющего переключателя есть адресат.** `open-pr.yml` будится на
  ЛЮБОЙ рабочей ветке (`branches-ignore`), а не по имени. Переключатель по имени
  отменяет операцию молча: у соседа правило пролежало сутки на ветке без единого
  прогона, потому что префикс не совпал.

ЧЕГО ЭТОТ ГЕЙТ НЕ ДЕЛАЕТ. Он не судит, ВЕРНА ли причина в вердикте, — только
что она названа. Отличить «нечем проверить» от отговорки машина не может, и
делать вид, что может, значило бы получить зелёное вокруг ложного основания
(правило 146).

Исходы: 0 — чисто; 1 — есть находки; 2 — проверка не отработала.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
WORKFLOWS = ROOT / ".github/workflows"
BINDINGS = ROOT / ".rules/bindings.json"

#: Строка докстроки, объявляющая исходы. Форма свободная, обязательны три числа.
OUTCOMES = re.compile(r"Исходы?:", re.I)

#: Слова, которыми вердикт признаёт отсутствие механизма. Список нужен, чтобы
#: отличить признание от умолчания: молчание и «нечем» выглядят одинаково, пока
#: их не развели.
GAP_WORDS = ("механизма нет", "механизма не", "гейта нет", "не даётся",
             "пробел", "держится тем", "держится чтением", "не проверяется")

#: Цикл ожидания в шаге прогона. Опрос чужого сервера держит исполнителя и
#: платится минутами за то, что событие отдаёт даром.
POLL_LOOP = re.compile(r"(while\s+(true|:)|for\s+\w+\s+in\s+\$\(seq)[\s\S]{0,400}?\bsleep\b")


def can_fail(source: str) -> bool:
    """У скрипта есть ``main``, способный вернуть ненулевой код.

    Спрашивается именно это, а не наличие ``main``. Модуль без входа исходов не
    имеет вовсе — ``checks.py`` это одна функция свёртки. А разбор, который по
    замыслу ВСЕГДА возвращает ноль и оставляет решение вызывающему, объявляет
    ровно один исход, и требовать от него трёх значило бы требовать неправды:
    так устроен ``gh_outcome.py``. Первый черновик гейта отверг оба — ложный
    отказ, и дороже пропуска (правило 051).
    """
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return any(isinstance(r, ast.Return) and isinstance(r.value, ast.Constant)
                       and r.value.value not in (0, None)
                       for r in ast.walk(node))
    return False


def outcomes_declared(source: str) -> bool:
    """Докстрока объявляет исходы, и объявляет все три."""
    doc = ast.get_docstring(ast.parse(source)) or ""
    head = OUTCOMES.search(doc)
    if not head:
        return False
    return all(code in doc[head.end():] for code in ("0", "1", "2"))


def gap_named(binding: dict) -> bool:
    """Вердикт без механизма называет, почему механизма нет."""
    claim = " ".join(str(binding.get(f, "")) for f in ("where", "why")).lower()
    return any(word in claim for word in GAP_WORDS)


def audit_scripts(sources: dict[str, str]) -> list[str]:
    """Скрипты, чьи докстроки не объявляют трёх исходов."""
    return [f"{name}: докстрока не объявляет три исхода — находка и поломка "
            f"склеиваются в один код возврата (039)"
            for name, source in sorted(sources.items())
            if can_fail(source) and not outcomes_declared(source)]


def audit_gaps(rules: dict[str, dict]) -> list[str]:
    """Действующие вердикты без механизма, не назвавшие причину."""
    return [f"{number}: действует, механизма нет — и не сказано, почему. "
            f"«Нечем проверить» и «не дошли руки» так неотличимы (057)"
            for number, binding in sorted(rules.items())
            if binding.get("status") == "active"
            and binding.get("mechanism") == "none"
            and not gap_named(binding)]


def audit_workflows(sources: dict[str, str]) -> list[str]:
    """Циклы ожидания в шагах и переключатель по имени ветки."""
    found = [f"{name}: цикл ожидания в шаге — прогон опрашивает вместо того, "
             f"чтобы дождаться события или расписания (011)"
             for name, source in sorted(sources.items()) if POLL_LOOP.search(source)]
    opener = sources.get("open-pr.yml", "")
    if opener and "branches-ignore:" not in opener:
        found.append("open-pr.yml: изменение открывается не на любой рабочей ветке. "
                     "Переключатель по имени отменяет операцию МОЛЧА — ни прогона, "
                     "ни красного, ни строки на вкладке (147)")
    return found


#: Хост площадки. Разбирается ВЫЗОВ, а не текст: первый черновик искал строкой и
#: поймал сам себя — образец с адресом внутри регулярного выражения неотличим от
#: обращения, если смотреть на буквы. Разбор дерева эту разницу видит.
API_HOST = "api.github.com"

#: Чужой хост, который на заголовок авторизации отвечает 404 вместо содержимого.
RAW_HOST = "raw.githubusercontent.com"


def _strings(node: ast.AST) -> list[str]:
    """Строковые куски выражения, включая f-строки."""
    return [n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _called(node: ast.Call) -> str:
    """Имя вызываемого: ``urlopen`` и ``urllib.request.urlopen`` одинаково."""
    f = node.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


def audit_calls(sources: dict[str, str]) -> list[str]:
    """Обращения мимо общего входа и авторизация, уходящая на чужой хост."""
    found: list[str] = []
    for name, source in sorted(sources.items()):
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            called, pieces = _called(node), " ".join(_strings(node))
            if called == "urlopen" and API_HOST in pieces:
                found.append(f"{name}: обращение к площадке мимо _api() — у REST один "
                             f"вход, второй заводит второе место, где ломается "
                             f"авторизация и разбор ошибок (001)")
            if called == "_get" and RAW_HOST in pieces:
                unauth = any(k.arg == "authenticated"
                             and getattr(k.value, "value", None) is False
                             for k in node.keywords)
                if not unauth:
                    found.append(f"{name}: {RAW_HOST} читается с заголовком авторизации — "
                                 f"чужой хост отвечает на него 404 вместо содержимого, и "
                                 f"отладка этого стоит дорого: адрес в браузере "
                                 f"открывается, а сборка падает (107)")
    return found


def selftest() -> int:
    """Прогоняет через гейт то, что он обязан отвергнуть и обязан пропустить.

    Набор двусторонний (правило 140). Ложный отказ здесь дороже пропуска вдвойне:
    гейт судит о ФОРМЕ чужих докстрок и вердиктов, и стоит ему заругаться на
    здоровое — его начнут обходить, а обойдённый не держит уже ничего.
    """
    MAIN = '\n\ndef main():\n    return 1\n'
    three = '"""Что делает.\n\nИсходы: 0 — чисто; 1 — находки; 2 — не отработала.\n"""' + MAIN
    two = '"""Что делает.\n\nИсходы: 0 — чисто; 1 — есть находки.\n"""' + MAIN
    none = '"""Что делает, без единого слова про исходы."""' + MAIN
    pure = '"""Свёртка без входа: исходов не имеет вовсе."""\ndef f():\n    return 1\n'
    cases = [
        ("три исхода объявлены", audit_scripts, {"a.py": three}, False),
        ("объявлено два из трёх", audit_scripts, {"a.py": two}, True),
        ("исходы не объявлены вовсе", audit_scripts, {"a.py": none}, True),
        ("скриптов нет", audit_scripts, {}, False),
        ("модуль без входа — исходов не имеет", audit_scripts, {"checks.py": pure}, False),

        ("пробел назван словами", audit_gaps,
         {"001": {"status": "active", "mechanism": "none",
                  "where": "механизма нет и быть не может: возраст окна изнутри не виден"}}, False),
        ("пробел не назван", audit_gaps,
         {"001": {"status": "active", "mechanism": "none", "where": "соблюдается устройством"}}, True),
        ("гейт есть — причина не требуется", audit_gaps,
         {"001": {"status": "active", "mechanism": "gate", "where": "scripts/x.py"}}, False),
        ("вердикт неприменим — не предмет", audit_gaps,
         {"001": {"status": "not-applicable", "mechanism": "none", "why": "предмета нет"}}, False),

        ("обращение через общий вход", audit_calls,
         {"a.py": "def f():\n    return _api('/repos/x')\n"}, False),
        ("обращение мимо общего входа", audit_calls,
         {"a.py": "urlopen('https://api.github.com/repos/x')\n"}, True),
        ("упоминание в комментарии — не обращение", audit_calls,
         {"a.py": "# urlopen('https://api.github.com/x') так делать нельзя\n"}, False),
        ("raw без заголовка авторизации", audit_calls,
         {"a.py": "_get(f'https://raw.githubusercontent.com/x', authenticated=False)\n"}, False),
        ("raw с заголовком авторизации", audit_calls,
         {"a.py": "_get(f'https://raw.githubusercontent.com/x')\n"}, True),

        ("прогоны без циклов ожидания", audit_workflows,
         {"open-pr.yml": "on:\n  push:\n    branches-ignore: [main]\n"}, False),
        ("цикл ожидания в шаге", audit_workflows,
         {"open-pr.yml": "on:\n  push:\n    branches-ignore: [main]\n",
          "x.yml": "run: |\n  while true; do\n    sleep 30\n  done\n"}, True),
        ("переключатель по имени ветки", audit_workflows,
         {"open-pr.yml": "on:\n  push:\n    branches: ['agent/**']\n"}, True),
    ]
    broken: list[str] = []
    for name, fn, data, must_reject in cases:
        found = fn(data)
        if bool(found) is not must_reject:
            broken.append(f"{name}: ожидалось {'отказ' if must_reject else 'пропуск'}, вышло {found}")
        print(f"  {'отвергнут' if found else 'пропущен '} — {name}")

    named = audit_gaps({"077": {"status": "active", "mechanism": "none", "where": "соблюдается устройством"}})
    if not any("077" in line for line in named):
        broken.append("отказ на неназванном пробеле не называет номер правила")

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: гейт отвергает то, что обязан, и называет предмет")
    return 0


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()
    try:
        sources = {p.name: p.read_text(encoding="utf-8") for p in sorted(SCRIPTS.glob("*.py"))}
        flows = {p.name: p.read_text(encoding="utf-8") for p in sorted(WORKFLOWS.glob("*.yml"))}
        rules = json.loads(BINDINGS.read_text(encoding="utf-8"))["rules"]
    except (OSError, ValueError, SyntaxError) as e:
        print(f"проверка не отработала: {e}", file=sys.stderr)
        return 2

    found = (audit_scripts(sources) + audit_calls(sources)
             + audit_gaps(rules) + audit_workflows(flows))
    if found:
        print("механизмы держат не то, что объявили:", file=sys.stderr)
        for line in found:
            print(f"  • {line}", file=sys.stderr)
        print("\n  Объявленное сверяется с сделанным. Если объявление устарело —"
              "\n  меняют объявление, а не отключают проверку.", file=sys.stderr)
        return 1

    print(f"механизмы держат объявленное: скриптов {len(sources)}, "
          f"прогонов {len(flows)}, вердиктов {len(rules)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
