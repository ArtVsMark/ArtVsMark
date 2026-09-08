#!/usr/bin/env python3
"""Собирает фрагменты `changelog.d/*.md` в общий `CHANGELOG.md`.

ЗАЧЕМ ФАЙЛАМИ, А НЕ СТРОКОЙ В ОБЩЕМ ЖУРНАЛЕ. Два файла с разными именами не
конфликтуют никогда. Строка в общем файле конфликтует всегда, если её пишут две
ветки, — и предмет здесь живой, а не заимствованный у соседей: 8 сентября две
ветки подряд встали с конфликтом в ``HISTORY.md``, потому что обе дописывали
свой раздел в конец. До этого дня свод витрины прямо объяснял, почему фрагменты
ей не нужны: «один автор и одна ветка». Довод перестал быть верным раньше, чем
его перечитали.

ЧЕМ ЭТО НЕ ЯВЛЯЕТСЯ. ``CHANGELOG.md`` отвечает «что изменилось», а
``HISTORY.md`` — «почему так решили». Первый читают за новостями, второй — чтобы
не переоткрывать закрытый вопрос. Причина в строку не влезает и не должна: для
неё есть тело изменения.

ФОРМАТ ИМЕНИ — ``<слаг>.<секция>.md``, и секция берётся ИЗ ИМЕНИ, а не из текста
внутри. Имя видно в списке файлов, в диффе и в проверке; строка внутри — только
после открытия. Разъехаться им негде, потому что источник один.

Соглашение общее с грейдером, каталогом правил и ``Claude-Code_Usage-Token``:
одно на четыре проекта дешевле четырёх (то же решение, что у имён веток).

Запуск::

    python scripts/collect_changelog.py --check     # формат фрагментов
    python scripts/collect_changelog.py --preview   # как соберётся
    python scripts/collect_changelog.py --collect   # перенести и удалить файлы

Исходы: 0 — чисто или собрано; 1 — находка: фрагмент не по формату; 2 — проверка
не отработала (нет каталога, нет раздела в журнале, запись не удалась).
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import checks

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRAGMENTS = ROOT / "changelog.d"
CHANGELOG = ROOT / "CHANGELOG.md"

#: Раздел, куда уезжают фрагменты. У витрины нет выпусков, и версии здесь не
#: выдумываются: раздел закрывается датой, когда накопленное перестаёт
#: помещаться в обозримое, — решением владельца, а не расписанием.
UNRELEASED = "## [Не выпущено]"

#: Секции и их подписи в журнале. Список ЗАКРЫТ: секция, которой здесь нет, —
#: находка, а не новая секция. Иначе `fix` и `fixed` разъедутся молча.
SECTIONS = {
    "added": "Добавлено",
    "changed": "Изменено",
    "fixed": "Починено",
    "removed": "Убрано",
    "internal": "Внутреннее",
}


def fragments() -> list[pathlib.Path]:
    """Файлы фрагментов, кроме соглашения. Порядок — по имени, он же в выводе."""
    return sorted(p for p in FRAGMENTS.glob("*.md") if p.name != "README.md")


def parse(path: pathlib.Path) -> tuple[str, str, list[str]]:
    """Секция, текст и находки одного фрагмента.

    Пустая строка — не запись: фрагмент, добавленный «чтобы гейт замолчал»,
    выглядит как память об изменении, которой нет (правило 046).
    """
    found: list[str] = []
    parts = path.name[: -len(".md")].rsplit(".", 1)
    section = parts[1] if len(parts) == 2 else ""
    if section not in SECTIONS:
        found.append(f"{path.name}: секция {section or '—'!r} не из списка "
                     f"({', '.join(sorted(SECTIONS))})")
    text = " ".join(path.read_text(encoding="utf-8").split())
    if not text:
        found.append(f"{path.name}: пусто — запись без текста хуже отсутствующей")
    if text.startswith("- "):
        found.append(f"{path.name}: ведущий дефис подставит сборка, убирается из текста")
    return section, text, found


def collected() -> tuple[dict[str, list[str]], list[str]]:
    """Записи по секциям и находки по всем фрагментам."""
    by_section: dict[str, list[str]] = {}
    found: list[str] = []
    for path in fragments():
        section, text, complaints = parse(path)
        found += complaints
        if not complaints:
            by_section.setdefault(section, []).append(text)
    return by_section, found


def render(by_section: dict[str, list[str]]) -> str:
    """Записи в том виде, в каком они лягут под заголовок раздела."""
    block = []
    for key, title in SECTIONS.items():
        if key not in by_section:
            continue
        block.append(f"### {title}")
        block += [f"- {line}" for line in by_section[key]]
        block.append("")
    return "\n".join(block).rstrip("\n")


def merge(text: str, block: str) -> str:
    """Вставляет блок сразу под заголовок «не выпущено», сохраняя прежнее."""
    if UNRELEASED not in text:
        raise ValueError(f"в {CHANGELOG.name} нет раздела {UNRELEASED!r}")
    head, tail = text.split(UNRELEASED, 1)
    return f"{head}{UNRELEASED}\n\n{block}\n{tail.lstrip(chr(10))}"


def selftest() -> int:
    """Прогоняет через сборщик то, что он обязан отвергнуть и обязан пропустить."""
    broken: list[str] = []

    name_cases = [
        ("правильное имя", "logo-loop.fixed.md", "починили", 0),
        ("секции нет вовсе", "logo-loop.md", "починили", 1),
        ("секция не из списка", "logo-loop.fix.md", "починили", 1),
        ("пустой фрагмент", "logo-loop.added.md", "   \n", 1),
        ("ведущий дефис", "logo-loop.added.md", "- добавили", 1),
    ]
    import tempfile                                            # noqa: PLC0415
    with tempfile.TemporaryDirectory() as tmp:
        for name, filename, body, expected in name_cases:
            path = pathlib.Path(tmp) / filename
            path.write_text(body, encoding="utf-8")
            _, _, found = parse(path)
            if len(found) != expected:
                broken.append(f"фрагмент, {name}: ожидалось находок {expected}, "
                              f"вышло {len(found)} ({found})")
            print(f"  {'отвергнут' if found else 'пропущен '} — фрагмент: {name}")

    # Порядок секций закреплён списком, а не сортировкой по алфавиту: читатель
    # ждёт «добавлено» раньше «внутреннего», а не «added» раньше «fixed».
    block = render({"internal": ["третье"], "added": ["первое"], "fixed": ["второе"]})
    if block.index("Добавлено") > block.index("Починено") > block.index("Внутреннее"):
        broken.append(f"порядок секций не по списку:\n{block}")
    print("  порядок   — секции идут по списку, а не по алфавиту")

    # Вставка сохраняет прежнее содержимое: журнал не переписывается, он растёт.
    merged = merge(f"# Ж\n\n{UNRELEASED}\n\n### Починено\n- прежнее\n", "### Добавлено\n- новое")
    if "прежнее" not in merged or "новое" not in merged:
        broken.append(f"вставка потеряла записи:\n{merged}")
    print("  вставка   — прежние записи на месте")

    try:
        merge("# Журнал без раздела\n", "### Добавлено\n- новое")
    except ValueError:
        print("  отвергнут — журнал без раздела «не выпущено»")
    else:
        broken.append("журнал без раздела принят — записи ушли бы в никуда")

    if broken:
        print(checks.annotate("error", "самопроверка провалена"), file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: формат фрагмента и порядок сборки держат объявленное")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--check", action="store_true", help="только проверить формат")
    parser.add_argument("--preview", action="store_true", help="показать сборку, не меняя файлов")
    parser.add_argument("--collect", action="store_true", help="перенести в журнал и удалить")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if not FRAGMENTS.is_dir():
        print(checks.annotate("error", f"каталога {FRAGMENTS.name}/ нет — "
                              f"проверять нечего"), file=sys.stderr)
        return 2

    by_section, found = collected()
    if found:
        print(checks.annotate("error", f"фрагменты не по формату: {len(found)}"),
              file=sys.stderr)
        for line in found:
            print(f"  • {line}", file=sys.stderr)
        print("\n  Имя: changelog.d/<слаг>.<секция>.md, внутри одна строка без "
              "ведущего\n  дефиса. Формат и примеры — changelog.d/README.md.",
              file=sys.stderr)
        return 1

    block = render(by_section)
    if args.check:
        print(f"фрагменты в порядке: {sum(len(v) for v in by_section.values())}")
        return 0
    if args.preview:
        print(block if block else "фрагментов нет — собирать нечего")
        return 0
    if not args.collect:
        print(f"фрагментов: {sum(len(v) for v in by_section.values())}. "
              f"--preview покажет сборку, --collect перенесёт в журнал")
        return 0

    if not block:
        print("фрагментов нет — журнал не тронут")
        return 0
    try:
        CHANGELOG.write_text(merge(CHANGELOG.read_text(encoding="utf-8"), block),
                             encoding="utf-8")
        for path in fragments():
            path.unlink()
    except (OSError, ValueError) as err:
        print(checks.annotate("error", f"собрать не удалось: {err}"), file=sys.stderr)
        return 2
    print(f"собрано записей: {sum(len(v) for v in by_section.values())}, "
          f"фрагменты удалены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
