#!/usr/bin/env python3
"""Проверяет, что у каждого файла репозитория есть ведущий.

Правило 082 требует проверять полноту ролей **обходом артефактов**, а не
чтением списка: артефакт без владельца называет недостающее направление сам.
Обход, сделанный руками, нашёл пять пластов сверх четырёх записанных — и
устарел бы к первому же новому файлу, потому что таблица в ``roles.md`` не
знает, что дерево изменилось.

Поэтому таблица покрытия — вход для проверки, а не иллюстрация. Сверка идёт в
обе стороны, и вторая важнее первой:

* **файл без строки** — новый артефакт приехал без ведущего;
* **строка без файлов** — пласт назван, а предмета у него больше нет. Сторож,
  не нашедший предмета, обязан упасть (правило 075): молча пропустив мёртвую
  строку, таблица начинает описывать репозиторий, которого нет.

Список файлов берётся у git, а не обходом каталога: иначе в него попадут
``.git``, кэш Python и всё, что лежит рядом, но репозиторием не является.
Исходы: 0 — чисто; 1 — есть находки; 2 — проверка не отработала.
"""

from __future__ import annotations

import fnmatch
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROLES = ROOT / ".rules/roles.md"
# Таблица живёт между маркерами: так её видно и человеку, и разбору, а
# соседние таблицы файла под проверку не попадают.
COVERAGE = re.compile(r"<!--покрытие-->(.*?)<!--/покрытие-->", re.DOTALL)
ROW = re.compile(r"^\|\s*`(?P<glob>[^`]+)`\s*\|(?P<rest>.*)\|\s*$", re.MULTILINE)


def patterns(text: str) -> list[str]:
    """Образцы артефактов из таблицы покрытия."""
    table = COVERAGE.search(text)
    if table is None:
        raise SystemExit("в .rules/roles.md нет таблицы покрытия между маркерами")
    return [match.group("glob") for match in ROW.finditer(table.group(1))]


def tracked() -> list[str]:
    """Файлы репозитория глазами git."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True, text=True, check=True,
    )
    return [line for line in out.stdout.splitlines() if line]


def audit(globs: list[str], files: list[str]) -> tuple[list[str], list[str]]:
    """Файлы без строки и строки без файлов."""
    orphans = [f for f in files if not any(fnmatch.fnmatch(f, g) for g in globs)]
    barren = [g for g in globs if not any(fnmatch.fnmatch(f, g) for f in files)]
    return orphans, barren


def selftest() -> int:
    """Прогоняет через проверку то, что она обязана отвергнуть и пропустить.

    Правило 140, и обе его стороны: набор из одних «обязан отвергнуть» не видит
    ложного отказа, а он здесь дороже пропуска — гейт, ругающийся на верное,
    начинают обходить.
    """
    cases = [
        ("файл без строки", ["README.md"], ["README.md", "scripts/new.py"], True),
        ("строка без файлов", ["README.md", "scripts/gone.py"], ["README.md"], True),
        ("образец со звёздочкой", ["assets/*.svg"], ["assets/header-dark.svg"], False),
        ("точное совпадение", ["CLAUDE.md"], ["CLAUDE.md"], False),
        ("файл со скрытым каталогом", [".github/workflows/*.yml"],
         [".github/workflows/pr-check.yml"], False),
    ]
    broken = []
    for name, globs, files, must_reject in cases:
        orphans, barren = audit(globs, files)
        rejected = bool(orphans or barren)
        if rejected is not must_reject:
            broken.append(f"{name}: ожидалось {'отказ' if must_reject else 'пропуск'}, вышло наоборот")
        print(f"  {'отвергнут' if rejected else 'пропущен '} — {name}")

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
        globs = patterns(ROLES.read_text(encoding="utf-8"))
        files = tracked()
        orphans, barren = audit(globs, files)
    except (OSError, ValueError) as e:
        print(f"проверка не отработала: роли или список файлов не прочитаны — {e}",
              file=sys.stderr)
        return 2

    if orphans:
        print("файлы без ведущего:", file=sys.stderr)
        for path in orphans:
            print(f"  {path}", file=sys.stderr)
        print(
            "\nАртефакт без владельца называет недостающее направление сам "
            "(правило 082). Допишите строку в .rules/roles.md — с пластом и тем, "
            "кто его ведёт, а не только с именем файла.",
            file=sys.stderr,
        )
    if barren:
        print("строки без артефактов:", file=sys.stderr)
        for glob in barren:
            print(f"  {glob}", file=sys.stderr)
        print(
            "\nПласт назван, а предмета у него нет. Уберите строку или верните "
            "файл: таблица описывает репозиторий, а не намерения.",
            file=sys.stderr,
        )
    if orphans or barren:
        return 1

    print(f"покрытие пластов: файлов {len(files)}, строк {len(globs)}, без ведущего нет")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
