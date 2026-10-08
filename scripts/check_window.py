#!/usr/bin/env python3
"""Окно по следу сессии: сколько оно живёт и не правили ли свод у него под ногами.

ЗАЧЕМ. Два правила каталога витрина держала только абзацем свода, и ответ по
обоим был «машиной нельзя: окно живёт вне репозитория». Разбор 8 октября по
соседям (#286) это опроверг: у каждого коммита окна трейлер
``Claude-Session: <адрес>``, и история общей ветки датирует сессию целиком.

  006 — окно живёт три–пять дней (CLAUDE.md § Окно). Возраст сессии — от
        первого её коммита до головы изменения; дольше предела — находка;
  047 — сменились правила, окна перезапускаются. Правка CLAUDE.md, слитая в
        общую ветку ПОСЛЕ первого коммита этой сессии и НЕ ею, — находка:
        окно работает по своду, прочитанному до неё.

ПРЕДУПРЕЖДЕНИЕ, А НЕ ОТКАЗ. Перезапуск решает владелец, а красное, которое
правкой изменения не чинится, гнало бы окно чинить неисправимое (051). Образец
— проект механизмов: check_window_lifetime и check_rulebook_fresh, обе
неблокирующие.

СЛЕД ЧИТАЕТСЯ ЛЮБОЙ СТРОКОЙ, А НЕ РАЗБОРОМ ТРЕЙЛЕРОВ GIT. Сообщение слияния —
тело изменения, черта и строка площадки ``Co-authored-by``; разбор git читает
только последний абзац, и ``Claude-Session`` выше черты он не видит (замер 8
октября: %(trailers) нашёл сессию у 4 первопредков из 236, построчный поиск —
у 146). Тот же критерий у check_author.py и у гейта атрибуции каталога.

Исходы: 0 — чисто; 1 — есть находки; 2 — проверка не отработала (история не
прочитана). Шаг в pr-check.yml неблокирующий (continue-on-error): код 1 виден
жёлтым, но изменения не держит — по причине выше.
"""

import re
import subprocess
import sys
from datetime import datetime

import checks

#: Предел из CLAUDE.md § Окно: «три–пять дней». Берётся верхняя граница:
#: нижняя — пожелание, а не порог, и краснеть на четвёртом дне значило бы
#: спорить со сводом.
LIFETIME_DAYS = 5

#: След сессии — строка в любом месте сообщения (см. докстроку модуля).
SESSION = re.compile(r"^Claude-Session:\s*(\S+)", re.M)

#: Файл свода, правка которого требует перезапуска окна (047).
RULEBOOK = "CLAUDE.md"

Record = tuple[str, datetime, set[str]]


def parse(log: str) -> list[Record]:
    """Записи ``git log --format=%h%x1f%cI%x1f%B%x1e`` → (sha, время, сессии).

    Хеш короткий от самого git (%h), а не срезом полного: обрубок выглядел бы
    целым (016)."""
    out: list[Record] = []
    for chunk in log.split("\x1e"):
        if not chunk.strip():
            continue
        sha, when, body = (chunk.strip("\n").split("\x1f") + ["", "", ""])[:3]
        out.append((sha, datetime.fromisoformat(when), set(SESSION.findall(body))))
    return out


def born(session: str, *histories: list[Record]) -> datetime | None:
    """Первый коммит сессии в любой из историй; None — следа нет."""
    seen = [when for history in histories for _, when, s in history if session in s]
    return min(seen) if seen else None


def lifetime(session: str, start: datetime, now: datetime) -> str:
    """Находка 006: сессия живёт дольше предела. Пусто — в пределе."""
    days = (now - start).total_seconds() / 86400
    if days <= LIFETIME_DAYS:
        return ""
    return (f"окно {checks.clip(session, 60)} живёт {days:.1f} сут при пределе "
            f"{LIFETIME_DAYS} (CLAUDE.md § Окно): пора эстафета ссылками и новое окно (006)")


def stale_rulebook(session: str, start: datetime, rulebook: list[Record]) -> list[str]:
    """Находки 047: правки свода в общей ветке под живым окном, сделанные не им."""
    return [f"{sha} от {when:%Y-%m-%d %H:%M} правил {RULEBOOK} после старта окна "
            f"и не этим окном — оно работает по своду, прочитанному до правки (047)"
            for sha, when, sessions in rulebook
            if when > start and session not in sessions]


