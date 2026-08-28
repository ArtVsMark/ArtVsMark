#!/usr/bin/env python3
"""Механизмы витрины держат то, что объявили, — и объявляют то, чего не держат.

ЗАЧЕМ. Замер по всем действующим вердиктам показал: у десяти из семидесяти
шести не бежало ничего, а ещё сорок пять держались словом «шаг процесса» —
которое каталог 28 августа расколол, измерив у себя, что под ним 27 записей из
44 означали «ничем». Решение владельца: всё, что можно сделать механическим,
делается механическим. Этот гейт забирает такие правила разом, потому что у них
общий предмет — **объявленное сверяется с сделанным**.

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
  прогона, потому что префикс не совпал;

* **100, 104, 149, 022/073 — утверждения «у ВСЕХ прогонов так».** Таймаут у
  каждой работы, ручная кнопка у каждого прогона, `$RUNNER_TEMP` вместо общего
  `/tmp`, одна версия языка на все прогоны. Четыре вердикта говорили «у всех», и
  проверялось это чтением восьми файлов глазами — то есть до первого нового
  файла. Перебор машина делает даром и без пропусков (`audit_runners`);

* **151 — причина доезжает до окна.** Гейт печатает находку командой площадки, а
  не в поток ошибок. Замер: окну витрины логи прогонов закрыты, и на чужом
  красном остаётся ровно «Process completed with exit code 1». До 28 августа так
  печатал ОДИН гейт из восьми;

* **014 и 150 — набор есть, бежит и зовёт механизм.** У каждого способного
  отвергнуть скрипта есть самопроверка (014, первая половина); `pr-check.yml`
  её зовёт (014, вторая половина — иначе набор держит до первой правки); и
  внутри неё есть вызов функции модуля, а не пересказ его условия (150).

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

import checks

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


#: Общий каталог исполнителя. Прогон, пишущий сюда, полагается на то, что сосед
#: не помешает; ``$RUNNER_TEMP`` площадка выдаёт каждому прогону свой (149).
SHARED_TMP = re.compile(r"(?<![\w$/])/tmp/")


#: Ключ верхнего уровня и ключ работы. Разбор по отступам, а не библиотекой:
#: у витрины нет ни одной сторонней зависимости, и заводить первую ради четырёх
#: проверок дороже, чем прочитать два уровня отступов. Цена решения названа:
#: разбор держится на форматировании в два пробела, и прогон, отступивший от
#: него, станет НАХОДКОЙ, а не тихим пропуском.
TOP_KEY = re.compile(r"^(\w[\w-]*):", re.M)
JOB_KEY = re.compile(r"^  (\w[\w-]*):\s*$", re.M)
JOB_TIMEOUT = re.compile(r"^    timeout-minutes:", re.M)
PY_VERSION = re.compile(r"^\s*python-version:\s*[\"']?([\d.]+)", re.M)


def _section(text: str, name: str) -> str:
    """Тело ключа верхнего уровня — до следующего такого ключа."""
    match = re.search(rf"^{name}:.*$", text, re.M)
    if not match:
        return ""
    rest = text[match.end():]
    following = TOP_KEY.search(rest)
    return rest[: following.start()] if following else rest


#: Свод окна и то, без чего он не свод. Правило 134: окно стартует, прочитав
#: местные правила; до PR #22 свода не было, и витрину вело вслепую.
CHARTER = "CLAUDE.md"
CHARTER_PARTS = ("claude-code-playbook", ".rules/")


def audit_charter(root) -> list[str]:
    """Свод на месте и ведёт к каталогу.

    ЧТО ЭТО ЛОВИТ. Не «прочитало ли окно» — этого машине не видно, — а
    исчезновение предмета чтения: файл удалён, переименован или потерял ссылку
    на каталог, из которого правила приходят. Ровно это и было инцидентом
    правила: свода не существовало, и стартовать было не с чего.

    ГРАНИЦА НАЗВАНА: зелёное здесь значит «свод существует и ведёт к каталогу»,
    и не значит «свод верен». Второе проверяется чтением (правило 146).
    """
    charter = root / CHARTER
    if not charter.is_file():
        return [f"{CHARTER}: свода нет — окно стартует вслепую, и это дословно "
                f"инцидент правила (134)"]
    text = charter.read_text(encoding="utf-8")
    missing = [part for part in CHARTER_PARTS if part not in text]
    return [f"{CHARTER}: свод не ведёт к {', '.join(missing)} — правила приходят "
            f"оттуда, и свод без этой ссылки обрывает дорогу (134)"] if missing else []


def audit_runners(flows: dict[str, str]) -> list[str]:
    """Утверждения о прогонах, которые до 28 августа держались одной прозой.

    Четыре вердикта говорили «у ВСЕХ прогонов так», и проверялось это чтением
    восьми файлов глазами — то есть до первого нового файла. Перебор машина
    делает даром и без пропусков.

    ПОЧЕМУ ОТСТУПЫ, А НЕ ГРЕП. ``timeout-minutes`` стоит и у работы, и у шага, и
    грепом одно от другого не отличить: файл с таймаутом у единственного шага
    прошёл бы как «у работы есть». Уровень отступа эту разницу видит.
    """
    found = []
    versions: dict[str, set[str]] = {}
    for name, text in sorted(flows.items()):
        triggers = _section(text, "on")
        # `on` в YAML — ещё и слово «истина», но здесь читается текст, и этой
        # двусмысленности у разбора по отступам просто нет.
        if "workflow_dispatch:" not in triggers:
            found.append(f"{name}: нет ручной кнопки — у событийной автоматики "
                         f"она обязательна, иначе прогон нельзя позвать (104)")
        jobs = _section(text, "jobs")
        if not jobs.strip():
            found.append(f"{name}: работ не разобрано ни одной. Разбор держится "
                         f"на отступах в два пробела — либо файл отступает от "
                         f"них, либо прогон пуст; молча пропускать нельзя (010)")
        bounds = [m.start() for m in JOB_KEY.finditer(jobs)] + [len(jobs)]
        for i, (job, begin) in enumerate((m.group(1), m.start())
                                         for m in JOB_KEY.finditer(jobs)):
            body = jobs[begin:bounds[i + 1]]
            if not JOB_TIMEOUT.search(body):
                found.append(f"{name}: у работы {job} нет timeout-minutes — "
                             f"умолчание площадки шесть часов (100)")
        for version in PY_VERSION.findall(text):
            versions.setdefault(version, set()).add(name)
        if SHARED_TMP.search(text):
            found.append(f"{name}: пишет в общий /tmp — площадка выдаёт "
                         f"$RUNNER_TEMP каждому прогону свой (149)")

    # Версия языка задана в ОДНОМ месте: две разные означают, что проверки и
    # сборка бегут на разных языках, и разойдутся они молча (022).
    if len(versions) > 1:
        where = "; ".join(f"{v} — {', '.join(sorted(f))}" for v, f in sorted(versions.items()))
        found.append(f"версий Python в прогонах больше одной: {where} (022, 073)")
    return found


#: Имена, по которым скрипт печатает находку командой площадки. Замер правила
#: 151: окну логи прогонов закрыты, и до него доходит только то, что напечатано
#: командой, — всё прочее сворачивается в «Process completed with exit code 1».
ANNOTATOR = "annotate"


def audit_voice(sources: dict[str, str]) -> list[str]:
    """Гейты, чья находка не доедет до окна: причина в поток, а не командой.

    ГРАНИЦА. Проверяется, что помощник ЗОВЁТСЯ, а не что позван на каждом
    отказе: разобрать, все ли ветки отказа он покрывает, значило бы судить о
    смысле кода. Это названо здесь прямо, чтобы зелёное не читалось шире, чем
    измерено (правило 146).
    """
    found = []
    for name, source in sorted(sources.items()):
        if not can_fail(source):
            continue
        tree = ast.parse(source)
        if not any(_called(node) == ANNOTATOR
                   for node in ast.walk(tree) if isinstance(node, ast.Call)):
            found.append(f"{name}: находка печатается в поток, а не командой "
                         f"площадки — до окна доедет «exit code 1» (151)")
        # Гейт без отрицательного набора — обещание. 014: механизм проверяется
        # тем, что он ОБЯЗАН отвергнуть, и набор этот бежит в конвейере, а не
        # рукой при заведении.
        if not any(isinstance(n, ast.FunctionDef) and n.name == "selftest"
                   for n in ast.walk(tree)):
            found.append(f"{name}: способен отвергнуть, а отрицательного набора "
                         f"нет — гейт не проверен тем, что обязан ловить (014)")
            continue
        # 150: набор ЗОВЁТ механизм, а не пересказывает его условие. Машине
        # видно ровно это — что внутри набора есть вызов другой функции модуля;
        # верность случаев она не судит.
        own = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        body = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "selftest")
        if not any(_called(c) in own - {"selftest"}
                   for c in ast.walk(body) if isinstance(c, ast.Call)):
            found.append(f"{name}: самопроверка не зовёт механизм — она "
                         f"пересказывает условие и разойдётся с ним молча (150)")
    return found


def audit_harness(sources: dict[str, str], flows: dict[str, str]) -> list[str]:
    """Наборы, которых конвейер не зовёт: они существуют и ничего не держат.

    Вторая половина правила 014. Первая — что набор ЕСТЬ (audit_voice); эта —
    что он БЕЖИТ. Набор, который гоняют рукой при заведении гейта, держит
    ровно до следующей правки: замер 28 августа — `checks.py` получил
    самопроверку и не был вписан в прогон, и заметить это удалось глазами.

    Спрашивается один прогон — `pr-check.yml`: набор обязан отказывать
    ИЗМЕНЕНИЮ, а не будиться расписанием, когда правка уже в общей ветке.
    """
    check = flows.get("pr-check.yml", "")
    if not check:
        return ["pr-check.yml: прогона проверок нет — наборы не бегут нигде (014)"]
    return [f"{name}: самопроверка есть, а pr-check.yml её не зовёт — "
            f"набор держит до первой правки (014)"
            for name, source in sorted(sources.items())
            if "def selftest" in source and f"scripts/{name} --selftest" not in check]


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


#: Образцы для отрицательного набора. Прогон-образец полон намеренно: каждый
#: случай ломает в нём РОВНО ОДНО, и видно, на что именно гейт отвечает.
GOOD_FLOW = (
    "name: a\n"
    "on:\n"
    "  push:\n"
    "  workflow_dispatch:\n"
    "jobs:\n"
    "  one:\n"
    "    runs-on: ubuntu-latest\n"
    "    timeout-minutes: 10\n"
    "    steps:\n"
    "      - run: echo\n"
)
PY_FLOW = (
    "name: a\n"
    "on:\n"
    "  workflow_dispatch:\n"
    "jobs:\n"
    "  one:\n"
    "    runs-on: ubuntu-latest\n"
    "    timeout-minutes: 10\n"
    "    steps:\n"
    "      - uses: actions/setup-python@v6\n"
    "        with:\n"
    '          python-version: "{v}"\n'
)
#: Образец гейта: докстрока с исходами, вызов помощника, набор, зовущий
#: механизм. Каждый случай ниже ломает ровно одну из трёх частей.
VOICE_OK = (
    '"""Гейт.\n'
    "\n"
    "Iskhody: 0, 1, 2.\n"
    '"""\n'
    "def audit():\n"
    "    return []\n"
    "\n"
    "def selftest():\n"
    "    return audit()\n"
    "\n"
    "def main():\n"
    "    print(checks.annotate(LEVEL, FOUND))\n"
    "    return 1\n"
)


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

        ("прогон полон", audit_runners, {"a.yml": GOOD_FLOW}, False),
        ("нет ручной кнопки", audit_runners,
         {"a.yml": GOOD_FLOW.replace("  workflow_dispatch:\n", "")}, True),
        ("нет таймаута у работы", audit_runners,
         {"a.yml": GOOD_FLOW.replace("    timeout-minutes: 10\n", "")}, True),
        ("таймаут у шага, а не у работы", audit_runners,
         {"a.yml": GOOD_FLOW.replace("    timeout-minutes: 10\n", "")
                            .replace("      - run: echo\n",
                                     "      - run: echo\n        timeout-minutes: 5\n")}, True),
        ("пишет в общий /tmp", audit_runners,
         {"a.yml": GOOD_FLOW.replace("run: echo", "run: echo x > /tmp/body.md")}, True),
        ("$RUNNER_TEMP общим не считается", audit_runners,
         {"a.yml": GOOD_FLOW.replace("run: echo", "run: echo x > $RUNNER_TEMP/body.md")}, False),
        ("одна версия языка на два прогона", audit_runners,
         {"a.yml": PY_FLOW.format(v="3.12"), "b.yml": PY_FLOW.format(v="3.12")}, False),
        ("две разные версии языка", audit_runners,
         {"a.yml": PY_FLOW.format(v="3.12"), "b.yml": PY_FLOW.format(v="3.11")}, True),

        ("гейт зовёт помощника и проверен набором", audit_voice, {"a.py": VOICE_OK}, False),
        ("причина печатается в поток", audit_voice,
         {"a.py": VOICE_OK.replace("checks.annotate(LEVEL, FOUND)", "FOUND")}, True),
        ("отрицательного набора нет", audit_voice,
         {"a.py": VOICE_OK.replace("def selftest():", "def proverka():")}, True),
        ("набор пересказывает условие вместо вызова", audit_voice,
         {"a.py": VOICE_OK.replace("return audit()", "return 1 if 2 > 1 else 0")}, True),
        ("модуль без входа набора не требует", audit_voice,
         {"checks.py": "def f():\n    return 1\n"}, False),
    ]
    charter = [
        ("свод на месте и ведёт к каталогу", ROOT, False),
        ("свода нет вовсе", ROOT / "нет-такого-каталога", True),
    ]
    harness = [
        ("набор бежит в прогоне проверок", {"a.py": "def selftest():\n    pass\n"},
         {"pr-check.yml": "run: python scripts/a.py --selftest\n"}, False),
        ("набор есть, а прогон его не зовёт", {"a.py": "def selftest():\n    pass\n"},
         {"pr-check.yml": "run: python scripts/a.py\n"}, True),
        ("набора нет — звать нечего", {"a.py": "def f():\n    pass\n"},
         {"pr-check.yml": "run: python scripts/a.py\n"}, False),
        ("прогона проверок нет вовсе", {"a.py": "def selftest():\n    pass\n"}, {}, True),
    ]
    broken: list[str] = []
    for name, root, must_reject in charter:
        found = audit_charter(root)
        if bool(found) is not must_reject:
            broken.append(f"{name}: ожидалось {'отказ' if must_reject else 'пропуск'}, вышло {found}")
        print(f"  {'отвергнут' if found else 'пропущен '} — {name}")
    for name, srcs, flws, must_reject in harness:
        found = audit_harness(srcs, flws)
        if bool(found) is not must_reject:
            broken.append(f"{name}: ожидалось {'отказ' if must_reject else 'пропуск'}, вышло {found}")
        print(f"  {'отвергнут' if found else 'пропущен '} — {name}")
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

    found = (audit_scripts(sources) + audit_calls(sources) + audit_voice(sources)
             + audit_gaps(rules) + audit_workflows(flows) + audit_runners(flows)
             + audit_harness(sources, flows) + audit_charter(ROOT))
    if found:
        print(checks.annotate("error", f"механизмы держат не то, что объявили: {len(found)}"), file=sys.stderr)
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
