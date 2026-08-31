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

* **090 — копия списка под сверкой.** `pr-check.yml` не будится на метку
  конвейера: она классификацию не меняет. Условие работы не умеет звать питон,
  поэтому имена меток в YAML повторены — и расхождение с `PIPELINE` в
  `check_labels.py` отвергается (`audit_pipeline_labels`). Копия допустима
  ровно до тех пор, пока разойтись молча она не может;

* **140 и 145 — вердикт набора выносится после последнего случая.** Набор,
  решивший «провален или нет» раньше конца перебора, оставляет за вердиктом
  случаи, которые печатают, но не судят: находка дописывается в список,
  который уже прочитан. Замер: в сборке витрины так стояли три группы, и
  подставной провал в последней давал код 0;

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


#: Точечная выборка файлов в шаге забора. Разбирается список: прогон, берущий
#: один скрипт, обязан взять и то, что этот скрипт зовёт.
SPARSE = re.compile(r"sparse-checkout:\s*(?:\|\s*\n((?:\s+\S+\n)+)|(\S+))")


def _imports(source: str) -> set[str]:
    """Имена соседних модулей, которые скрипт импортирует."""
    return {node.names[0].name for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Import) and node.names[0].name.isidentifier()}


def audit_sparse(sources: dict[str, str], flows: dict[str, str]) -> list[str]:
    """Прогон, берущий скрипт точечно, берёт и то, что тот зовёт.

    ИНЦИДЕНТ, ИЗ-ЗА КОТОРОГО ГЕЙТ ЕСТЬ. 28 августа общий помощник разметки был
    вынесен выше гейтов — правильный ход по правилу 090, — и `hold.py` начал
    его звать. Прогон `release-hold` забирал ровно один файл, и механизм снятия
    стоп-крана упал с `ModuleNotFoundError` на первом же изменении. Правка
    вызываемого, сделанная без взгляда на вызывающего: то же рассуждение, что в
    правиле 152, только в другую сторону.

    ПОЧЕМУ ЭТО ЛОВИТСЯ, А НЕ ОБСУЖДАЕТСЯ. Список файлов в шаге и список
    импортов в скрипте — оба машинные, и расхождение между ними видно точно.
    Судить о смысле не требуется.
    """
    found = []
    for name, text in sorted(flows.items()):
        match = SPARSE.search(text)
        if not match:
            continue
        listed = {line.strip() for line in (match.group(1) or match.group(2) or "").split()
                  if line.strip()}
        for path in sorted(listed):
            script = sources.get(pathlib.PurePath(path).name)
            if script is None:
                continue
            for module in sorted(_imports(script)):
                if f"{module}.py" in sources and f"scripts/{module}.py" not in listed:
                    found.append(f"{name}: берёт {path} точечно, а тот зовёт "
                                 f"{module} — выборка оборвёт зависимость (090, 152)")
    return found


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


def _own(fn: ast.FunctionDef) -> list[ast.AST]:
    """Узлы самой функции, без тел вложенных ``def``.

    Различие не косметическое: первый черновик этого разбора считал вердиктом
    ``return`` вложенного помощника — ``config_of`` внутри набора сборки — и
    объявил находку там, где её нет. Ложный отказ у гейта о наборах дороже
    обычного: чинить пошли бы исправный набор.
    """
    stack, own = list(fn.body), []
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        own.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return own


def audit_verdicts(sources: dict[str, str]) -> list[str]:
    """Случаи, приписанные ЗА вердиктом набора: они печатают, но не судят.

    Правила 140 и 145; формулировка взята у 136 — «вердикт после перечисления
    всех предметов», — но предмет здесь другой: там ответ по чужому правилу,
    здесь прогон набора. Набор копит находки в список и в конце решает по нему,
    провален ли прогон. Вердикт, вынесенный раньше последнего случая,
    превращает всё, что идёт следом, в печать: случаи бегут, находки
    дописываются в список, который уже никто не прочтёт, — и прогон отвечает
    «пройдена».

    Замер, из-за которого проверка завелась: в ``build_metrics.py::selftest``
    за вердиктом стояли три группы — вызов без клона грейдера, сверка ответа
    с каталогом и отказ источника. Подставной провал в последней группе дал
    код 0 и строку «самопроверка пройдена».

    Накопитель узнаётся по употреблению, а не по имени: это список, по
    которому набор выносит вердикт (``if broken:`` с ``return`` внутри) и в
    который делает ``append``. Граница названа: вердикт в тернарной форме
    (``return 1 if broken else 0``) разбор не ловит — у витрины такой формы
    нет, и заводить её ради разбора не нужно.
    """
    found: list[str] = []
    for name, source in sorted(sources.items()):
        for fn in [n for n in ast.walk(ast.parse(source))
                   if isinstance(n, ast.FunctionDef)]:
            own = _own(fn)
            # Вердикт: `if <имя>:` с выходом внутри.
            verdicts = {
                node.test.id: node.lineno
                for node in own
                if isinstance(node, ast.If) and isinstance(node.test, ast.Name)
                and any(isinstance(inner, ast.Return) for inner in ast.walk(node))
            }
            for holder, at in verdicts.items():
                late = sorted(
                    node.lineno for node in own
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "append" and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == holder and node.lineno > at
                )
                if late:
                    found.append(
                        f"{name}::{fn.name}: вердикт по «{holder}» вынесен строкой {at}, "
                        f"а находки дописываются позже — строки {late}. Эти случаи "
                        f"печатают, но не судят (140, 145)")
    return found


