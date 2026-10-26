#!/usr/bin/env python3
"""Сверка подписок владельца: на кого он подписан, а тот на него — нет.

ЗАЧЕМ. Решение владельца 26 октября: постоянно отслеживаемая задача, где
каждый аккаунт из «following», которого нет в «followers», предложен к одному
из двух решений — отписаться или внести в исключения. Без сверки список
расходится молча: подписки копятся, а взаимность никто не пересчитывает.

ЧТО ДЕЛАЕТ. Читает оба списка владельца у площадки целиком (страницами),
берёт разность «подписан − подписчики», снимает с неё исключения из
``.github/follow-exceptions.json`` и ведёт ОДНУ задачу по маркеру: кандидаты
с именем профиля и ссылкой, исключения с логином, на который легло имя, и
исключения, не нашедшие никого среди подписок, — их пора убрать.

ЧЕГО НЕ ДЕЛАЕТ. Не отписывается сам: это жест владельца, и штатному токену
площадки права на него не дают. Не закрывает задачу: закрытие — «я
посмотрел», а механизм такого сказать не может (как у ``stuck_prs.py``).
Пустой разности задачу не заводит; заведённую — переписывает «расхождений нет».

ИСКЛЮЧЕНИЕ — ПО ЛОГИНУ ИЛИ ПО ИМЕНИ. Владелец называет аккаунты так, как видит
их на странице («Поколение Python»), и логин по имени из окна не узнать —
список подписок окну площадка не отдаёт. Поэтому имя принимается как есть,
без учёта регистра, а задача показывает, на какой логин оно легло: два
аккаунта с одним именем видны сразу, а не прячутся.

Запуск::

    python scripts/follow_check.py [--dry-run]
    python scripts/follow_check.py --selftest

Исходы: 0 — расхождений нет (задача, если была, переписана «расхождений
нет»); 1 — есть подписки без взаимности, и задача по ним заведена или
обновлена; 2 — сверка не отработала: площадка не ответила или файл
исключений не разобран.
"""

import argparse
import json
import os
import pathlib
import sys
import tempfile
import urllib.error

import checks

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = os.environ.get("SHOWCASE_REPO", "ArtVsMark/ArtVsMark")
#: Чьи подписки сверяются: владелец репозитория витрины.
OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", REPO.split("/", 1)[0])
EXCEPTIONS = ROOT / ".github/follow-exceptions.json"

#: По этой строке задача находится снова. Одна задача на предмет.
MARKER = "<!-- follow-check: не удаляйте, по этой строке задача находится снова -->"
TITLE = "Подписки без взаимности: отписаться или внести в исключения"


def load_exceptions(path: pathlib.Path = EXCEPTIONS) -> list[dict]:
    """Исключения из файла. Запись без логина и имени или без причины — отказ."""
    data = json.loads(path.read_text(encoding="utf-8"))
    found = data.get("exceptions")
    if not isinstance(found, list):
        raise ValueError(f"{path.name}: нет списка exceptions")
    for one in found:
        if not (one.get("login") or one.get("name")) or not str(one.get("why", "")).strip():
            raise ValueError(f"{path.name}: запись {one} без login/name или без why")
    return found


def compare(following: list[str], followers: list[str], names: dict[str, str],
            exceptions: list[dict]) -> tuple[list[str], list[tuple[dict, list[str]]],
                                             list[dict]]:
    """Разность подписок за вычетом исключений.

    Возвращает: кандидатов (логины), сработавшие исключения с логинами, на
    которые они легли, и исключения, не нашедшие никого среди подписок.
    ``names`` — имя профиля по логину, только для разности.
    """
    mutual = {login.lower() for login in followers}
    lonely = [login for login in following if login.lower() not in mutual]
    followed = {login.lower() for login in following}
    matched: list[tuple[dict, list[str]]] = []
    stale: list[dict] = []
    excused: set[str] = set()
    for one in exceptions:
        login = str(one.get("login", "")).lower()
        name = str(one.get("name", "")).strip().lower()
        hits = [who for who in lonely
                if (login and who.lower() == login)
                or (name and str(names.get(who) or "").strip().lower() == name)]
        if hits:
            matched.append((one, hits))
            excused.update(hits)
        elif not (login and login in followed):
            # Взаимный аккаунт законно не попадает в разность — исключение ему
            # просто не нужно; «устаревшим» оно становится, только если
            # подписки на него нет вовсе.
            stale.append(one)
    return [who for who in lonely if who not in excused], matched, stale


