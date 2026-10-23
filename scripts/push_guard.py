#!/usr/bin/env python3
"""Сторож окна перед толчком: ни в чужую ветку, ни в воскресшую, ни сверх предела (012, 202, 227).

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

* 227 — окно доводит своё открытое, прежде чем открыть новое. Толчок НОВОЙ
  ветки ``agent/*`` — то есть ветки, по которой изменения ещё нет, — при
  ``LIMIT`` открытых изменениях этого окна отменяется. Предел — решение
  владельца 23 октября: два, а не один, потому что починка своего красного
  иногда едет новым изменением (#368 стоял на красном main, чинил его #369).
  Толчок в ветку уже открытого изменения предела не прибавляет — это починка
  своего, ровно то, чего правило требует.

  ЧЬЁ — ПО ТРЕЙЛЕРУ, А НЕ ПО АВТОРУ. Все изменения открывает одна учётная
  запись (131), автор окна не различает. Окно — значение трейлера
  ``Claude-Session`` самого нового своего коммита толкаемой ветки
  (``origin/main..ветка``, без слияний): тот же трейлер понесёт и изменение.
  Изменение — окна, если трейлер несёт хотя бы один его коммит. Считаются
  только ветки ``agent/*``: машинные окно не открывает, даже если чинило их.

ТРЕТИЙ ИСХОД НЕ МОЛЧИТ (039). Площадка не ответила о слитых изменениях —
толчок проходит, а причина названа: сторож, который отказывает от
неведения, научил бы обходить себя. Конвейерная половина 202 стоит дальше.

ГРАНИЦА ПРЕДЕЛА. Окно без трейлера в толкаемых коммитах не опознано — предел
не проверен, толчок проходит с причиной. Клон окна мелкий: за срезом общая
ветка, влитая в рабочую, могла бы принести чужие коммиты в ``origin/main..``;
окно ветки режет от свежего ``origin/main`` и влитием не продолжает, поэтому
трейлер берётся у самого НОВОГО коммита — своего. Неразобранные находки и
конфликт на своих изменениях сторож не видит: их число площадка одним ответом
не отдаёт, и это держит чтение плана.

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
#: Сколько открытых изменений окна держит предел: следующее не открывается.
#: Число — решение владельца 23.10.2026; копия в CLAUDE.md § Ветки, совпадение
#: держит самопроверка (OPEN_LIMIT_SAID, 214).
LIMIT = 2
#: Как предел назван в своде. Самопроверка ищет эту строку в CLAUDE.md.
OPEN_LIMIT_SAID = f"Не больше {LIMIT} открытых изменений окна"
#: Приставка веток, которые открывает окно (003): только они считаются.
WINDOW_PREFIX = "agent/"
PUSH = re.compile(r"\bgit\b[^;&|]*\bpush\b")


#: Разделители команд оболочки — токены, целиком из этих знаков (210).
SEPARATORS = frozenset(";&|()")


def segments(command: str) -> list[list[str]]:
    """Команды строки — словами, по всем формам разделителя, а не по одной.

    ПЕРЕЧЕНЬ ФОРМ (210): находки #329 по этому месту шли по одной форме за раз
    (``;`` без пробела, перевод строки), и каждая обходила и 012, и 202. Формы,
    которыми окно пишет команды сегодня, и что с каждой делается:

    1. ``a && b``, ``a ; b`` с пробелами — разделитель;
    2. склеенные ``a&&b``, ``a;b``, ``a||b``, ``a|b`` — разделитель
       (``shlex`` со знаками пунктуации отдаёт их отдельным токеном);
    3. перевод строки — разделитель: строки разбираются порознь;
    4. ``\\`` в конце строки — продолжение той же команды, не разделитель;
    5. ``&`` — фоновый разделитель;
    6. ``(`` и ``)`` подоболочки — разделители;
    7. перенаправление (``2>&1``, ``> файл``, ``< файл``) — выбрасывается вместе
       с целью, иначе ``2`` и ``1`` стали бы аргументами толчка;
    8. строка, которую не разобрать (тело heredoc с непарной кавычкой), —
       пропускается, если толчка в ней нет; есть — отказ разбора (``ValueError``),
       и сторож говорит, что команду не судил.

    ГРАНИЦА: подстановка ``$(…)`` и переменные не раскрываются — толчок,
    собранный из них, виден как слово, и это названо в докстроке модуля.
    """
    parts: list[list[str]] = []
    for line in command.replace("\\\n", " ").split("\n"):
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        try:
            words = list(lexer)
        except ValueError:
            if PUSH.search(line):
                raise
            continue
        current: list[str] = []
        skip = False
        for word in words:
            if skip:
                skip = False
                continue
            if word and set(word) <= SEPARATORS:
                if current:
                    parts.append(current)
                current = []
            elif "<" in word or ">" in word:
                if current and current[-1].isdigit():
                    current.pop()
                skip = True
            else:
                current.append(word)
        if current:
            parts.append(current)
    return parts


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


def session_of(source: str) -> str:
    """Окно толкаемой ветки — трейлер ``Claude-Session`` её самого нового коммита."""
    log = subprocess.run(["git", "-C", str(ROOT), "log", "--no-merges", "--format=%B%x00",
                          f"{resurrected.BASE}..{source}"],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    for body in log.split("\0"):
        said = checks.trailers(body.strip()).get("claude-session")
        if said:
            return said[-1]
    return ""


def open_changes(repo: str = resurrected.REPO) -> list[tuple[int, str]]:
    """Открытые изменения витрины: (номер, головная ветка)."""
    pulls = checks.rest_list(f"/repos/{repo}/pulls?state=open&per_page=100")
    return [(pull["number"], pull["head"]["ref"]) for pull in pulls]


def change_messages(number: int, repo: str = resurrected.REPO) -> list[str]:
    """Сообщения коммитов изменения."""
    commits = checks.rest_list(f"/repos/{repo}/pulls/{number}/commits?per_page=100")
    return [str(one.get("commit", {}).get("message", "")) for one in commits]


def over_limit(branch: str, session: str, changes: list[tuple[int, str]],
               messages) -> list[int]:
    """Открытые изменения окна, если толчок открыл бы сверх предела; иначе пусто (227).

    Ветка уже открытого изменения — починка своего: пусто, сколько бы ни было.
    """
    if any(head == branch for _, head in changes):
        return []
    mine = [number for number, head in changes
            if head.startswith(WINDOW_PREFIX)
            and any(session in checks.trailers(text).get("claude-session", [])
                    for text in messages(number))]
    return sorted(mine) if len(mine) >= LIMIT else []


def verdict(command: str, current: str, merged_of, in_head, in_base,
            session=lambda source: "", changes=lambda: [],
            messages=lambda number: []) -> tuple[int, str]:
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
        if not branch.startswith(WINDOW_PREFIX):
            continue
        try:
            window = session(source)
            if not window:
                lines.append(f"{branch}: в толкаемых коммитах нет трейлера Claude-Session — "
                             f"окно не опознано, предел открытых изменений не проверен (227, 039)")
                continue
            mine = over_limit(branch, window, changes(), messages)
        except (urllib.error.URLError, OSError, ValueError, KeyError,
                subprocess.SubprocessError) as e:
            lines.append(f"{branch}: площадка не ответила об открытых изменениях — "
                         f"предел не проверен ({checks.clip(str(e), 100)}) (227, 039)")
            continue
        if mine:
            listed = ", ".join(f"#{number}" for number in mine)
            return 2, (f"толчок новой ветки {branch} отменён — у окна уже {len(mine)} открытых "
                       f"изменения ({listed}). «{OPEN_LIMIT_SAID}» — CLAUDE.md § Ветки (227). "
                       f"Сначала довести своё: "
                       f"находки, конфликт, красное. Толчок в ветку открытого изменения "
                       f"предела не трогает")
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
        # Перечень форм разделителя (210) — по случаю на форму.
        ("2: склеенное ;", f"cd {root} && git commit -m x;git push origin main",
         [("main", "main")]),
        ("2: склеенное &&", f"cd {root}&&git push origin main", [("main", "main")]),
        ("2: склеенное ||", f"cd {root} && false||git push origin main", [("main", "main")]),
        ("3: перевод строки", f"cd {root}\ngit add -A\ngit push origin main",
         [("main", "main")]),
        ("4: продолжение строки — одна команда", f"cd {root} && git push \\\n origin main",
         [("main", "main")]),
        ("5: фоновый &", f"cd {root} & git push origin main", [("main", "main")]),
        ("6: подоболочка", f"(cd {root} && git push origin main)", [("main", "main")]),
        ("7: перенаправление — не аргумент", f"cd {root} && git push -u origin agent/x 2>&1 | tail -1",
         [("agent/x", "agent/x")]),
        ("7: перенаправление в файл", f"cd {root} && git push > /tmp/log", [("agent/x", "agent/x")]),
        ("8: непарная кавычка в теле — строка пропущена",
         f"cd {root} && cat <<'E' > /tmp/m\nдон't\nE\ngit push origin main",
         [("main", "main")]),
    ]
    for name, command, expected in targets:
        got = push_targets(command, "agent/x")
        if got != expected:
            broken.append(f"разбор, {name}: ждали {expected}, вышло {got}")
        print(f"  {'верно' if got == expected else 'СБОЙ '} — разбор: {name}")

    try:
        push_targets(f"cd {root} && git push origin 'main", "agent/x")
        broken.append("разбор, 8: непарная кавычка в строке толчка — ждали отказ разбора")
        print("  СБОЙ  — разбор: 8: толчок в неразбираемой строке — отказ")
    except ValueError:
        print("  верно — разбор: 8: толчок в неразбираемой строке — отказ")

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
        got_code, got_said = verdict(command, "agent/x", merged_of, in_head, in_base,
                                     lambda source: "S")
        right = got_code == code and said in got_said and (said or not got_said)
        if not right:
            broken.append(f"решение, {name}: ждали {code} «{said}», вышло {got_code} «{got_said}»")
        print(f"  {'верно' if right else 'СБОЙ '} — решение: {name}")

    # Предел открытых изменений окна (227): обе стороны и все три исхода.
    def ours(number: int) -> list[str]:
        return {1: ["правка\n\nClaude-Session: S"], 2: ["правка\n\nClaude-Session: S"],
                3: ["правка\n\nClaude-Session: T"],
                4: ["пины\n\nClaude-Session: S"]}.get(number, [])

    def silent() -> list:
        raise urllib.error.URLError("подделка: сеть закрыта")

    push = f"cd {root} && git push -u origin agent/new"
    two = [(1, "agent/a"), (2, "agent/b")]
    limits = [
        ("два своих открыто — новая ветка отменена", push, "S", lambda: two, 2, "Не больше 2"),
        ("два своих, толчок в открытую ветку — починка", f"cd {root} && git push origin agent/a",
         "S", lambda: two, 0, ""),
        ("одно своё открыто — проходит", push, "S", lambda: [(1, "agent/a")], 0, ""),
        ("два чужого окна — проходит", push, "T", lambda: two + [(3, "agent/c")], 0, ""),
        ("машинная ветка со своим трейлером не считается", push, "S",
         lambda: [(1, "agent/a"), (4, "chore/deps-9")], 0, ""),
        ("окно не опознано — пропуск с причиной", push, "", lambda: two, 0, "не опознано"),
        ("площадка молчит — пропуск с причиной", push, "S", silent, 0, "не ответила об открытых"),
    ]
    for name, command, window, changes, code, said in limits:
        got_code, got_said = verdict(command, "agent/new", lambda b: [], never, never,
                                     lambda source, w=window: w, changes, ours)
        right = got_code == code and said in got_said and (said or not got_said)
        if not right:
            broken.append(f"предел, {name}: ждали {code} «{said}», вышло {got_code} «{got_said}»")
        print(f"  {'верно' if right else 'СБОЙ '} — предел: {name}")

    # Число предела — копия в своде (214): разойтись им нельзя.
    rulebook = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    if OPEN_LIMIT_SAID not in rulebook:
        broken.append(f"CLAUDE.md не называет предел строкой «{OPEN_LIMIT_SAID}» — "
                      f"число в своде и LIMIT разошлись (227, 214)")
    print(f"  {'верно' if OPEN_LIMIT_SAID in rulebook else 'СБОЙ '} — свод называет предел {LIMIT}")

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
    print("самопроверка пройдена: чужая, воскресшая и сверх предела ветки отменяются, своя — нет")
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
                             lambda sha: resurrected.is_ancestor(sha, resurrected.BASE),
                             session_of, open_changes, change_messages)
    except ValueError as e:          # кавычки не закрыты — команду разобрать нечем
        print(f"сторож толчка не разобрал команду ({e}) — толчок не судится", file=sys.stderr)
        return 0
    if said:
        print(said, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
