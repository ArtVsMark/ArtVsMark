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
* ссылки на разделы (``§``) не проверяются: заголовок — не имя в коде, и
  сверять его пришлось бы по написанию.
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


def refuted(rules: dict[str, dict], exists) -> list[str]:
    """Ответы «предмета нет», у которых предмет нашёлся.

    ОТВЕТ «ЭТОГО У НАС НЕТ» — УТВЕРЖДЕНИЕ О ДЕЙСТВИТЕЛЬНОСТИ, а не оборот речи,
    и устаревает оно молча: прозу не двигает никакой механизм, а выглядит она
    осознанным решением (правило 175). Проверяется подкласс, сводимый к наличию
    объекта: вердикт называет его сам, полем ``refuted_by`` — образцом пути,
    существование которого опровергает ответ.

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
        pattern = binding.get("refuted_by")
        if not pattern:
            continue
        hits = exists(pattern)
        if hits:
            found.append(f"{number}: ответ «предмета нет» опровергается — {pattern} "
                         f"существует ({', '.join(sorted(hits)[:3])}). Утверждение о "
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
        for match in REFERENCE.finditer(claim):
            path, anchor = match.group("path"), match.group("anchor")
            checked += 1
            file = locate(path)
            if file is None:
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
        ("ссылка на раздел", {"022": {"where": "CLAUDE.md § Источники истины"}}, False),
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
         {"053": {"status": "not-applicable", "refuted_by": "x.yml"}}, ["x.yml"], True),
        ("предмета нет — молчим",
         {"053": {"status": "not-applicable", "refuted_by": "x.yml"}}, [], False),
        ("опровержение не названо — не наше дело",
         {"053": {"status": "not-applicable", "why": "очереди нет"}}, ["x.yml"], False),
        ("действующий вердикт поля не несёт",
         {"011": {"status": "active", "where": "metrics.yml"}}, ["x.yml"], False),
    ]
    for name, rules, hits, must_reject in refute_cases:
        found = bool(refuted(rules, lambda glob, h=hits: h))
        if found is not must_reject:
            broken.append(f"опровержение, {name}: ожидалось "
                          f"{'отказ' if must_reject else 'пропуск'}, вышло {found}")
        print(f"  {'отвергнут' if found else 'пропущен '} — опровержение: {name}")

    # Находка обязана назвать НОМЕР и НАЙДЕННОЕ: «что-то устарело» отправляет
    # читающего искать предмет самому.
    said = refuted({"053": {"status": "not-applicable", "refuted_by": "q.yml"}},
                   lambda glob: ["q.yml"])
    if not (said and "053" in said[0] and "q.yml" in said[0]):
        broken.append("опровержение: находка не называет номер и найденное")

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: гейт отвергает то, что обязан")
    return 0


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
            print(f"  {number}: {why[:96]}")
        return 0

    try:
        bindings = json.loads(BINDINGS.read_text(encoding="utf-8"))
        # Долг по правилам печатается ПЕРВЫМ и до находок: очередь новой работы
        # идёт после незакрытой старой, а не наоборот (177).
        unreviewed, unheld = debt(bindings["rules"])
        print(f"долг по правилам: не рассмотрено {unreviewed} · "
              f"держится ничем {unheld}")
        dead, checked = audit(bindings["rules"])
        # Существование предмета спрашивается у дерева одной командой — без
        # сети, как и требует правило: то, что видно локально.
        alive = refuted(bindings["rules"], lambda glob: [str(p.relative_to(ROOT))
                                                        for p in ROOT.glob(glob)])
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
    if alive:
        return 1

    checkable = sum(1 for b in bindings["rules"].values() if b.get("refuted_by"))
    print(f"ссылок в вердиктах: {checked}, все живые; "
          f"ответов «предмета нет» с проверяемым опровержением: {checkable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
