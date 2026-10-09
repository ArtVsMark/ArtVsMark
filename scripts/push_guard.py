#!/usr/bin/env python3
"""Сторож окна перед толчком: ни в чужую ветку, ни в воскресшую (012, 202).

ЗАЧЕМ. Две половины двух правил стояли «не построено» по одной причине —
«хуков у витрины нет ни одного, и первый заводится решением владельца». Первый
завёл владелец (хук старта, #269), и причина устарела. Обе половины спрашивают
одно и то же место — команду толчка до того, как git её выполнит, — и потому
живут в одном стороже, а не в двух.

* 012 — работа не вписывается в чужую ветку. Чужие ветки витрины названы
  поимённо: машинные (``checks.MACHINE_BRANCHES`` — ``chore/metrics``,
  ``dependabot/**``) и общая ``main``. Толчок туда из окна — отказ.
* 202 — слитую ветку не продолжают. Признак тот же, что у конвейерной
  половины (``resurrected.py``): голова уже слитого изменения той же ветки
  лежит в истории толкаемого и не лежит в истории ``main``. Конвейер
  отвергает изменение при открытии; сторож — раньше, до того как толчок
  воскресит ветку на площадке.

КАК ЗОВЁТСЯ. Хук окна ``PreToolUse`` на Bash (``.claude/settings.json``):
площадка отдаёт вызов JSON-ом в stdin, код 2 отменяет вызов и показывает
окну причину. Команда без ``git push`` пропускается сразу. Толчок в чужом
репозитории (``cd`` или ``-C`` за пределами витрины) не судится: признаки
здесь — о витрине.

ТРЕТИЙ ИСХОД НЕ МОЛЧИТ (039). Площадка не ответила о слитых изменениях —
толчок проходит, а причина названа: сторож, который отказывает от
неведения, научил бы обходить себя. Конвейерная половина 202 стоит дальше.

ГРАНИЦА. Разбор команды — по словам, а не оболочкой: толчок, собранный
подстановкой (``git push origin "$b"``), сторож видит как имя ``$b`` и
пропускает. Окно так не толкает; названо, а не скрыто.

Запуск::

    python scripts/push_guard.py < вызов.json   # как хук
    python scripts/push_guard.py --selftest

Исходы: 0 — толчок пропущен (или это не толчок); 2 — толчок отменён, причина
названа. Кода 1 нет: находку здесь некому чинить после — её чинят до толчка.
"""

import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import urllib.error

import checks
import resurrected

ROOT = pathlib.Path(__file__).resolve().parent.parent
#: Общая ветка — тоже чужая для окна: в неё сливает конвейер, а не толчок.
SHARED = "main"
PUSH = re.compile(r"\bgit\b[^;&|]*\bpush\b")


def segments(command: str) -> list[list[str]]:
    """Команды строки, разрезанные по ``&&``, ``;``, ``||`` и ``|``, — словами."""
    words = shlex.split(command, posix=True) if command.strip() else []
    parts: list[list[str]] = [[]]
    for word in words:
        if word in ("&&", ";", "||", "|"):
            parts.append([])
        else:
            parts[-1].append(word)
    return [part for part in parts if part]


def push_targets(command: str, current: str, root: pathlib.Path = ROOT) -> list[tuple[str, str]]:
    """Ветки, в которые толкает команда: (куда на площадке, что локально).

    Пусто — это не толчок витрины: толчка нет вовсе либо он идёт из чужого
    каталога. Без явной ветки — текущая.
    """
    where = pathlib.Path(os.getcwd())
    targets: list[tuple[str, str]] = []
    for words in segments(command):
        if words[0] == "cd" and len(words) > 1:
            where = (where / words[1]).resolve()
            continue
        if words[0] != "git":
            continue
        rest, place = words[1:], where
        while rest and rest[0].startswith("-"):
            if rest[0] == "-C" and len(rest) > 1:
                place = (place / rest[1]).resolve()
                rest = rest[2:]
            else:
                rest = rest[1:]
        if not rest or rest[0] != "push":
            continue
        if place != root and root not in place.parents:
            continue
        plain = [w for w in rest[1:] if not w.startswith("-")]
        refspecs = plain[1:] if plain else []
        for spec in refspecs or [current]:
            spec = spec.lstrip("+")
            src, _, dst = spec.partition(":")
            src = current if src in ("", "HEAD") else src
            dst = dst or src
            targets.append((dst.removeprefix("refs/heads/"), src))
    return targets


def foreign(branch: str) -> str:
    """Почему ветка чужая для окна; пусто — своя (012)."""
    if branch == SHARED:
        return "общая ветка: в неё сливает конвейер, а не толчок окна"
    if checks.machine_branch(branch):
        return "машинная ветка: её ведёт обновлятель или суточный прогон, а не окно"
    return ""