def profile(who: str, names: dict[str, str]) -> str:
    """Ссылка на профиль: текстом — имя, как владелец видит его на странице, рядом логин."""
    name = (names.get(who) or "").strip()
    return f"[{name or who}](https://github.com/{who}){f' · `{who}`' if name else ''}"


def body(candidates: list[str], names: dict[str, str],
         matched: list[tuple[dict, list[str]]], stale: list[dict],
         following: int, followers: int) -> str:
    """Тело задачи: кандидаты, сработавшие и лишние исключения."""
    lines = [MARKER, "",
             f"> Сверка подписок `{OWNER}`: подписан на {following}, подписчиков "
             f"{followers}. Собирает `scripts/follow_check.py` по расписанию "
             f"(`.github/workflows/follow-check.yml`); руками тело не правится — "
             f"следующий прогон его перепишет.", ""]
    if candidates:
        lines += ["## Подписан, а взаимности нет", "",
                  "По каждому — одно из двух: **отписаться** (на странице аккаунта) "
                  "или **внести в исключения** — строкой в "
                  "`.github/follow-exceptions.json` с причиной.", ""]
        for who in candidates:
            lines.append(f"- [ ] {profile(who, names)}")
    else:
        lines += ["## Расхождений нет", "",
                  "Все, на кого подписан владелец, подписаны в ответ или внесены в "
                  "исключения. Закрыть задачу — решение владельца."]
    if matched:
        lines += ["", "## Исключения сработали", ""]
        for one, hits in matched:
            said = one.get("login") or one.get("name")
            landed = ", ".join(profile(who, names) for who in hits)
            twice = " — **имя легло на несколько аккаунтов**" if len(hits) > 1 else ""
            lines.append(f"- {said} → {landed}{twice} ({one['why']})")
    if stale:
        lines += ["", "## Исключения не сработали", "",
                  "Среди подписок без взаимности нет никого с таким логином или "
                  "именем: аккаунт подписался в ответ, подписка снята или имя "
                  "сменилось. Если так и задумано — исключение можно убрать из файла.", ""]
        lines += [f"- {one.get('login') or one.get('name')} ({one['why']})" for one in stale]
    return "\n".join(lines) + "\n"


def sync(text: str, needed: bool, dry: bool) -> str:
    """Одна задача по маркеру; без кандидатов новую не заводит. Тело перечитывается (188)."""
    issues = checks.rest_list(f"/repos/{REPO}/issues?state=open&per_page=100")
    existing = next((i for i in issues if MARKER in (i.get("body") or "")), None)
    if not existing and not needed:
        return "задача не нужна: расхождений нет"
    if dry:
        return f"вхолостую: {'обновил бы' if existing else 'завёл бы'} задачу"
    if existing:
        done = checks.rest(f"/repos/{REPO}/issues/{existing['number']}", "PATCH", {"body": text})
        said = f"задача #{existing['number']} обновлена"
    else:
        done = checks.rest(f"/repos/{REPO}/issues", "POST",
                           {"title": TITLE, "body": text, "labels": ["enhancement"]})
        said = f"задача #{done['number']} заведена"
    differs = checks.published_differs(text, done)
    if differs:
        print(checks.annotate("warning", differs))
    return said


