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

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: гейт отвергает то, что обязан")
    return 0


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()

    try:
        bindings = json.loads(BINDINGS.read_text(encoding="utf-8"))
        dead, checked = audit(bindings["rules"])
    except (OSError, ValueError, SyntaxError) as e:
        # Третий исход, а не разновидность второго: находку чинит автор, а
        # неотработавшую проверку — тот, кто её запускает (правило 039).
        print(f"проверка не отработала: ответ каталогу не разобран — {e}", file=sys.stderr)
        return 2

    if dead:
        print("вердикты показывают в пустоту:", file=sys.stderr)
        for line in dead:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nВердикт — утверждение о текущем коде. Либо поправьте ссылку, либо "
            "пересмотрите вердикт: правило могло перестать держаться.",
            file=sys.stderr,
        )
        return 1

    print(f"ссылок в вердиктах: {checked}, все живые")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