def verdict(command: str, current: str, merged_of, in_head, in_base) -> tuple[int, str]:
    """Решение по команде: (исход, причина). Зависимости — параметрами, ради набора."""
    lines: list[str] = []
    for branch, source in push_targets(command, current):
        if why := foreign(branch):
            return 2, f"толчок в {branch} отменён — {why} (012)"
        try:
            hits = resurrected.resurrected(merged_of(branch),
                                           lambda sha, s=source: in_head(sha, s), in_base)
        except (urllib.error.URLError, OSError, ValueError, KeyError,
                subprocess.SubprocessError) as e:
            lines.append(f"{branch}: площадка не ответила о слитых изменениях — "
                         f"воскрешение не проверено ({checks.clip(str(e), 100)}); "
                         f"конвейер проверит при открытии (039)")
            continue
        if hits:
            return 2, f"толчок отменён — {resurrected.refusal(branch, hits)}"
    return 0, "\n".join(lines)


def current_branch() -> str:
    """Текущая ветка витрины; пусто — голова отделена."""
    return subprocess.run(["git", "-C", str(ROOT), "branch", "--show-current"],
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()


def selftest() -> int:
    """Обе стороны (140): чужая и воскресшая ветки отменяются, своя — нет."""
    broken: list[str] = []
    root = str(ROOT)
    targets = [
        ("толчок текущей", f"cd {root} && git push -u origin agent/x", [("agent/x", "agent/x")]),
        ("без ветки — текущая", f"cd {root} && git push", [("agent/x", "agent/x")]),
        ("HEAD:ветка", f"git -C {root} push origin HEAD:refs/heads/main", [("main", "agent/x")]),
        ("не толчок", f"cd {root} && git status", []),
        ("чужой репозиторий", "cd /tmp && git push origin main", []),
        ("пуш в echo — не толчок", f"cd {root} && echo git push", []),
    ]
    for name, command, expected in targets:
        got = push_targets(command, "agent/x")
        if got != expected:
            broken.append(f"разбор, {name}: ждали {expected}, вышло {got}")
        print(f"  {'верно' if got == expected else 'СБОЙ '} — разбор: {name}")

    def never(sha: str, *_: str) -> bool:
        return False

    def offline(_branch: str) -> list:
        raise urllib.error.URLError("подделка: сеть закрыта")

    cases = [
        ("своя ветка, слитых нет", f"cd {root} && git push origin agent/x",
         lambda b: [], never, never, 0, ""),
        ("в main", f"cd {root} && git push origin main", lambda b: [], never, never, 2, "(012)"),
        ("в машинную ветку", f"cd {root} && git push origin chore/metrics",
         lambda b: [], never, never, 2, "(012)"),
        ("воскрешение", f"cd {root} && git push origin agent/x",
         lambda b: [(180, "old")], lambda sha, s: sha == "old", never, 2, "#180"),
        ("начата заново — голова слитого не в истории", f"cd {root} && git push origin agent/x",
         lambda b: [(180, "old")], never, never, 0, ""),
        ("площадка молчит — пропуск с причиной", f"cd {root} && git push origin agent/x",
         offline, never, never, 0, "не ответила"),
    ]
    for name, command, merged_of, in_head, in_base, code, said in cases:
        got_code, got_said = verdict(command, "agent/x", merged_of, in_head, in_base)
        right = got_code == code and said in got_said and (said or not got_said)
        if not right:
            broken.append(f"решение, {name}: ждали {code} «{said}», вышло {got_code} «{got_said}»")
        print(f"  {'верно' if right else 'СБОЙ '} — решение: {name}")

    # Живой путь main: вызов хуком — JSON в stdin. Сравнение прямо с main():
    # так его считает храповик непрогнанных исходов (186).
    import io                                                  # noqa: PLC0415
    saved = sys.stdin
    try:
        sys.stdin = io.StringIO(json.dumps({"tool_input": {"command": "git status"}}))
        if main([]) != 0:
            broken.append("не толчок — main вернул не 0")
        sys.stdin = io.StringIO(json.dumps(
            {"tool_input": {"command": f"cd {root} && git push origin main"}}))
        if main([]) != 2:
            broken.append("толчок в main — main вернул не 2")
    finally:
        sys.stdin = saved

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: чужая и воскресшая ветки отменяются, своя — нет")
    return 0


def main(argv: list[str] | None = None) -> int:
    if "--selftest" in (sys.argv[1:] if argv is None else argv):
        return selftest()
    try:
        command = str(json.load(sys.stdin).get("tool_input", {}).get("command") or "")
    except ValueError:
        return 0                     # не вызов площадки — судить нечего
    if not PUSH.search(command):
        return 0
    try:
        code, said = verdict(command, current_branch(), resurrected.merged_heads,
                             resurrected.is_ancestor,
                             lambda sha: resurrected.is_ancestor(sha, resurrected.BASE))
    except ValueError as e:          # кавычки не закрыты — команду разобрать нечем
        print(f"сторож толчка не разобрал команду ({e}) — толчок не судится", file=sys.stderr)
        return 0
    if said:
        print(said, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
