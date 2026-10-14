#!/usr/bin/env python3
"""Источники истины свода — данные под гейтом, а не таблица в прозе (181).

ЗАЧЕМ. Свод читают по частям: окно приходит в тот раздел, куда его привела
задача, и соседних не открывает. Два абзаца, каждый из которых называет себя
единственным источником одного и того же, по отдельности верны — и оба
перестают действовать. Таблица «Источники истины» жила в CLAUDE.md прозой, и
сверять её было нечем: 14 октября в своде стояло исключительное утверждение
(«задачи этого репозитория — единственный источник статусов»), которого в
таблице не было вовсе.

ВСЕ ПЯТЕРО СОСЕДЕЙ ДЕРЖАТ ЭТО ГЕЙТОМ. Образец — check_sources_of_truth.py
грейдера: объявление «предмет → адрес», и три отказа — незаявленное
утверждение, объявление, пережившее текст, два адреса у одного предмета. Здесь
к ним два своих:

* таблица в CLAUDE.md собирается из данных (``--write``) и сверяется с ними:
  её читает каждое окно при старте, поэтому она остаётся, но руками больше не
  правится (125);
* адрес внутри дерева обязан существовать; ``external`` — адрес вне дерева
  (каталог, трекер), его деревом не проверить, и это названо.

ЧЕГО ГЕЙТ НЕ ДЕЛАЕТ (057). Утверждение, написанное оборотом вне ``MARKERS``,
он не увидит: найти незаписанное машина не может. Список оборотов закрытый и
взят замером 14 октября по CLAUDE.md и .rules/*.md (206).

Запуск::

    python scripts/check_sources.py            # сверка
    python scripts/check_sources.py --write    # пересобрать таблицу в CLAUDE.md
    python scripts/check_sources.py --selftest

Исходы: 0 — сходится; 1 — расхождение названо; 2 — проверка не отработала
(нет данных, свода или меток таблицы).
"""

import argparse
import json
import pathlib
import re
import sys
import tempfile

import checks

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / ".rules" / "sources.json"
RULEBOOK = ROOT / "CLAUDE.md"
#: Метки таблицы в своде: между ними — собранное, а не написанное.
OPEN, CLOSE = "<!-- sources -->", "<!-- /sources -->"
#: Обороты исключительности. Замер 14 октября: в своде — «единственный источник»
#: (статусы работы); прочие взяты у грейдера — их пока нет, но они той же формы.
MARKERS = ("единственный источник", "единственное место", "источник истины",
           "только отсюда", "только оттуда")


def render(subjects: list[dict]) -> str:
    """Таблица свода из данных — ровно то, что стоит между метками."""
    rows = ["| Тема | Канонический документ |", "|---|---|"]
    for item in subjects:
        address = str(item["address"])
        shown = address if item.get("external") else f"[`{address}`]({address})"
        rows.append(f"| {item['subject']} | {shown} |")
    return "\n".join(rows)


def _plain(text: str) -> str:
    """Текст без выделения: «**единственный** источник» читается как оборот."""
    return " ".join(text.replace("**", "").replace("`", "").split())


def exclusive_paragraphs(rulebook: str) -> list[str]:
    """Абзацы свода с оборотом исключительности, кроме самой таблицы и заголовков."""
    body = re.sub(re.escape(OPEN) + r".*?" + re.escape(CLOSE), "", rulebook, flags=re.S)
    return [para for block in checks.paragraphs(body)
            if (para := _plain(block)) and not para.startswith("#")
            and any(marker in para.lower() for marker in MARKERS)]


def audit(subjects: list[dict], rulebook: str, exists) -> list[str]:
    """Расхождения данных со сводом и деревом. Пусто — сходится."""
    found: list[str] = []
    start, end = rulebook.find(OPEN), rulebook.find(CLOSE)
    if start < 0 or end < start:
        raise ValueError(f"в своде нет меток таблицы {OPEN} … {CLOSE}")
    if rulebook[start + len(OPEN):end].strip() != render(subjects):
        found.append("таблица «Источники истины» в CLAUDE.md разошлась с .rules/sources.json — "
                     "пересоберите: python scripts/check_sources.py --write")
    seen: dict[str, set[str]] = {}
    for item in subjects:
        seen.setdefault(str(item["subject"]), set()).add(str(item["address"]))
        if not item.get("external") and not exists(str(item["address"])):
            found.append(f"{item['subject']}: адреса {item['address']} в дереве нет")
    found += [f"{subject}: один предмет назван разными адресами — {', '.join(sorted(a))}"
              for subject, a in sorted(seen.items()) if len(a) > 1]
    claims = [str(c) for item in subjects for c in item.get("claims") or []]
    paragraphs = exclusive_paragraphs(rulebook)
    found += [f"исключительное утверждение не объявлено — назовите предмет и адрес в "
              f"sources.json: «{checks.clip(para, 120)}»"
              for para in paragraphs if not any(claim in para for claim in claims)]
    joined = "\n".join(paragraphs)
    found += [f"объявленная фраза «{claim}» в своде больше не стоит — уберите её из "
              f"sources.json" for claim in claims if claim not in joined]
    return found