def git_log(*args: str) -> str:
    return subprocess.run(
        ["git", "log", "--format=%h%x1f%cI%x1f%B%x1e", *args],
        capture_output=True, text=True, encoding="utf-8", check=True).stdout


def selftest() -> int:
    """Прогоняет разбор тем, что он обязан найти и пропустить (140)."""
    broken: list[str] = []
    t = datetime.fromisoformat

    # Разбор: след в теле выше черты площадки находится, чужая строка — нет.
    log = ("a1\x1f2026-10-01T10:00:00+00:00\x1fтело\n\nClaude-Session: https://s/1\n"
           "\n---------\n\nCo-authored-by: X <x@y>\x1e"
           "b2\x1f2026-10-02T10:00:00+00:00\x1fтекст про Claude-Session: в середине\x1e")
    got = parse(log)
    cases = [
        ("след выше черты площадки найден", got[0][2] == {"https://s/1"}),
        ("упоминание в середине строки — не след", got[1][2] == set()),
        ("время разобрано с поясом", got[0][1] == t("2026-10-01T10:00:00+00:00")),
        ("первый коммит — по всем историям",
         born("https://s/1", [("c", t("2026-10-03T00:00:00+00:00"), {"https://s/1"})], got)
         == t("2026-10-01T10:00:00+00:00")),
        ("следа нет — None", born("https://s/9", got) is None),
    ]
    start = t("2026-10-01T00:00:00+00:00")
    cases += [
        ("ровно пять суток — в пределе",
         lifetime("s", start, t("2026-10-06T00:00:00+00:00")) == ""),
        ("пять с лишним — находка",
         "5.5 сут" in lifetime("s", start, t("2026-10-06T12:00:00+00:00"))),
    ]
    rulebook = [
        ("r0", t("2026-09-30T00:00:00+00:00"), set()),               # до старта
        ("r1", t("2026-10-02T00:00:00+00:00"), set()),               # владелец руками
        ("r2", t("2026-10-03T00:00:00+00:00"), {"s"}),               # само окно
        ("r3", t("2026-10-04T00:00:00+00:00"), {"другое"}),          # чужое окно
    ]
    found = stale_rulebook("s", start, rulebook)
    cases += [
        ("правка до старта окна — не находка", not any("r0" in f for f in found)),
        ("правка без следа после старта — находка", any(f.startswith("r1") for f in found)),
        ("своя правка окна — не находка", not any(f.startswith("r2") for f in found)),
        ("правка чужого окна — находка", any(f.startswith("r3") for f in found)),
    ]
    for name, ok in cases:
        if not ok:
            broken.append(name)
        print(f"  {'да ' if ok else 'НЕТ'} — {name}")
    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: след сессии читается, срок и свежесть свода судятся")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    base = next((a for a in argv if not a.startswith("-")), "origin/main")
    try:
        own = parse(git_log(f"{base}..HEAD"))
        shared = parse(git_log("--first-parent", base))
        rulebook = parse(git_log("--first-parent", base, "--", RULEBOOK))
        now = datetime.fromisoformat(subprocess.run(
            ["git", "log", "-1", "--format=%cI", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip())
    except (subprocess.CalledProcessError, OSError, ValueError) as e:
        print(checks.annotate("warning", f"история не прочитана — окно не судится: {e}"),
              file=sys.stderr)
        return 2

    sessions = sorted({s for _, _, ss in own for s in ss})
    total = 0
    if not sessions:
        # Машинная ветка или правка руками — следа окна нет, судить некого (051).
        print("у изменения нет следа сессии — окно не судится")
        return 0
    for session in sessions:
        start = born(session, own, shared)
        found = [lifetime(session, start, now)] + stale_rulebook(session, start, rulebook)
        found = [f for f in found if f]
        days = (now - start).total_seconds() / 86400
        print(f"окно {checks.clip(session, 60)}: живёт {days:.1f} сут, "
              f"находок {len(found)}")
        for line in found:
            print(checks.annotate("warning", line))
        total += len(found)
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
