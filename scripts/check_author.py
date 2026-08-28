#!/usr/bin/env python3
"""Отвергает коммит, подписанный контейнерным умолчанием агентского окна.

ПОЧЕМУ ОТДЕЛЬНО ОТ ГЕЙТА АТРИБУЦИИ. Гейт каталога сверяет **трейлеры**:
соавтор вне списка — отказ, след сессии без соавторства — отказ. На **автора**
коммита он не смотрит вовсе, и это проверено прогоном, а не прочитано:

    коммит 4d9e300, автор «Claude <noreply@anthropic.com>» — гейт ПРОПУСКАЕТ
    коммит без единого трейлера                            — гейт ПРОПУСКАЕТ

Предмет здесь другой, поэтому это не вторая копия чужого механизма, а
недостающая половина. Место ей уровнем выше — в том же действии каталога,
параметром; предложено там же. Пока не переехало — живёт тут.

ПОЧЕМУ ПРОВЕРКА УЗКАЯ. Спрашивается ровно одно запрещённое написание, а не
«правильные имена». У владельца есть свои коммиты из веб-интерфейса с его
noreply-адресом, и объявлять их дефектом неверно; список согласованных имён —
предмет гейта атрибуции, а не этого (правило 051: ложный отказ дороже пропуска).

ЛОВИТ ПОЗДНО, И ЭТО НАЗВАНО. Коммит к моменту проверки уже сделан, и починка
означает ``git commit --amend`` или новый коммит поверх. Раньше поймать нечем:
хука в облачном окне нет. Искать несуществующий способ починить «до» не надо.

Исходы: 0 — чисто; 1 — есть находки; 2 — проверка не отработала.
"""

from __future__ import annotations

import subprocess
import sys

import checks

#: Умолчание, которое облачный контейнер проставляет в глобальной настройке.
#: Оно попадало в main пять раз, пока соглашение держалось памятью окна.
FORBIDDEN = {"Claude <noreply@anthropic.com>"}

#: Что делать, а не «почини атрибуцию»: отказ обязан называть команду целиком.
REMEDY = (
    'git config user.name "ArtVsMark" && '
    'git config user.email "arvs.markitanov@gmail.com"'
)


def offenders(authors: list[str]) -> list[str]:
    """Подписи из списка запрещённых, встретившиеся среди авторов."""
    return [a for a in authors if a.strip() in FORBIDDEN]


def selftest() -> int:
    """Прогоняет через проверку то, что она обязана отвергнуть и пропустить."""
    cases = [
        ("контейнерное умолчание", ["Claude <noreply@anthropic.com>"], True),
        ("оно же среди верных", ["ArtVsMark <arvs.markitanov@gmail.com>",
                                 "Claude <noreply@anthropic.com>"], True),
        ("согласованный автор", ["ArtVsMark <arvs.markitanov@gmail.com>"], False),
        ("владелец из веб-интерфейса",
         ["Artem Markitanov <86671904+ArtVsMark@users.noreply.github.com>"], False),
        ("соавтор-исполнитель автором не притворяется",
         ["Claude Opus 5 <noreply@anthropic.com>"], False),
        ("бот площадки — не предмет этой проверки",
         ["github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>"], False),
        ("коммитов нет", [], False),
    ]
    broken = []
    for name, authors, must_reject in cases:
        found = offenders(authors)
        if bool(found) is not must_reject:
            broken.append(f"{name}: ожидалось {'отказ' if must_reject else 'пропуск'}, вышло наоборот")
        print(f"  {'отвергнут' if found else 'пропущен '} — {name}")

    # Третий объявленный исход — «проверка не отработала», код 2. Он был
    # объявлен в докстроке и не прогонялся ни разу: набор проверял `offenders`,
    # то есть только пути 0 и 1. Правило 145 ровно про это — необъявленная
    # ветка обычно не «работает неверно», а НЕ СУЩЕСТВУЕТ, и при чтении это
    # неотличимо. Поэтому исход прогоняется целиком, запуском самого скрипта:
    # проверить его вызовом `offenders` нельзя, он живёт в `main`.
    probe = subprocess.run(
        [sys.executable, __file__, "нет-такой-ветки..HEAD"],
        capture_output=True, text=True,
    )
    if probe.returncode != 2:
        broken.append(
            f"исход «проверка не отработала» дал код {probe.returncode}, а не 2"
        )
    if "не отработала" not in probe.stderr:
        broken.append("исход «проверка не отработала» не называет себя в потоке ошибок")
    print(f"  код {probe.returncode}     — неразобранный диапазон: проверка не отработала")

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: проверка отвергает то, что обязана, и все три исхода прогнаны")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()

    rng = next((a for a in argv if not a.startswith("-")), "origin/main..HEAD")
    try:
        out = subprocess.run(["git", "log", "--format=%an <%ae>%x00%h%x00%s", rng],
                             capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"проверка не отработала: диапазон {rng!r} не разобран — {e}", file=sys.stderr)
        return 2

    records = [line.split("\x00") for line in out.splitlines() if line.strip()]
    bad = [r for r in records if r[0].strip() in FORBIDDEN]

    if bad:
        print(checks.annotate("error", f"подписано контейнерным умолчанием коммитов: {len(bad)} из {len(records)}"), file=sys.stderr)
        for author, sha, subject in bad:
            print(f"  • {sha} {subject[:60]}\n        автор: {author}", file=sys.stderr)
        print(
            f"\n  Соглашение: автор коммита — владелец, исполнитель уходит трейлером."
            f"\n  Выполните в окне:\n\n      {REMEDY}\n"
            "\n  и перепишите подпись: git commit --amend --reset-author (или новый"
            "\n  коммит поверх). Раньше этого места поймать нечего — хука в облачном"
            "\n  окне нет, и коммит к моменту проверки уже сделан.",
            file=sys.stderr,
        )
        return 1

    print(f"подписи авторов в порядке: {len(records)} коммитов в {rng}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