def selftest() -> int:
    """Обе стороны сверки и третий исход (140)."""
    broken: list[str] = []
    names = {"py": "Python", "gen": "Поколение Python", "x": "X", "twin1": "Twin",
             "twin2": "Twin"}
    following = ["py", "gen", "x", "mutual", "twin1", "twin2"]
    followers = ["Mutual", "fan"]
    exceptions = [{"name": "python", "why": "т"}, {"login": "GEN", "why": "т"},
                  {"name": "Twin", "why": "т"}, {"name": "Ушедший", "why": "т"},
                  {"login": "mutual", "why": "т"}]
    candidates, matched, stale = compare(following, followers, names, exceptions)
    cases = [
        ("взаимная подписка не кандидат, регистр не важен", "mutual" not in candidates),
        ("без взаимности и без исключения — кандидат", candidates == ["x"]),
        ("исключение по имени, без учёта регистра", any(h == ["py"] for _, h in matched)),
        ("исключение по логину", any(h == ["gen"] for _, h in matched)),
        ("имя на двух аккаунтах — оба сняты и видны", any(h == ["twin1", "twin2"]
                                                          for _, h in matched)),
        ("несработавшее исключение названо", [o.get("name") for o in stale] == ["Ушедший"]),
        ("исключение на взаимного не лишнее", all(o.get("login") != "mutual" for o in stale)),
    ]
    text = body(candidates, names, matched, stale, len(following), len(followers))
    cases += [
        ("в теле маркер, кандидат и двойное имя",
         MARKER in text and "[X](https://github.com/x) · `x`" in text
         and "несколько аккаунтов" in text),
        ("пустая разность — «расхождений нет»",
         "Расхождений нет" in body([], {}, [], [], 1, 1)),
    ]
    for name, good in cases:
        if not good:
            broken.append(name)
        print(f"  {'верно' if good else 'СБОЙ '} — {name}")

    with tempfile.TemporaryDirectory(dir=checks.runner_temp()) as place:
        bad = pathlib.Path(place) / "exceptions.json"
        bad.write_text('{"exceptions": [{"name": "X"}]}', encoding="utf-8")
        try:
            load_exceptions(bad)
            broken.append("исключение без причины не отвергнуто")
        except ValueError:
            print("  верно — исключение без причины отвергнуто")

    # Исходы живым путём main, вхолостую: площадка подменена (186).
    saved, saved_one = checks.rest_list, checks.rest
    lists = {"following": [{"login": "x"}, {"login": "m"}], "followers": [{"login": "m"}],
             "issues": []}
    checks.rest = lambda path, *a, **k: {"name": "X"}
    try:
        checks.rest_list = lambda path, *a, **k: next(v for k_, v in lists.items() if k_ in path)
        if main(["--dry-run"]) != 1:
            broken.append("есть без взаимности — main вернул не 1")
        else:
            print("  верно — есть без взаимности: исход 1")
        lists["followers"] = [{"login": "x"}, {"login": "m"}]
        if main(["--dry-run"]) != 0:
            broken.append("все взаимны — main вернул не 0")
        else:
            print("  верно — все взаимны: исход 0")
    finally:
        checks.rest_list, checks.rest = saved, saved_one

    # Третий исход живым путём main: площадка молчит — код 2, а не «чисто».
    try:
        def silent(*_a, **_k):
            raise urllib.error.URLError("подделка: сеть закрыта")
        checks.rest_list = silent
        if main(["--dry-run"]) != 2:
            broken.append("площадка молчит — main вернул не 2")
        else:
            print("  верно — площадка молчит: исход 2")
    finally:
        checks.rest_list = saved

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: сверка подписок держит объявленное")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="не трогать задачу")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        exceptions = load_exceptions()
        following = [u["login"] for u in checks.rest_list(f"/users/{OWNER}/following?per_page=100")]
        followers = [u["login"] for u in checks.rest_list(f"/users/{OWNER}/followers?per_page=100")]
        mutual = {login.lower() for login in followers}
        names = {who: str(checks.rest(f"/users/{who}").get("name") or "")
                 for who in following if who.lower() not in mutual}
        candidates, matched, stale = compare(following, followers, names, exceptions)
        text = body(candidates, names, matched, stale, len(following), len(followers))
        said = sync(text, bool(candidates), args.dry_run)
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as refusal:
        print(checks.annotate("error", f"сверка подписок не отработала — {refusal}"),
              file=sys.stderr)
        return 2
    print(f"подписан на {len(following)}, подписчиков {len(followers)}; без взаимности "
          f"{len(candidates)}, исключений сработало {len(matched)}, не сработало "
          f"{len(stale)}; {said}")
    return 1 if candidates else 0


if __name__ == "__main__":
    raise SystemExit(main())