#: Откуда берётся список конвейерных меток и где лежит его копия.
PIPELINE_SOURCE = "check_labels.py"
PIPELINE_FLOW = "pr-check.yml"
#: Копия в условии работы: `fromJSON('["hold"]')`. Разбирается литерал списка,
#: а не вся строка условия — условие живёт своей жизнью и переписывается.
PIPELINE_IN_FLOW = re.compile(r"fromJSON\(\s*'(\[[^']*\])'\s*\)")


def audit_pipeline_labels(sources: dict[str, str], flows: dict[str, str]) -> list[str]:
    """Копия списка конвейерных меток в условии прогона, разошедшаяся с кодом.

    Правило 090 в его неудобной части. `pr-check.yml` не будится на постановку
    метки конвейера: она классификацию не меняет, и прогон на неё — чистая
    трата (замер: на #100 шесть отменённых прогонов из восьми). Но условие
    работы не умеет звать питон, поэтому имена приходится повторить в YAML.

    Копия допустима ровно до тех пор, пока она под механической сверкой:
    добавь завтра вторую конвейерную метку в PIPELINE — и прогон начнёт
    просыпаться на неё молча, вернув то, что этот фильтр убрал. Гейт делает
    расхождение находкой.

    Отсутствие копии — тоже находка: значит фильтр убрали, а список остался, и
    комментарий рядом с ним врёт.
    """
    source = sources.get(PIPELINE_SOURCE, "")
    flow = flows.get(PIPELINE_FLOW, "")
    if not source or not flow:
        return [f"{PIPELINE_SOURCE} или {PIPELINE_FLOW} не прочитан — "
                f"сверять список конвейерных меток не с чем (090)"]

    declared: set[str] | None = None
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", "") == "PIPELINE" for t in node.targets)):
            declared = {c.value for c in ast.walk(node) if isinstance(c, ast.Constant)
                        and isinstance(c.value, str)}
    if declared is None:
        return [f"{PIPELINE_SOURCE}: PIPELINE не найден — фильтр в {PIPELINE_FLOW} "
                f"опирается на список, которого нет (090)"]

    found = PIPELINE_IN_FLOW.search(flow)
    if not found:
        return [f"{PIPELINE_FLOW}: копии списка конвейерных меток нет, а в "
                f"{PIPELINE_SOURCE} он объявлен — либо фильтр убран и комментарий "
                f"рядом с ним врёт, либо копия переписана в форму, которой гейт "
                f"не видит (090)"]
    copied = set(json.loads(found.group(1)))
    if copied != declared:
        return [f"{PIPELINE_FLOW}: список конвейерных меток разошёлся с "
                f"{PIPELINE_SOURCE} — в коде {sorted(declared)}, в условии "
                f"{sorted(copied)}. Прогон будет просыпаться на метку, которая "
                f"классификацию не меняет, или молчать на той, что меняет (090)"]
    return []


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
    HOLD = "import checks\n\ndef main():\n    return 1\n"
    sparse = [
        ("выборка несёт зависимость", {"hold.py": HOLD, "checks.py": ""},
         {"a.yml": "sparse-checkout: |\n  scripts/hold.py\n  scripts/checks.py\n"}, False),
        ("выборка обрывает зависимость", {"hold.py": HOLD, "checks.py": ""},
         {"a.yml": "sparse-checkout: |\n  scripts/hold.py\n"}, True),
        ("выборка одной строкой обрывает зависимость", {"hold.py": HOLD, "checks.py": ""},
         {"a.yml": "sparse-checkout: scripts/hold.py\n"}, True),
        ("скрипт без соседних импортов", {"a.py": "import json\n", "checks.py": ""},
         {"a.yml": "sparse-checkout: scripts/a.py\n"}, False),
        ("выборки нет — берётся всё", {"hold.py": HOLD, "checks.py": ""},
         {"a.yml": "uses: actions/checkout@v7\n"}, False),
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
    for name, srcs, flws, must_reject in sparse:
        found = audit_sparse(srcs, flws)
        if bool(found) is not must_reject:
            broken.append(f"{name}: ожидалось {'отказ' if must_reject else 'пропуск'}, вышло {found}")
        print(f"  {'отвергнут' if found else 'пропущен '} — {name}")
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

    # Вердикт набора: обе стороны. Ложный отказ здесь дороже пропуска — он
    # отправляет чинить исправный набор, и первый черновик разбора его давал.
    LATE = ("def selftest():\n"
            "    broken = []\n"
            "    if broken:\n"
            "        return 1\n"
            "    broken.append('поздняя находка')\n"
            "    return 0\n")
    ORDERED = ("def selftest():\n"
               "    broken = []\n"
               "    broken.append('находка')\n"
               "    if broken:\n"
               "        return 1\n"
               "    return 0\n")
    NESTED = ("def selftest():\n"
              "    broken = []\n"
              "    def helper():\n"
              "        return {}\n"
              "    broken.append(helper())\n"
              "    if broken:\n"
              "        return 1\n"
              "    return 0\n")
    OTHER = ("def selftest():\n"
             "    broken, seen = [], []\n"
             "    if broken:\n"
             "        return 1\n"
             "    seen.append('чужой список')\n"
             "    return 0\n")
    verdicts = [
        ("находка дописана за вердиктом", {"a.py": LATE}, True),
        ("вердикт после последнего случая", {"a.py": ORDERED}, False),
        ("return вложенного помощника — не вердикт", {"a.py": NESTED}, False),
        ("список, по которому не судят", {"a.py": OTHER}, False),
        ("набора нет вовсе", {"a.py": "def f():\n    return 1\n"}, False),
    ]
    for name, srcs, must_reject in verdicts:
        found = audit_verdicts(srcs)
        if bool(found) is not must_reject:
            broken.append(f"вердикт набора, {name}: ожидалось "
                          f"{'отказ' if must_reject else 'пропуск'}, вышло {found}")
        print(f"  {'отвергнут' if found else 'пропущен '} — вердикт набора: {name}")

    # Отказ обязан назвать и место вердикта, и строки, приписанные за ним:
    # без них чинящий ищет их сам, а гейт для того и заведён (151).
    late_found = audit_verdicts({"a.py": LATE})
    if not (late_found and "a.py::selftest" in late_found[0]
            and "строки" in late_found[0]):
        broken.append("отказ по вердикту набора не называет предмет и строки")

    # ── копия списка конвейерных меток ─────────────────────────────────────
    LABELS_SRC = 'PIPELINE = frozenset({"hold"})\n'
    LABELS_TWO = 'PIPELINE = frozenset({"hold", "wip"})\n'
    FLOW_ONE = "jobs:\n  a:\n    if: >-\n      !contains(fromJSON('[\"hold\"]'), x)\n"
    FLOW_TWO = "jobs:\n  a:\n    if: >-\n      !contains(fromJSON('[\"hold\",\"wip\"]'), x)\n"
    FLOW_NONE = "jobs:\n  a:\n    runs-on: ubuntu-latest\n"
    pipeline_cases = [
        ("список и копия сходятся", LABELS_SRC, FLOW_ONE, False),
        ("в коде добавилась метка, в копии нет", LABELS_TWO, FLOW_ONE, True),
        ("в копии метка, которой нет в коде", LABELS_SRC, FLOW_TWO, True),
        ("порядок в копии другой — не расхождение", LABELS_TWO,
         "jobs:\n  a:\n    if: >-\n      !contains(fromJSON('[\"wip\",\"hold\"]'), x)\n", False),
        ("копии нет вовсе, а список объявлен", LABELS_SRC, FLOW_NONE, True),
        ("списка нет в коде", "CONTENT = frozenset({\"bug\"})\n", FLOW_ONE, True),
    ]
    for name, src, flow, must_reject in pipeline_cases:
        found = audit_pipeline_labels({"check_labels.py": src}, {"pr-check.yml": flow})
        if bool(found) is not must_reject:
            broken.append(f"конвейерные метки, {name}: ожидалось "
                          f"{'отказ' if must_reject else 'пропуск'}, вышло {found}")
        print(f"  {'отвергнут' if found else 'пропущен '} — конвейерные метки: {name}")

    # Отказ обязан показать обе стороны: чинить придётся ту, что устарела, и
    # без обоих списков читающий пойдёт смотреть их сам.
    diverged = audit_pipeline_labels({"check_labels.py": LABELS_TWO}, {"pr-check.yml": FLOW_ONE})
    if not (diverged and "wip" in diverged[0] and "check_labels.py" in diverged[0]):
        broken.append("конвейерные метки: отказ не называет обе стороны расхождения")

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
             + audit_harness(sources, flows) + audit_charter(ROOT)
             + audit_sparse(sources, flows) + audit_verdicts(sources)
             + audit_pipeline_labels(sources, flows))
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
