#!/usr/bin/env python3
"""Проверяет, что вердикты в ``.rules/bindings.json`` показывают на живое.

У вердикта есть поле «чем именно здесь держится» — и это не пояснение, а
**утверждение о текущем коде**. Устаревает оно ровно так же, как число,
вписанное руками: функцию переименовали, прогон удалили, скрипт выбросили — а
вердикт продолжает уверенно ссылаться на них. Так и вышло: ``count_rules``
переименовали в ``rules_export``, и два вердикта полгода показывали в пустоту.
Заметить это можно было только глазами, и никто не заметил.

Что проверяется: каждый упомянутый файл существует, и каждый якорь
``файл::имя`` объявлен в этом файле.

Чего проверка НЕ делает и почему. Ложный отказ здесь дороже пропуска: гейт,
который ругается на верное, начинают обходить (правило 051). Поэтому:

* разбираются только пути с известным расширением — ``.py``, ``.yml``,
  ``.yaml``, ``.json``, ``.md``. Шаблоны вроде ``assets/metrics-*.svg``
  пропускаются молча: проверять их значило бы гадать;
* короткое имя прогона (``pr-check.yml``) ищется и в корне, и в
  ``.github/workflows/`` — в вердиктах его пишут без каталога, и это не ошибка;
* якорь ищется среди имён **верхнего уровня**: функция, класс и константа
  одинаково годятся — ``check_labels.py::CONTENT`` это список, а не функция;
* ссылки на разделы (``§``) ПРОВЕРЯЮТСЯ с 8 сентября. Прежде здесь стояло
  «заголовок — не имя в коде, и сверять его пришлось бы по написанию», и довод
  был верен по трудности и неверен по выводу: замер нашёл ЧЕТЫРЕ ссылки в
  никуда, и все четыре осиротели В ТОТ ЖЕ ДЕНЬ от собственных правок витрины —
  #158 переименовал «What holds the quality» и убрал «Contributions welcome»,
  #172 переименовал раздел свода о журналах. Сверка идёт по НОРМАЛИЗОВАННОМУ
  написанию: эмодзи, кавычки и выделение снимаются, регистр не важен, годится
  и заголовок, и жирный зачин абзаца — в этих документах именованный кусок
  бывает и тем и другим.

Исходы: 0 — чисто; 1 — есть находки; 2 — проверка не отработала.
"""

import ast
import json
import pathlib
import re
import sys
from collections.abc import Callable

import checks

ROOT = pathlib.Path(__file__).resolve().parent.parent
BINDINGS = ROOT / ".rules/bindings.json"
WORKFLOWS = ROOT / ".github/workflows"

# Путь с известным расширением и необязательным якорем `::имя`.
#
# Ведущая точка в пути обязательна к разбору: без неё `.github/workflows/…`
# читается с середины, как `github/workflows/…`, и проверка отвергает
# восемнадцать живых ссылок из восемнадцати. Это первый черновик и делал —
# ложный отказ, дефект проверки, а не вердикта.
REFERENCE = re.compile(
    r"(?<![\w./-])(?P<path>\.?[\w][\w./-]*\.(?:py|ya?ml|json|md))(?:::(?P<anchor>\w+))?"
)

# Якорь-продолжение: «scripts/checks.py::clip и ::tail» — второе имя ищется в
# ПОСЛЕДНЕМ названном файле. ФОРМА ВЗЯТА ЗАМЕРОМ (206): 29 сентября в
# вердиктах 250 якорей с путём и 30 без, и последние не проверял никто.
# Из тридцати четыре — команды площадки `::error::`, их отсекает `::` сразу
# за именем; из остальных двадцати шести четыре показывали не туда: якорь
# стоял после чужого файла (072, 144, 180).
CONTINUED = re.compile(r"(?<![\w.:])::(?P<anchor>\w+)\b(?!::)")


