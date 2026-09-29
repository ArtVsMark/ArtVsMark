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

ЕДИНИЦА — МЕСЯЦ, КАК У ЖУРНАЛА РЕШЕНИЙ. Раздел ``## Сентябрь 2026``; повторный
сбор за тот же месяц дописывает в существующий раздел, новый месяц ложится
выше прежних. Записи внутри секции идут по номеру изменения, а не по имени
файла: слаг говорит о теме, номер — о порядке слияния.

ПОЧЕМУ СОБИРАЕТ ПРОГОН, А НЕ «КОГДА НАКОПИТСЯ». Здесь стояло: раздел
закрывается, когда накопленное перестаёт помещаться в обозримое, — решением
владельца. Решения не случилось ни разу: за три недели легли 62 фрагмента, а
в журнале не было ни одной строки. Шаг, который держится памятью, механизмом
не является — тот же вывод, что у стоп-крана. Сбор запускает
.github/workflows/changelog.yml первого числа, за прошедший месяц.

Запуск::

    python scripts/collect_changelog.py --check                  # формат фрагментов
    python scripts/collect_changelog.py --preview --month 2026-09 # как соберётся
    python scripts/collect_changelog.py --collect --month 2026-09 # перенести и удалить

Исходы: 0 — чисто или собрано; 1 — находка: фрагмент не по формату; 2 — проверка
не отработала (нет каталога, нет раздела в журнале, запись не удалась).
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

import checks

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRAGMENTS = ROOT / "changelog.d"
CHANGELOG = ROOT / "CHANGELOG.md"

#: Месяц сбора — ``ГГГГ-ММ``: его считает прогон, и в имени нет языка.
MONTH = re.compile(r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])$")

#: Номер изменения в записи. По нему записи идут в порядке слияния.
ENTRY_NUMBER = re.compile(r"\(#(\d+)\)")

#: Секции и их подписи в журнале. Список ЗАКРЫТ: секция, которой здесь нет, —
#: находка, а не новая секция. Иначе `fix` и `fixed` разъедутся молча.
SECTIONS = {
    "added": "Добавлено",
    "changed": "Изменено",
    "fixed": "Починено",
    "removed": "Убрано",
    "internal": "Внутреннее",
}


#: Имя секции в начале строки, с двоеточием: «internal: …», «Fixed : …». Секцию
#: подставляет сборка из ИМЕНИ файла, и второе её написание внутри текста уехало
#: бы в журнал как «- internal: …» под заголовком «Внутреннее». Спрашивается
#: именно ПРЕФИКС — слово секции внутри фразы («починка internal-гейта»)
#: законно и находкой не является.
#:
#: ФОРМЫ ВЗЯТЫ ИЗ СОГЛАШЕНИЙ, А НЕ ИЗ ДЕРЕВА (206): по всем 59 фрагментам
#: истории префикса нет ни в одной форме, и замер по дереву дал бы одну форму
#: из шести. Секцию пишут именем файла («internal:»), подписью журнала
#: («Внутреннее:»), жирным («**fixed:**», «**Fixed**:»), в скобках
#: («[added]») и типом conventional commits («fix:», «feat(gate):»); прежде
#: читалась только первая. Слово без двоеточия и скобки не читается: «**fixed**
#: навсегда» — выделение, а не подпись.
CONVENTIONAL = ("feat", "fix", "chore", "docs", "refactor", "perf", "test", "ci", "build")
_LABEL = "|".join((*SECTIONS, *SECTIONS.values(), *CONVENTIONAL))
SECTION_PREFIX = re.compile(
    rf"^(?:\*\*|__)?[\[(]?\s*(?P<name>{_LABEL})\b(?:\([^)]*\))?\s*"
    rf"(?::\s*(?:\*\*|__)?|(?:\*\*|__)\s*:|[\])]\s*:?)\s*", re.I)


def is_fragment(path: str) -> bool:
    """Путь от корня — фрагмент журнала: `.md` прямо в changelog.d/, кроме соглашения.

    ОДИН ОТВЕТ НА ВОПРОС ДЛЯ СБОРЩИКА И ДЛЯ ГЕЙТА ЖУРНАЛА (214). Гейт засчитывал
    любой путь под changelog.d/, а сборщик читал только `.md` верхнего уровня:
    правка, приложившая `changelog.d/x.txt` или вложенный файл, проходила гейт
    и в журнал не попадала. Узнаёт фрагмент тот, кто его собирает, — здесь.
    """
    parent, _, name = path.rpartition("/")
    return parent == FRAGMENTS.name and name.endswith(".md") and name != "README.md"