def selftest() -> int:
    """Обе стороны (140): каждый отказ — подделкой, сходящееся — молчит."""
    broken: list[str] = []
    subjects = [{"subject": "витрина", "address": "README.md"},
                {"subject": "статусы", "address": "трекер", "external": True,
                 "claims": ["единственный источник статусов"]}]
    good = (f"# Свод\n\n{OPEN}\n{render(subjects)}\n{CLOSE}\n\n"
            "Задачи — **единственный** источник статусов.\n")
    present = {"README.md"}.__contains__
    twice = subjects + [{"subject": "витрина", "address": "HISTORY.md", "external": True}]
    cases = [
        ("всё сходится", subjects, good, 0),
        ("таблица правлена руками", subjects, good.replace("| витрина |", "| страница |"), 1),
        ("адреса нет в дереве", [{**subjects[0], "address": "NOPE.md"}, subjects[1]],
         good.replace("README.md", "NOPE.md"), 1),
        ("два адреса у предмета", twice, good.replace(render(subjects), render(twice)), 1),
        ("утверждение не объявлено", subjects,
         good + "\nПланы — единственное место для решений.\n", 1),
        ("объявление пережило текст", subjects,
         good.replace("Задачи — **единственный** источник статусов.\n", ""), 1),
    ]
    for name, items, text, expected in cases:
        got = len(audit(items, text, present))
        if got != expected:
            broken.append(f"{name}: ждали находок {expected}, вышло {got}")
        print(f"  {'верно' if got == expected else 'СБОЙ '} — {name}")
    try:
        audit(subjects, "# свод без меток\n", present)
        broken.append("свод без меток таблицы принят молча")
    except ValueError:
        pass

    # Исходы main прогоняются вызовом (186): живое дерево сходится — 0,
    # правленная руками таблица — 1, нет данных — 2.
    if main([]) != 0:
        broken.append("живое дерево: main вернул не 0")
    with tempfile.TemporaryDirectory(dir=checks.runner_temp()) as scratch:
        data, rulebook = pathlib.Path(scratch, "sources.json"), pathlib.Path(scratch, "CLAUDE.md")
        data.write_text(json.dumps({"subjects": subjects[:1]}), encoding="utf-8")
        rulebook.write_text(f"{OPEN}\n| руками |\n{CLOSE}\n", encoding="utf-8")
        if main(["--data", str(data), "--rulebook", str(rulebook)]) != 1:
            broken.append("таблица правлена руками: main вернул не 1")
        if main(["--data", str(data) + ".nope", "--rulebook", str(rulebook)]) != 2:
            broken.append("нет данных: main вернул не 2")

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: источники истины сверяются с данными, деревом и сводом")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--write", action="store_true", help="пересобрать таблицу в CLAUDE.md")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--data", type=pathlib.Path, default=DATA, help=argparse.SUPPRESS)
    parser.add_argument("--rulebook", type=pathlib.Path, default=RULEBOOK, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        subjects = json.loads(args.data.read_text(encoding="utf-8"))["subjects"]
        rulebook = args.rulebook.read_text(encoding="utf-8")
        if args.write:
            start, end = rulebook.find(OPEN), rulebook.find(CLOSE)
            if start < 0 or end < start:
                raise ValueError(f"в своде нет меток таблицы {OPEN} … {CLOSE}")
            args.rulebook.write_text(rulebook[:start + len(OPEN)] + "\n" + render(subjects) + "\n"
                                + rulebook[end:], encoding="utf-8")
            rulebook = args.rulebook.read_text(encoding="utf-8")
        found = audit(subjects, rulebook, lambda path: (ROOT / path).exists())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(checks.annotate("error", f"проверка не отработала: {error}"), file=sys.stderr)
        return 2
    for line in found:
        print(checks.annotate("error", line), file=sys.stderr)
    if found:
        return 1
    print(f"источники истины сходятся: предметов {len(subjects)}, исключительных "
          f"утверждений в своде {len(exclusive_paragraphs(rulebook))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