def locate(path: str) -> pathlib.Path | None:
    """Файл, на который показывает ссылка, или ``None``.

    Короткое имя прогона разрешается в ``.github/workflows/``: в вердиктах
    пишут ``pr-check.yml``, а лежит он не в корне. Без этого проверка дала бы
    ложный отказ на двух ссылках из четырёх — то есть сама стала бы дефектом.
    """
    candidates = [ROOT / path]
    if "/" not in path and path.endswith((".yml", ".yaml")):
        candidates.append(WORKFLOWS / path)
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def declared(file: pathlib.Path) -> set[str]:
    """Имена верхнего уровня файла: функции, классы, константы."""
    if file.suffix != ".py":
        # Не-Python: якорь ищется как слово в тексте. Грубее, зато не врёт в
        # сторону отказа — шаг прогона объявляется не так, как функция.
        return set(re.findall(r"\w+", file.read_text(encoding="utf-8")))
    names: set[str] = set()
    for node in ast.parse(file.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


#: Ссылка на раздел документа: «CLAUDE.md § Ветки». Имя раздела кончается на
#: первом тире, точке, точке с запятой или запятой — дальше идёт проза вердикта.
#: Граница названа, а не угадывается: вердикт, у которого имя раздела длиннее,
#: пишется так, чтобы оно кончалось раньше знака.
SECTION_REF = re.compile(r"([\w./-]+\.md)\s+§\s+([^—;,\.]+)")


def normal(text: str) -> str:
    """Написание раздела, приведённое к сравнимому виду.

    Снимается ровно то, что не несёт смысла имени: выделение, кавычки, эмодзи и
    их модификаторы, регистр, точка на конце. Свод пишет заголовки со значками —
    «## 🌿 Ветки», — а вердикты ссылаются на них словом.
    """
    import unicodedata                                          # noqa: PLC0415
    text = re.sub(r"[*_`«»\"]", "", text)
    text = "".join(c for c in text
                   if not unicodedata.category(c).startswith(("So", "Sk")) and c != "\ufe0f")
    return " ".join(text.split()).casefold().rstrip(".")


def anchors(text: str) -> set[str]:
    """Именованные куски документа: заголовки и жирные зачины абзацев.

    ЗАЧИН СЧИТАЕТСЯ НАРАВНЕ С ЗАГОЛОВКОМ, и это не поблажка. В служебных
    документах витрины именованный кусок бывает и тем и другим: «**Кто снимает
    `hold`.**» в .rules/README.md — такой же адрес, как заголовок, и вердикт 181
    ссылается именно на него. Требовать от них заголовка значило бы требовать
    переписать документы под гейт, а не наоборот.
    """
    found = set()
    for line in text.splitlines():
        if line.startswith("#"):
            found.add(normal(line.lstrip("#")))
        lead = re.match(r"\*\*(.+?)\*\*", line.strip())
        if lead:
            found.add(normal(lead.group(1)))
    return found


def dead_sections(rules: dict[str, dict], read) -> list[str]:
    """Вердикты, ссылающиеся на разделы, которых в документе нет.

    ПРЕДМЕТ ОПЛАЧЕН СВОИМИ ЖЕ ПРАВКАМИ. Замер 8 сентября: 37 ссылок на разделы,
    четыре в никуда — и все четыре осиротели в тот же день. Переименовать раздел
    страницы или свода можно, не заметив, что на него ссылается вердикт: путь к
    файлу остаётся живым, гейт остаётся зелёным, а утверждение показывает в
    пустоту.

    СРАВНЕНИЕ ПО ПРЕФИКСУ В ОБЕ СТОРОНЫ: вердикт вправе назвать раздел короче,
    чем он озаглавлен, и наоборот — проза после имени иногда не отделена знаком.
    Точное совпадение требовать нельзя, иначе гейт ругается на верное.

    ФОРМА «файл § раздел» ОЗНАЧАЕТ ЖИВОЙ АДРЕС, и это граница, а не придирка.
    Первая же редакция вердиктов под этот гейт написала историю тем же знаком —
    «он ссылался на README.md § Contributions welcome» — и гейт отверг: отличить
    рассказ о снесённом разделе от ссылки на него ему нечем, а разбирать время
    глагола он не умеет и не должен. Раздел, которого больше нет, называется
    СЛОВОМ; знак § остаётся адресом.
    """
    found = []
    cache: dict[str, set[str] | None] = {}
    for number, binding in sorted(rules.items()):
        body = f"{binding.get('where', '')} {binding.get('why', '')}"
        for match in SECTION_REF.finditer(body):
            document, section = match.group(1), normal(match.group(2))
            if document not in cache:
                cache[document] = read(document)
            known = cache[document]
            if known is None:                    # файла нет — это ловит другая проверка
                continue
            if not any(section == name or name.startswith(section)
                       or section.startswith(name) for name in known):
                found.append(f"{number}: в {document} нет раздела "
                             f"«{match.group(2).strip()}» — вердикт показывает в "
                             f"пустоту (правило 175)")
    return found


def refuted(rules: dict[str, dict], files: Callable[[str], list[str]],
            read: Callable[[str], str] = lambda path: "") -> list[str]:
    """Ответы «предмета нет», у которых предмет нашёлся.

    ОТВЕТ «ЭТОГО У НАС НЕТ» — УТВЕРЖДЕНИЕ О ДЕЙСТВИТЕЛЬНОСТИ, а не оборот речи,
    и устаревает оно молча: прозу не двигает никакой механизм, а выглядит она
    осознанным решением (правило 175). Проверяется подкласс, сводимый к наличию
    объекта: вердикт называет его сам, полем ``refuted_by`` — пробой
    ``{globs, contains}``: файл по маске (при непустом ``contains`` — файл с
    одной из строк) опровергает ответ. Семантика — ``answer_form.прогнать_пробу``
    каталога: совпадает файл, а не каталог.

    ОТКАЗ ТОЛЬКО В ОДНУ СТОРОНУ: нашли опровержение — красное; не нашли —
    молчим. Незнание не доказывает отсутствия, и односторонность здесь не
    послабление, а условие работы в мелком клоне, где команда отвечает «нет» на
    всё.

    ЦЕНА ЗАПЛАЧЕНА ТРЕМЯ ВЕРДИКТАМИ РАЗОМ. 3 сентября нашлись: «входного свода
    у витрины нет» при живом CLAUDE.md, «сознательных дублей нет: скрипт один»
    при тринадцати скриптах и подписанном дубле, «один прогон в сутки» при пяти
    расписаниях. Все три опровергались одной командой и стояли месяцами.
    """
    found = []
    for number, binding in sorted(rules.items()):
        probe = binding.get("refuted_by")
        if not probe:
            continue
        # ФОРМА — КОНТРАКТА 1.9: объект {globs, contains}. Строка-маска —
        # диалект до 1.9; на нём проба читалась ROOT.glob и совпадала с
        # КАТАЛОГОМ, а по контракту совпадает только файл. Перенос строки как
        # есть заглушил бы 16 проб из 28 — те, что смотрели на каталоги.
        if not isinstance(probe, dict):
            found.append(f"{number}: refuted_by — {type(probe).__name__}, а с контракта "
                         f"1.9 проба пишется объектом {{globs, contains}}")
            continue
        globs, needles = probe.get("globs") or [], probe.get("contains") or []
        hits = [path for glob in globs for path in files(glob)
                if not needles or any(needle in read(path) for needle in needles)]
        if hits:
            what = ", ".join(globs) + (f" со строкой из {needles}" if needles else "")
            found.append(f"{number}: ответ «предмета нет» опровергается — {what} "
                         f"существует ({checks.tail(sorted(set(hits)), 3)}). Утверждение о "
                         f"действительности устарело молча (175)")
    return found


def audit(rules: dict[str, dict]) -> tuple[list[str], int]:
    """Мёртвые ссылки вердиктов и число проверенных."""
    dead: list[str] = []
    checked = 0

    for number, binding in sorted(rules.items()):
        # Проверяются оба поля: «чем держится» у действующего и причина у
        # отрицательного. Причина «этого у нас нет» устаревает от появления
        # артефакта так же, как ссылка — от переименования.
        claim = " ".join(str(binding.get(field, "")) for field in ("where", "why"))
        # Ссылки и продолжения — в порядке текста: продолжение берёт файл у
        # ближайшей ссылки слева.
        found = sorted([*REFERENCE.finditer(claim), *CONTINUED.finditer(claim)],
                       key=lambda m: m.start())
        path = None
        for match in found:
            checked += 1
            anchor = match.group("anchor")
            if match.re is REFERENCE:
                path = match.group("path")
            elif path is None:
                dead.append(f"{number}: имя ::{anchor} без файла — продолжению не "
                            f"к чему относиться")
                continue
            file = locate(path)
            if file is None:
                if match.re is REFERENCE:
                    dead.append(f"{number}: нет файла — {path}")
            elif anchor and anchor not in declared(file):
                dead.append(f"{number}: нет имени {anchor} в {file.relative_to(ROOT)}")

    return dead, checked


def selftest() -> int:
    """Прогоняет через проверку то, что она ОБЯЗАНА отвергнуть.

    Правило 140 каталога: пока такого прогона нет, «гейт не пропустит» —
    обещание, а не механизм. Зелёный прогон на хорошем входе подтверждает лишь
    то, что скрипт запускается: проверка, всегда возвращающая ноль, проходит
    его идеально.

    Предметы подделываются нарочно, а не ждутся из жизни: ждать настоящего
    протухшего вердикта значит проверять гейт тогда, когда он уже не сработал.
    Оба случая настоящие — ровно так протухли 045 и 090, когда count_rules
    переименовали в rules_export, и ровно так протух бы вердикт, державшийся
    удалённым scripts/merge_pr.py.
    """
    cases = [
        ("мёртвое имя функции", {"075": {"where": "scripts/build_metrics.py::count_rules"}}, True),
        ("удалённый файл", {"004": {"why": "держалось scripts/merge_pr.py::when_green"}}, True),
        ("короткое имя прогона", {"011": {"where": "metrics.yml и pr-check.yml"}}, False),
        # Случай, который поймал мутацию собственной самопроверки: разбор пути,
        # съедающий ведущую точку, читает .github/… как github/… и отвергает
        # ВОСЕМНАДЦАТЬ живых ссылок. Проверка обязана ловить и ложный отказ —
        # он дороже пропуска (правило 051), а прогон на одних лишь «обязан
        # отвергнуть» его не видит.
        ("полный путь с ведущей точкой",
         {"010": {"where": ".github/workflows/automerge.yml — автомерж включается рано"}}, False),
        ("шаблон вместо пути", {"075": {"where": "assets/metrics-*.svg переписываются сборкой"}}, False),
        # Знак § раньше означал «этой ссылки проверка не касается»; теперь она
        # её проверяет, и случай остался — но означает другое: путь живой, а
        # раздел судит dead_sections, не эта проверка.
        ("ссылка на раздел: путь разбирается, раздел судит другая проверка",
         {"022": {"where": "CLAUDE.md § Источники истины"}}, False),
        # Продолжение якоря (206): второе имя ищется в последнем названном файле.
        ("продолжение живое", {"016": {"where": "scripts/checks.py::clip и ::tail"}}, False),
        ("продолжение мёртвое", {"016": {"where": "scripts/checks.py::clip и ::nope"}}, True),
        ("продолжение после чужого файла",
         {"016": {"where": "scripts/checks.py::clip; README.md, как ::clip"}}, True),
        ("продолжение без файла", {"016": {"where": "держит ::clip"}}, True),
        ("команда площадки — не якорь",
         {"151": {"where": "печатают через ::error:: и ::warning::"}}, False),
    ]
    broken = []
    for name, rules, must_reject in cases:
        dead, _ = audit(rules)
        if bool(dead) is not must_reject:
            broken.append(f"{name}: ожидалось {'отказ' if must_reject else 'пропуск'}, вышло наоборот")
        print(f"  {'отвергнут' if dead else 'пропущен '} — {name}")

    # ── ответ «предмета нет», у которого предмет нашёлся ──────────────────
    # Отказ ОДНОСТОРОННИЙ: нашли опровержение — красное, не нашли — молчим.
    # Незнание не доказывает отсутствия, и в мелком клоне двусторонний гейт
    # стал бы генератором ложных находок.
    refute_cases = [
        ("предмет нашёлся — ответ устарел",
         {"053": {"status": "not-applicable", "refuted_by": {"globs": ["x.yml"]}}}, ["x.yml"], True),
        ("предмета нет — молчим",
         {"053": {"status": "not-applicable", "refuted_by": {"globs": ["x.yml"]}}}, [], False),
        ("строка-маска — диалект до 1.9",
         {"053": {"status": "not-applicable", "refuted_by": "x.yml"}}, [], True),
        ("файл есть, нужной строки в нём нет — молчим",
         {"053": {"status": "not-applicable",
                  "refuted_by": {"globs": ["x.yml"], "contains": ["merge_group"]}}},
         ["x.yml"], False),
        ("опровержение не названо — не наше дело",
         {"053": {"status": "not-applicable", "why": "очереди нет"}}, ["x.yml"], False),
        ("действующий вердикт поля не несёт",
         {"011": {"status": "active", "where": "metrics.yml"}}, ["x.yml"], False),
    ]
    for name, rules, hits, must_reject in refute_cases:
        found = bool(refuted(rules, lambda glob, h=hits: h, lambda path: "on: push"))
        if found is not must_reject:
            broken.append(f"опровержение, {name}: ожидалось "
                          f"{'отказ' if must_reject else 'пропуск'}, вышло {found}")
        print(f"  {'отвергнут' if found else 'пропущен '} — опровержение: {name}")

    # Находка обязана назвать НОМЕР и НАЙДЕННОЕ: «что-то устарело» отправляет
    # читающего искать предмет самому.
    said = refuted({"053": {"status": "not-applicable", "refuted_by": {"globs": ["q.yml"]}}},
                   lambda glob: ["q.yml"])
    # Строка из contains найдена — опровергнуто: вторая половина пробы.
    if not refuted({"053": {"status": "not-applicable",
                            "refuted_by": {"globs": ["x.yml"], "contains": ["merge_group"]}}},
                   lambda glob: ["x.yml"], lambda path: "on: merge_group"):
        broken.append("опровержение: строка из contains найдена, а ответ не опровергнут")
    if not (said and "053" in said[0] and "q.yml" in said[0]):
        broken.append("опровержение: находка не называет номер и найденное")


    # ── ссылки на разделы документов ─────────────────────────────────────
    # Замер, из-за которого проверка завелась: 37 ссылок, четыре в никуда, и все
    # четыре осиротели в тот же день от собственных правок витрины. Соседи
    # признака «раздел жив» перебраны поимённо: заголовок · заголовок со значком
    # · жирный зачин абзаца · короче заголовка · длиннее заголовка · чужой
    # регистр · кавычки · снесённый раздел · документ, которого нет вовсе.
    doc = ("# 🌿 Ветки\n\ntext\n\n## Журнал изменений и журнал решений\n\n"
           "**Кто снимает `hold`.** Ставит его прогон.\n")
    section_cases = [
        ("заголовок со значком", "Ветки", False),
        ("заголовок словом", "Журнал изменений и журнал решений", False),
        ("вердикт назвал короче", "Журнал изменений", False),
        ("вердикт назвал длиннее", "Ветки называют задачу", False),
        ("жирный зачин абзаца", "Кто снимает hold", False),
        ("чужой регистр", "ВЕТКИ", False),
        ("снесённого раздела нет", "Contributions welcome", True),
    ]
    for name, section, expected in section_cases:
        rule = {"001": {"status": "active", "where": f"CLAUDE.md § {section} — проза"}}
        got = bool(dead_sections(rule, lambda _d, t=doc: anchors(t)))
        if got != expected:
            broken.append(f"раздел, {name}: ожидалось находок {expected}, вышло {got}")
        print(f"  {'найдено ' if got else 'пропущено'} — раздел: {name}")

    # Словари предела и механизма — обе стороны (140): законные слова проходят, чужое слово
    # и отказ без замера краснеют.
    limit_cases = [
        ("три слова без отказа законны", {str(n): {"holdable": w} for n, w in
                                      enumerate(("no", "not-yet", "conditional"), 1)}, 0),
        ("отказ с замером — законен",
         {"001": {"holdable": "refused", "machine_half": "сработал бы на 109 из 143"}}, 0),
        ("предела нет вовсе — не предмет", {"001": {"status": "active"}}, 0),
        ("отказ без замера", {"001": {"holdable": "refused"}}, 1),
        ("отказ с пустым замером", {"001": {"holdable": "refused", "machine_half": " "}}, 1),
        ("слово вне словаря", {"001": {"holdable": "impossible"}}, 1),
        ("пять слов механизма законны", {str(n): {"mechanism": w} for n, w in
                                     enumerate(("gate", "pipeline", "skill", "document"), 1)}
         | {"005": {"mechanism": "none", "machine_half": "строится с #9"}}, 0),
        ("механизм code — вне словаря", {"001": {"mechanism": "code"}}, 1),
        ("устаревший process-step — вне словаря", {"001": {"mechanism": "process-step"}}, 1),
        ("ничем, с машинной половиной — законно",
         {"001": {"status": "active", "mechanism": "none", "machine_half": "строится с #9"}}, 0),
        ("ничем без машинной половины", {"001": {"status": "active", "mechanism": "none"}}, 1),
        ("ничем с пустой машинной половиной",
         {"001": {"status": "active", "mechanism": "none", "machine_half": "  "}}, 1),
        ("ничем, но неприменимо — не предмет",
         {"001": {"status": "not-applicable", "mechanism": "none"}}, 0),
    ]
    for name, rules, expected in limit_cases:
        got = len(limits(rules))
        if got != expected:
            broken.append(f"словарь, {name}: ожидалось находок {expected}, вышло {got}")
        print(f"  {got} находок — словарь: {name}")

    # Очередь на перечитывание (207) — обе стороны: «предмета нет» на одной
    # прозе в очереди, с пробой опровержения — нет; пустая проба ничего не
    # доказывает и очереди не покидает; действующее — не предмет. Порядок —
    # по номеру, чтобы заход брал предметы один за другим, а не вразброс.
    probe = {"globs": ["*.yml"], "contains": []}
    queue_cases = [
        ("проза без пробы — в очереди",
         {"001": {"status": "not-applicable", "why": "предмета нет"}}, ["001"]),
        ("с пробой опровержения — не в очереди",
         {"001": {"status": "not-applicable", "why": "нет", "refuted_by": probe}}, []),
        ("пустая проба — всё ещё проза",
         {"001": {"status": "not-applicable", "why": "нет", "refuted_by": {}}}, ["001"]),
        ("действующее — не предмет", {"001": {"status": "active", "why": "x"}}, []),
        ("порядок по номеру",
         {"010": {"status": "not-applicable"}, "002": {"status": "not-applicable"},
          "005": {"status": "not-applicable", "refuted_by": probe}}, ["002", "010"]),
    ]
    for name, rules, expected in queue_cases:
        got = [number for number, _ in unchecked(rules)]
        if got != expected:
            broken.append(f"очередь, {name}: ожидалось {expected}, вышло {got}")
        print(f"  {len(got)} в очереди — {name}")

    # Исполняемый адрес у ответа gate/pipeline (139) — шесть видов адреса
    # проходят, документ и пустота краснеют, document и неприменимое не предмет.
    run_cases = [
        ("прогон .yml", "gate", ".github/workflows/pr-check.yml — шаг", 0),
        ("прогон .yaml", "pipeline", ".github/workflows/x.yaml", 0),
        ("действие", "gate", ".github/actions/attribution/action.yml", 0),
        ("скрипт .py", "gate", "scripts/check_page.py::audit", 0),
        ("скрипт .sh", "gate", "scripts/run.sh", 0),
        ("тест", "gate", "tests/test_x.py::test_y", 0),
        ("хук окна", "gate", ".claude/hooks/session-start.sh", 0),
        ("только документ", "gate", "CLAUDE.md § Гейты — абзац", 1),
        ("документ и пустота", "pipeline", "", 1),
        ("путь в чужом каталоге не свой", "gate", "x/scripts/y.py", 1),
        ("document не предмет", "document", "README.md", 0),
    ]
    for name, mechanism, where_, expected in run_cases:
        got = len(unrunnable({"001": {"status": "active", "mechanism": mechanism,
                                      "where": where_}}))
        if got != expected:
            broken.append(f"исполняемый адрес, {name}: ожидалось {expected}, вышло {got}")
        print(f"  {got} находок — исполняемый адрес: {name}")

    # ── заявленное число предметов против перечня (136) ───────────────────
    count_cases = [
        ("число и перечень сходятся", "предметов три, перебраны все. (1) а (2) б (3) в", 0),
        ("число прописью заглавными", "предметов ПЯТЬ: (1) (2) (3) (4) (5)", 0),
        ("число цифрой", "предметов 2: (1) а; (2) б", 0),
        ("пункт сверх числа", "предметов три: (1) (2) (3) (4)", 1),
        ("пункта не хватает", "предметов три: (1) (2)", 1),
        ("пункт дважды", "предметов три: (1) (2) (2)", 1),
        ("перечень не размечен", "предметов три, перебраны все", 1),
        ("числа не заявлено — не судим", "главный из пяти предметов; (1) а", 0),
        ("номер правила в скобках — не пункт", "предметов два: (1) а (157) (2) б", 0),
    ]
    for name, where_, expected in count_cases:
        got = len(declared_counts({"001": {"status": "active", "where": where_}}))
        if got != expected:
            broken.append(f"число предметов, {name}: ожидалось {expected}, вышло {got}")
        print(f"  {got} находок — число предметов: {name}")

    # ── статусы говорят, чего не означают (056) ────────────────────────────
    head = STATUS_SECTION + "\n\n| статус | означает | **не** означает |\n|---|---|---|\n"
    full = "".join(f"| `{w}` | да | **не** означает другое |\n" for w in STATUSES)
    status_cases = [
        ("все четыре со строкой", head + full, {}, 0),
        ("строки нет", head + full.replace("| `unreviewed` | да | **не** означает другое |\n", ""), {}, 1),
        ("клетка пуста", head + full.replace("**не** означает другое |\n| `unreviewed`",
                                             " |\n| `unreviewed`"), {}, 1),
        ("статус ответа вне словаря и без строки", head + full,
         {"001": {"status": "deferred"}}, 1),
        ("строка в соседнем разделе не считается",
         head + full.replace("| `active` | да | **не** означает другое |\n", "")
         + "\n### Другое\n\n| `active` | да | **не** означает |\n", {}, 1),
        ("раздела нет вовсе", full, {}, 1),
    ]
    for name, doc, rules_, expected in status_cases:
        got = len(unsaid_statuses(doc, rules_))
        if got != expected:
            broken.append(f"статусы, {name}: ожидалось находок {expected}, вышло {got}")
        print(f"  {got} находок — статусы: {name}")

    # Документа нет вовсе — это НЕ наш предмет: на него жалуется проверка ссылок,
    # и вторая жалоба о том же сбивала бы с толку.
    rule = {"001": {"status": "active", "where": "нет-такого.md § Ветки — проза"}}
    if dead_sections(rule, lambda _d: None):
        broken.append("раздел: нечитаемый документ дал вторую жалобу о том же")
    print("  пропущено — раздел: документа нет вовсе — жалуется другая проверка")

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: гейт отвергает то, что обязан")
    return 0


#: Слова предела — закрытый словарь контракта ответа каталогу (правило 213):
#: чего машина не держит и почему. КОПИЯ НАМЕРЕННАЯ (071): словарь живёт в
#: заготовке каталога templates/bindings.json, машинно отдельным списком он не
#: публикуется, а подъём контракта ответа сверяет
#: scripts/build_metrics.py::contracts_drift — тогда же перечитывается и этот
#: список.
LIMITS = ("no", "not-yet", "conditional", "refused")

#: Слова механизма — закрытый словарь того же контракта (поле `mechanism`).
#: КОПИЯ НАМЕРЕННАЯ, как LIMITS (071). `process-step` каталог ещё принимает как
#: устаревшее, но здесь его нет: витрина им не пишет, и вернуть его — значит
#: сказать «чем-то держится», не сказав чем. Свой `code` жил вне словаря
#: месяц у 14 ответов, и не спрашивал никто (#267).
MECHANISMS = ("gate", "pipeline", "skill", "document", "none")


def limits(rules: dict[str, dict]) -> list[str]:
    """Слова предела и механизма вне словаря, отказы без замера. Пусто — чисто.

    ЧЕТВЁРТОЕ СЛОВО ЗАКОННО ТОЛЬКО С ЧИСЛОМ. `refused` — машинная половина
    есть, замерена, и строить её отказались, потому что сигнал бил бы по
    разрешённому. Без замера в ``machine_half`` такой ответ неотличим от «не
    смотрели» — и от `no`, сказанного, чтобы не строить (213).

    До этой проверки словарь не спрашивал никто: запись со словом вне него или
    `refused` без числа проходила молча, а сводка каталога считала её как есть.
    """
    found: list[str] = []
    for number, binding in sorted(rules.items()):
        mechanism = binding.get("mechanism")
        if mechanism is not None and mechanism not in MECHANISMS:
            found.append(f"{number}: слово механизма {mechanism!r} не из словаря "
                         f"({', '.join(MECHANISMS)}) — сводка каталога его не считает")
        # «ДЕРЖИТСЯ НИЧЕМ» НЕ БЕСПЛАТНО (182, контракт ответа). Ответ
        # `mechanism: none` обязан назвать машинную половину — что следует из
        # данных и почему не построено. Спрашивалось это только у `refused`;
        # каталог, грейдер, счётчик токенов и глоссарий требуют поле у любого
        # `none` (сводка 8 октября, #286). Разложен ли ответ ВЕРНО — суждение.
        if (binding.get("status") == "active" and binding.get("mechanism") == "none"
                and not str(binding.get("machine_half", "")).strip()):
            found.append(f"{number}: «держится ничем» без machine_half — машинная "
                         f"половина не названа, и ответ неотличим от «не разбирали» (182)")
        word = binding.get("holdable")
        if word is None:
            continue
        if word not in LIMITS:
            found.append(f"{number}: слово предела {word!r} не из словаря "
                         f"({', '.join(LIMITS)})")
        elif word == "refused" and not str(binding.get("machine_half", "")).strip():
            found.append(f"{number}: `refused` без замера в machine_half — отказ, за "
                         f"которым нет числа, неотличим от «не смотрели» (213)")
    return found


#: Адрес ИСПОЛНЯЕМОГО: прогон, действие, скрипт, тест, хук окна. Список видов
#: закрытый — «похоже на путь» приняло бы и документ, а абзац свода прогоном
#: не подтверждается вовсе (139). Формы перечислены поимённо: прогон .yml и
#: .yaml, действие action.yml, скрипт .py и .sh, тест, хук .claude/hooks —
#: шесть видов, каждый в наборе.
RUNNABLE = re.compile(
    r"(?<![\w/.-])(?:\.github/workflows/[\w.-]+\.ya?ml"
    r"|\.github/actions/[\w./-]+/action\.ya?ml"
    r"|scripts/[\w./-]+\.(?:py|sh)"
    r"|tests/[\w./-]+\.py"
    r"|\.claude/hooks/[\w./-]+\.(?:sh|py))")


def unrunnable(rules: dict[str, dict]) -> list[str]:
    """Ответы «держится гейтом/конвейером», не назвавшие ничего исполняемого.

    МЕХАНИЗМ ПОДТВЕРЖДАЕТСЯ ПРОГОНОМ, А НЕ ЧТЕНИЕМ (139). Ответ `gate` или
    `pipeline`, в чьём ``where`` нет ни прогона, ни скрипта, ни теста, обещает
    проверку, которой нет: документ не запускается. Образец — каталог
    (check_bindings) и проект механизмов (test_a_gate_names_something_runnable);
    у витрины на 8 октября таких ответов 0 — гейт держит регресс.

    ЧЕГО НЕ ДЕРЖИТ: что названный скрипт держит ИМЕННО это правило — это
    суждение. Ответа `code` («код держит поведением») больше нет: слова нет в
    словаре контракта, и ``limits`` его отвергает. Поведение, которое не
    краснеет ни в одном наборе, — это `none` с машинной половиной (#267).
    """
    return [f"{number}: «{binding['mechanism']}» без исполняемого адреса — ни прогона, "
            f"ни скрипта, ни теста в where; документ прогоном не подтверждается (139)"
            for number, binding in sorted(rules.items())
            if binding.get("status") == "active"
            and binding.get("mechanism") in ("gate", "pipeline")
            and not RUNNABLE.search(binding.get("where") or "")]


#: Заявленное число предметов: «предметов три», «предметов ПЯТЬ», «предметов 4».
#: Слова — до десяти: больше в одном ответе не перечисляли ни разу.
NUMBER_WORDS = {"два": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6,
                "семь": 7, "восемь": 8, "девять": 9, "десять": 10}
DECLARED = re.compile(rf"предмет(?:ов|а)\s+({'|'.join(NUMBER_WORDS)}|\d{{1,2}})\b", re.I)

#: Пункт перечня: «(1)», «(2)»… Двузначный предел намеренный — номер правила
#: в скобках «(157)» трёхзначен и пунктом не считается.
ITEM = re.compile(r"\((\d{1,2})\)")


#: Словарь статусов контракта ответа каталогу (export/README.md, поле
#: `status`). КОПИЯ НАМЕРЕННАЯ, как LIMITS (071): словарь живёт в таблице
#: контракта, машинно отдельным списком не публикуется, а подъём контракта
#: сверяет scripts/build_metrics.py::contracts_drift — тогда же перечитывается
#: и этот список.
STATUSES = ("active", "rejected", "not-applicable", "unreviewed")

#: Где витрина говорит, что статус НЕ означает (056).
STATUS_DOC = ROOT / ".rules/README.md"
STATUS_SECTION = "## Что означают статусы и чего не означают"
STATUS_ROW = re.compile(r"^\|\s*`([\w-]+)`\s*\|([^|]*)\|([^|]*)\|", re.M)


def unsaid_statuses(doc: str, rules: dict[str, dict]) -> list[str]:
    """Статусы, у которых не написано, чего они НЕ означают (056).

    ЧТО ДЕРЖИТСЯ: вторая половина сигнала НАПИСАНА — у каждого слова
    словаря и у каждого статуса, встречающегося в ответе, есть строка в
    таблице раздела, и её клетка «не означает» несёт отрицание. Образец —
    test_signals глоссария: «не означает» у каждого кода.

    ЧЕГО НЕ ДЕРЖИТ: верна ли написанная граница. Это суждение о смысле.
    """
    start = doc.find(STATUS_SECTION)
    if start < 0:
        return [f"{STATUS_DOC.name}: нет раздела «{STATUS_SECTION[3:]}» — "
                f"статусы читают, не заглядывая в реализацию (056)"]
    tail = doc[start + len(STATUS_SECTION):]
    end = re.search(r"^#{2,3} ", tail, re.M)
    section = tail[:end.start()] if end else tail
    rows = {word: denial for word, _means, denial in STATUS_ROW.findall(section)}
    wanted = sorted(set(STATUSES) | {str(b.get("status")) for b in rules.values()
                                     if b.get("status")})
    found: list[str] = []
    for word in wanted:
        if word not in rows:
            found.append(f"статус `{word}` без строки в таблице «чего не означают» (056)")
        elif not re.search(r"\bне\b", rows[word], re.I):
            found.append(f"статус `{word}`: клетка «не означает» пуста или без "
                         f"отрицания — вторая половина сигнала не написана (056)")
    return found


def declared_counts(rules: dict[str, dict]) -> list[str]:
    """Ответы, где заявленное число предметов расходится с размеченным перечнем.

    ЧТО ДЕРЖИТСЯ (136, разложено надвое по 182). Ответ «предметов N, перебраны
    все» обязан перечислить их пунктами (1)…(N) — каждый номер ровно раз. Так
    у соседа «находок N» сверяется с числом строк (review_findings проекта
    механизмов); у нас перечень — проза, и разметка делает его счётным.

    ЧЕГО НЕ ДЕРЖИТ: что предметов у правила ИМЕННО N — это знание о правиле.
    Машина ловит число, пережившее перечень, а не перечень, не доросший до
    правила. Случай, ради которого гейт заведён, нашёлся на его же разметке:
    ответ 142 заявлял «ЧЕТЫРЕ» при пяти адресатах в собственном тексте.
    """
    found: list[str] = []
    for number, binding in sorted(rules.items()):
        text = " ".join(str(binding.get(field, "")) for field in ("where", "why"))
        said = DECLARED.search(text)
        if not said:
            continue
        word = said.group(1).lower()
        expected = NUMBER_WORDS.get(word) or int(word)
        items = [int(m) for m in ITEM.findall(text)]
        if sorted(items) != list(range(1, expected + 1)):
            found.append(f"{number}: заявлено предметов {expected}, а пункты перечня — "
                         f"{items or 'не размечены'}; ждётся (1)…({expected}), каждый раз (136)")
    return found


def unchecked(rules: dict[str, dict]) -> list[tuple[str, str]]:
    """Ответы «предмета нет», которые не проверяет ничто. Очередь на перечитывание.

    НЕ ГЕЙТ, А ПОДСКАЗКА, и это решение, а не слабость. Перечитан ли ответ,
    машине не видно: отметка «проверено» устарела бы ровно так же, как сам
    ответ, и заводить её значило бы завести второе враньё поверх первого.

    Зато видно, какие ответы держатся **одной прозой**. Их и печатает эта
    очередь — по одному предмету за заход, а не «когда-нибудь целиком».

    Цена известна и измерена: 3 сентября из трёх наугад перечитанных ответов
    «предмета нет» неверными оказались ТРИ. Двум из них правило было уже
    действующим — витрина отвечала «предмета нет» месяцами. Половина корпуса
    ответов на прозе — не фон, а очередь.
    """
    return [(number, str(binding.get("why", "")))
            for number, binding in sorted(rules.items())
            if binding.get("status") == "not-applicable" and not binding.get("refuted_by")]


def debt(rules: dict) -> tuple[int, int]:
    """Незакрытая работа по правилам: не рассмотрено · держится ничем.

    ЗАЧЕМ ЭТО ПЕЧАТАЕТСЯ ВСЕГДА И ПЕРВЫМ (правило 177). Разбор правил
    конкурирует с остальной работой за одно внимание и проигрывает по простой
    причине: у работы есть заказчик, а у разбора его нет. Правило без механизма
    сегодня ничего не ломает — оно ломает потом и не признаётся в этом ничем:
    «действует, но держится ничем» — ЗЕЛЁНОЕ состояние во всех отчётах.

    Замер каталога 3 сентября: 47 таких правил на трёх проектах из четырёх, у
    витрины — 15. Держалось это тем, что владелец напоминал вслух, то есть
    становился единственной точкой отказа.

    Числа печатаются и когда они нули: «держится ничем 0» — это состояние, а не
    пустота (027).

    ЗАСЛОН НАЗЫВАЕТ, А НЕ ЗАПРЕЩАЕТ. Остановить работу окна механизм не может и
    не притворяется: он ставит числа туда, где их нельзя не увидеть. Отсрочка
    разбора остаётся законной — но становится решением, а не следствием того,
    что долг невидим.

    Третьего числа — правил каталога, на которые ответа нет вовсе, — здесь нет
    намеренно: его знает только сборка, ходящая в каталог, и она его печатает.
    Выдумывать его локально значило бы печатать ноль вместо «не знаю».
    """
    unreviewed = sum(1 for b in rules.values() if b.get("status") == "unreviewed")
    unheld = sum(1 for b in rules.values()
                 if b.get("status") == "active" and b.get("mechanism") == "none")
    return unreviewed, unheld


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()

    if "--queue" in sys.argv[1:]:
        # Очередь на перечитывание. Печатается всегда с нулевым кодом: это
        # рабочий список, а не находка, и красить им прогон нечем (039).
        rules = json.loads(BINDINGS.read_text(encoding="utf-8"))["rules"]
        queue = unchecked(rules)
        total = sum(1 for b in rules.values() if b.get("status") == "not-applicable")
        print(f"ответов «предмета нет»: {total}; проверяется опровержением "
              f"{total - len(queue)}, держится прозой {len(queue)}")
        for number, why in queue:
            print(f"  {number}: {checks.clip(why, 96)}")
        return 0

    try:
        bindings = json.loads(BINDINGS.read_text(encoding="utf-8"))
        # Долг по правилам печатается ПЕРВЫМ и до находок: очередь новой работы
        # идёт после незакрытой старой, а не наоборот (177).
        unreviewed, unheld = debt(bindings["rules"])
        print(f"долг по правилам: не рассмотрено {unreviewed} · "
              f"держится ничем {unheld}")
        dead, checked = audit(bindings["rules"])
        # Разделы документов — вторая половина того же предмета: путь к файлу
        # живой, а раздел внутри переименован. Читается тот же файл, что и для
        # ссылок на код, и нечитаемый документ отвечает None, а не пустотой:
        # «файла нет» ловит проверка выше, и второй жалобы на него не нужно.
        def sections(document: str) -> set[str] | None:
            found = ROOT / document
            try:
                return anchors(found.read_text(encoding="utf-8"))
            except OSError:
                return None

        dead += dead_sections(bindings["rules"], sections)
        vocabulary = limits(bindings["rules"])
        unrun = unrunnable(bindings["rules"])
        counts = declared_counts(bindings["rules"])
        unsaid = unsaid_statuses(STATUS_DOC.read_text(encoding="utf-8"), bindings["rules"])
        # Существование предмета спрашивается у дерева одной командой — без
        # сети, как и требует правило: то, что видно локально.
        alive = refuted(
            bindings["rules"],
            lambda glob: [str(p.relative_to(ROOT)) for p in ROOT.glob(glob)
                          if p.is_file() and ".git" not in p.relative_to(ROOT).parts],
            lambda path: (ROOT / path).read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError, SyntaxError) as e:
        # Третий исход, а не разновидность второго: находку чинит автор, а
        # неотработавшую проверку — тот, кто её запускает (правило 039).
        print(f"проверка не отработала: ответ каталогу не разобран — {e}", file=sys.stderr)
        return 2

    if alive:
        print(checks.annotate("error", f"ответы «предмета нет» опровергаются: {len(alive)}"),
              file=sys.stderr)
        for line in alive:
            print(f"  {line}", file=sys.stderr)
        print("\nОтвет «этого у нас нет» — утверждение о действительности, и оно устарело."
              "\nЛибо предмет появился и вердикт стал действующим, либо уберите refuted_by.",
              file=sys.stderr)

    if vocabulary:
        print(checks.annotate("error", f"слова вне словаря контракта: {len(vocabulary)}"),
              file=sys.stderr)
        for line in vocabulary:
            print(f"  {line}", file=sys.stderr)
        print(f"\nСловари закрыты: предел — {', '.join(LIMITS)}; механизм — "
              f"{', '.join(MECHANISMS)}. Отказ строить механизм законен "
              "только с замером — что считается командой и сколько раз сигнал сработал "
              "бы на законном.", file=sys.stderr)

    if unrun:
        print(checks.annotate("error", f"ответы «держится гейтом» без исполняемого "
                              f"адреса: {len(unrun)}"), file=sys.stderr)
        for line in unrun:
            print(f"  {line}", file=sys.stderr)
        print("\nНазовите прогон, скрипт или тест, которым правило держится, — или "
              "поменяйте механизм на document: абзац не запускается.", file=sys.stderr)

    if unsaid:
        print(checks.annotate("error", f"статусы без «не означает»: {len(unsaid)}"),
              file=sys.stderr)
        for line in unsaid:
            print(f"  {line}", file=sys.stderr)
        print(f"\nСтатус читают, не заглядывая в реализацию: у каждого — строка в "
              f"{STATUS_DOC.name} § {STATUS_SECTION[3:]}.", file=sys.stderr)

    if counts:
        print(checks.annotate("error", f"число предметов разошлось с перечнем: {len(counts)}"),
              file=sys.stderr)
        for line in counts:
            print(f"  {line}", file=sys.stderr)
        print("\nОтвет «предметов N, перебраны все» перечисляет их пунктами (1)…(N): либо "
              "число пережило перечень, либо перечень не размечен.", file=sys.stderr)

    if dead:
        print(checks.annotate("error", f"вердикты показывают в пустоту, мёртвых ссылок: {len(dead)}"), file=sys.stderr)
        for line in dead:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nВердикт — утверждение о текущем коде. Либо поправьте ссылку, либо "
            "пересмотрите вердикт: правило могло перестать держаться.",
            file=sys.stderr,
        )
        return 1
    if alive or vocabulary or unrun or counts or unsaid:
        return 1

    checkable = sum(1 for b in bindings["rules"].values() if b.get("refuted_by"))
    print(f"ссылок в вердиктах: {checked}, все живые; "
          f"ответов «предмета нет» с проверяемым опровержением: {checkable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