def fragments() -> list[pathlib.Path]:
    """Файлы фрагментов. Порядок — по имени, он же в выводе."""
    return sorted(p for p in FRAGMENTS.glob("*")
                  if is_fragment(p.relative_to(ROOT).as_posix()))


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
    body = text
    if body.startswith("- "):
        found.append(f"{path.name}: ведущий дефис подставит сборка, убирается из текста")
        body = body[2:]
    # ПРЕФИКС ИЩЕТСЯ ПОСЛЕ СНЯТОГО ДЕФИСА — тем же разбором, а не вторым. Иначе
    # «- internal: …» показал бы одну находку, и вторая всплыла бы только
    # следующим прогоном, после починки первой: две ходки на один фрагмент.
    prefix = SECTION_PREFIX.match(body)
    if prefix:
        rest = body[prefix.end():]
        found.append(f"{path.name}: подпись секции «{prefix['name']}» в начале строки "
                     f"подставит сборка из имени файла — оставьте «{checks.clip(rest, 60)}»")
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


def month_title(month: str) -> str:
    """Заголовок раздела по ``ГГГГ-ММ``: ``## Сентябрь 2026``.

    Названия месяцев — те же, по которым журнал решений узнаёт свои разделы
    (scripts/checks.py::MONTHS): два журнала одной витрины не расходятся в
    том, как зовут месяц.
    """
    found = MONTH.match(month)
    if not found:
        raise ValueError(f"месяц {month!r} — не в форме ГГГГ-ММ")
    return f"## {checks.MONTHS[int(found['month']) - 1].capitalize()} {found['year']}"


def by_number(entry: str) -> tuple[int, str]:
    """Ключ порядка: номер изменения; запись без номера — в конец секции."""
    found = ENTRY_NUMBER.search(entry)
    return (int(found.group(1)) if found else sys.maxsize, entry)


def section_entries(body: str) -> dict[str, list[str]]:
    """Записи раздела по секциям — обратный разбор того, что пишет ``render``.

    Строка вне формы — отказ, а не пропуск: молча выброшенная при пересборке
    раздела запись пропала бы из журнала навсегда.
    """
    titles = {title: key for key, title in SECTIONS.items()}
    entries: dict[str, list[str]] = {}
    current = None
    for line in body.splitlines():
        if line.startswith("### "):
            current = titles.get(line[4:].strip())
            if current is None:
                raise ValueError(f"секция «{line[4:].strip()}» не из списка")
            entries.setdefault(current, [])
        elif line.startswith("- ") and current:
            entries[current].append(line[2:])
        elif line.strip():
            raise ValueError(f"строка вне формы раздела: {checks.clip(line, 60)}")
    return entries


def merge(text: str, title: str, by_section: dict[str, list[str]]) -> str:
    """Записи ложатся в раздел месяца. Есть раздел — дописываются в него, нет —
    он заводится выше прежних. Журнал растёт, прежнее не теряется."""
    lines = text.rstrip("\n").split("\n")
    heads = [i for i, line in enumerate(lines) if line.startswith("## ")]
    start = next((i for i in heads if lines[i].strip() == title), None)
    if start is None:
        at = heads[0] if heads else len(lines)
        block = [title, "", render({k: sorted(v, key=by_number) for k, v in by_section.items()}), ""]
        lines[at:at] = block if heads else ["", *block[:-1]]
        return "\n".join(lines) + "\n"
    end = next((i for i in heads if i > start), len(lines))
    old = section_entries("\n".join(lines[start + 1:end]))
    combined = {key: sorted(old.get(key, []) + by_section.get(key, []), key=by_number)
                for key in SECTIONS if key in old or key in by_section}
    lines[start:end] = [title, "", render(combined), *([""] if end < len(lines) else [])]
    return "\n".join(lines) + "\n"


def selftest() -> int:
    """Прогоняет через сборщик то, что он обязан отвергнуть и обязан пропустить."""
    broken: list[str] = []

    name_cases = [
        ("правильное имя", "logo-loop.fixed.md", "починили", 0),
        ("секции нет вовсе", "logo-loop.md", "починили", 1),
        ("секция не из списка", "logo-loop.fix.md", "починили", 1),
        ("пустой фрагмент", "logo-loop.added.md", "   \n", 1),
        ("ведущий дефис", "logo-loop.added.md", "- добавили", 1),
        # Имя секции внутри текста (находка 24 сентября: «internal: …» прошёл
        # --check зелёным). Обе стороны: префикс — отказ в любом регистре и для
        # любой секции, не только своей; слово секции в прозе — пропуск.
        ("имя своей секции префиксом", "opus.internal.md", "internal: трейлер соавтора", 1),
        ("регистр не спасает", "opus.internal.md", "Internal: трейлер соавтора", 1),
        ("пробел перед двоеточием не спасает", "opus.fixed.md", "fixed : починили", 1),
        ("чужая секция префиксом", "opus.internal.md", "fixed: починили", 1),
        ("слово секции не первым", "gate.fixed.md", "починка internal-гейта (#1)", 0),
        ("слово секции первым, но без двоеточия", "gate.fixed.md",
         "internal-гейт починен (#1)", 0),
        ("длиннее имени секции — не префикс", "gate.changed.md",
         "addedness: слово длиннее имени секции", 0),
        # Формы подписи, которых прежний образец не видел (206).
        ("подпись журнала по-русски", "opus.internal.md", "Внутреннее: трейлер соавтора", 1),
        ("подпись жирным, двоеточие внутри", "opus.fixed.md", "**fixed:** починили", 1),
        ("подпись жирным, двоеточие снаружи", "opus.fixed.md", "**Fixed**: починили", 1),
        ("подпись в скобках", "opus.added.md", "[added] новый гейт", 1),
        ("тип conventional commits", "opus.fixed.md", "fix(gate): починили", 1),
        ("выделение без двоеточия — не подпись", "opus.fixed.md",
         "**починено** навсегда: гейт читает все формы (#1)", 0),
        ("слово-тип внутри слова — не подпись", "opus.fixed.md",
         "fixture гейта: подделка стала честной (#1)", 0),
        # Тот же разбор, что у дефиса: обе находки за один прогон, а не по одной.
        ("дефис и префикс вместе", "opus.internal.md", "- internal: трейлер соавтора", 2),
    ]
    import tempfile                                            # noqa: PLC0415
    with tempfile.TemporaryDirectory(dir=checks.runner_temp()) as tmp:
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

    # Раздел месяца: заводится, дописывается, прежнее не теряется (обе стороны).
    head = "# Ж\n\n<!-- соглашение -->\n"
    sept = month_title("2026-09")
    first = merge(head, sept, {"fixed": ["второе (#12)", "первое (#3)"]})
    if not (sept in first and first.index("первое (#3)") < first.index("второе (#12)")):
        broken.append(f"раздел месяца не заведён или записи не по номеру:\n{first}")
    print("  заведён   — раздел месяца, записи по номеру изменения")
    again = merge(first, sept, {"fixed": ["между (#7)"], "added": ["новое (#20)"]})
    if (again.count(sept) != 1 or "первое (#3)" not in again
            or not again.index("первое (#3)") < again.index("между (#7)") < again.index("второе (#12)")
            or again.index("Добавлено") > again.index("Починено")):
        broken.append(f"повторный сбор за месяц не дописал в раздел:\n{again}")
    print("  дописан   — тот же месяц: один раздел, прежние записи на месте")
    octo = merge(again, month_title("2026-10"), {"changed": ["позже (#30)"]})
    if not (octo.index("## Октябрь 2026") < octo.index(sept) and "первое (#3)" in octo):
        broken.append(f"новый месяц лёг не выше прежнего:\n{octo}")
    print("  выше      — новый месяц ложится над прежним")
    if month_title("2026-09") != "## Сентябрь 2026":
        broken.append(f"заголовок месяца: {month_title('2026-09')!r}")
    for wrong in ("2026-13", "09-2026", "сентябрь"):
        try:
            month_title(wrong)
        except ValueError:
            continue
        broken.append(f"месяц {wrong!r} принят")
    print("  отвергнут — месяц не в форме ГГГГ-ММ")
    try:
        merge(first.replace("- первое", "* первое"), sept, {"fixed": ["x (#1)"]})
    except ValueError:
        print("  отвергнут — строка вне формы раздела не выбрасывается молча")
    else:
        broken.append("строка вне формы раздела выброшена молча при пересборке")

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
    parser.add_argument("--month", help="месяц раздела, ГГГГ-ММ: обязателен для --collect")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    try:
        title = month_title(args.month) if args.month else ""
    except ValueError as err:
        print(checks.annotate("error", str(err)), file=sys.stderr)
        return 2
    if args.collect and not title:
        print(checks.annotate("error", "--collect без --month: раздел месяца не назван"),
              file=sys.stderr)
        return 2
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
              "ведущего\n  дефиса и без имени секции. Формат и примеры — "
              "changelog.d/README.md.",
              file=sys.stderr)
        return 1

    # Порядок — по номеру изменения сразу после разбора: предпросмотр обязан
    # показывать ровно то, что ляжет в журнал.
    by_section = {key: sorted(lines, key=by_number) for key, lines in by_section.items()}
    block = render(by_section)
    if args.check:
        print(f"фрагменты в порядке: {sum(len(v) for v in by_section.values())}")
        return 0
    if args.preview:
        print(f"{title or '## <месяц>'}\n\n{block}" if block else "фрагментов нет — собирать нечего")
        return 0
    if not args.collect:
        print(f"фрагментов: {sum(len(v) for v in by_section.values())}. "
              f"--preview покажет сборку, --collect перенесёт в журнал")
        return 0

    if not block:
        print("фрагментов нет — журнал не тронут")
        return 0
    try:
        CHANGELOG.write_text(merge(CHANGELOG.read_text(encoding="utf-8"), title, by_section),
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
