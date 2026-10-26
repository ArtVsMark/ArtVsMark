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

ИСКЛЮЧЕНИЕ СНИМАЕТ ПО ЛОГИНУ, ИМЯ — ТОЛЬКО ПОДСКАЗКА (194). Владелец называет
аккаунты так, как видит их на странице («Поколение Python»), но имя профиля
аккаунт ставит себе сам: назовись любой кандидат «Python» — и исключение по
имени тихо сняло бы его со списка (взгляд на #381). Поэтому запись по имени
кандидата не снимает: совпавший остаётся в списке, и рядом сказано, чьё имя
совпало, — подтверждается это только логином. Чужое имя вставляется в
задачу как текст: упоминание гасится, разметка экранируется.

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
import re
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
    """Исключения из файла. Запись не того вида, без логина и имени или без причины — отказ.

    Отказ — ``ValueError``, то есть исход 2: голая строка вместо объекта
    уронила бы разбор ``AttributeError``, питон вышел бы кодом 1, а прогон
    прочёл бы его как «есть кандидаты» — сбой прошёл бы зелёным (039).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    found = data.get("exceptions") if isinstance(data, dict) else None
    if not isinstance(found, list):
        raise ValueError(f"{path.name}: нет списка exceptions")
    for one in found:
        if not isinstance(one, dict) or not all(isinstance(one.get(key, ""), str)
                                                for key in ("login", "name", "why")):
            raise ValueError(f"{path.name}: запись {one!r} — не объект со строковыми полями")
        if not (one.get("login") or one.get("name")) or not one.get("why", "").strip():
            raise ValueError(f"{path.name}: запись {one} без login/name или без why")
    return found


def compare(following: list[str], followers: list[str], names: dict[str, str],
            exceptions: list[dict]) -> tuple[list[str], list[tuple[dict, str]],
                                             dict[str, list[dict]], list[dict]]:
    """Разность подписок за вычетом исключений — ПО ЛОГИНУ, а не по имени (194).

    ИМЯ НЕ ДОКАЗЫВАЕТ ВЛАДЕНИЯ. Имя профиля аккаунт ставит себе сам: назовись
    любой из кандидатов «Python» — и исключение по имени тихо сняло бы его со
    списка (взгляд на #381). Поэтому кандидата снимает только исключение по
    ЛОГИНУ, а запись по имени — подсказка: совпавший по имени остаётся
    кандидатом, и рядом сказано, чьё имя совпало, — подтвердить его можно
    только логином.

    Возвращает: кандидатов; сработавшие исключения по логину; подсказки по
    имени — кандидат → записи, чьё имя совпало; исключения по логину, на
    которых подписки нет вовсе. ``names`` — имя профиля по логину, только для
    разности.
    """
    mutual = {login.lower() for login in followers}
    lonely = [login for login in following if login.lower() not in mutual]
    followed = {login.lower() for login in following}
    matched: list[tuple[dict, str]] = []
    stale: list[dict] = []
    excused: set[str] = set()
    hints: dict[str, list[dict]] = {}
    for one in exceptions:
        login = one.get("login", "").lower()
        name = one.get("name", "").strip().lower()
        if login:
            hit = next((who for who in lonely if who.lower() == login), "")
            if hit:
                matched.append((one, hit))
                excused.add(hit)
            elif login not in followed:
                # На взаимного исключение просто не нужно; лишним оно
                # становится, только если подписки на логин нет вовсе.
                stale.append(one)
        elif name:
            for who in lonely:
                if (names.get(who) or "").strip().lower() == name:
                    hints.setdefault(who, []).append(one)
    candidates = [who for who in lonely if who not in excused]
    return candidates, matched, {who: hints[who] for who in candidates if who in hints}, stale


#: Знаки разметки, которые чужое имя профиля могло бы обратить в ссылку,
#: выделение или код. Экранируются обратной косой.
MARKUP = re.compile(r"([\\`*_\[\]()<>#|~!])")


def plain(text: str) -> str:
    """Чужое имя профиля — как текст, а не как разметка.

    Имя пишет владелец аккаунта, а не мы: ``@кто-то`` в нём упомянул бы
    постороннего, ``](`` сломал бы ссылку (взгляд на #381). Упоминание
    гасится невидимым разделителем после ``@``, знаки разметки — обратной косой.
    """
    return MARKUP.sub(r"\\\1", text).replace("@", "@\u2060")


def profile(who: str, names: dict[str, str]) -> str:
    """Ссылка на профиль: текстом — имя, как владелец видит его на странице, рядом логин."""
    name = (names.get(who) or "").strip()
    return f"[{plain(name) if name else who}](https://github.com/{who}){f' · `{who}`' if name else ''}"


def body(candidates: list[str], names: dict[str, str], matched: list[tuple[dict, str]],
         hints: dict[str, list[dict]], stale: list[dict], unused: list[dict],
         following: int, followers: int) -> str:
    """Тело задачи: кандидаты с подсказками, сработавшие, лишние и несовпавшие записи."""
    lines = [MARKER, "",
             f"> Сверка подписок `{OWNER}`: подписан на {following}, подписчиков "
             f"{followers}. Собирает `scripts/follow_check.py` по расписанию "
             f"(`.github/workflows/follow-check.yml`); руками тело не правится — "
             f"следующий прогон его перепишет.", ""]
    if candidates:
        lines += ["## Подписан, а взаимности нет", "",
                  "По каждому — одно из двух: **отписаться** (на странице аккаунта) "
                  "или **внести в исключения** — строкой с логином в "
                  "`.github/follow-exceptions.json` и причиной.", ""]
        for who in candidates:
            said = ", ".join(f"«{plain(one['name'])}»" for one in hints.get(who, []))
            hint = (f" — имя совпало с исключением {said}; имя не доказывает, что это "
                    f"тот аккаунт: если он, впишите логин `{who}`") if said else ""
            lines.append(f"- [ ] {profile(who, names)}{hint}")
    else:
        lines += ["## Расхождений нет", "",
                  "Все, на кого подписан владелец, подписаны в ответ или внесены в "
                  "исключения. Закрыть задачу — решение владельца."]
    if matched:
        lines += ["", "## Исключения сработали", ""]
        lines += [f"- {profile(who, names)} ({plain(one['why'])})" for one, who in matched]
    if stale:
        lines += ["", "## Исключения без подписки", "",
                  "Подписки на этот логин нет вовсе — исключение можно убрать из файла.", ""]
        lines += [f"- `{one['login']}` ({plain(one['why'])})" for one in stale]
    if unused:
        lines += ["", "## Подсказки по имени ни с кем не совпали", "",
                  "Среди подписок без взаимности нет аккаунта с таким именем: он "
                  "подписан в ответ, подписка снята или имя другое. Записи по имени "
                  "кандидата не снимают — надёжнее вписать логин.", ""]
        lines += [f"- {plain(one['name'])} ({plain(one['why'])})" for one in unused]
    return "\n".join(lines) + "\n"


def unused_hints(exceptions: list[dict], hints: dict[str, list[dict]]) -> list[dict]:
    """Записи по имени, не совпавшие ни с одним кандидатом."""
    used = {id(one) for found in hints.values() for one in found}
    return [one for one in exceptions
            if not one.get("login") and one.get("name") and id(one) not in used]


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
             "twin2": "Twin", "fake": "Python", "evil": "@victim ](x) *b*"}
    following = ["py", "gen", "x", "mutual", "twin1", "twin2", "fake", "evil"]
    followers = ["Mutual", "fan"]
    exceptions = [{"name": "python", "why": "т"}, {"login": "GEN", "why": "т"},
                  {"name": "Twin", "why": "т"}, {"name": "Ушедший", "why": "т"},
                  {"login": "mutual", "why": "т"}, {"login": "gone", "why": "т"}]
    candidates, matched, hints, stale = compare(following, followers, names, exceptions)
    unused = unused_hints(exceptions, hints)
    cases = [
        ("взаимная подписка не кандидат, регистр не важен", "mutual" not in candidates),
        ("исключение по логину снимает кандидата, регистр не важен",
         "gen" not in candidates and [w for _, w in matched] == ["gen"]),
        ("имя не снимает: совпавший по имени остаётся кандидатом (194)",
         "py" in candidates and "fake" in candidates),
        ("подделка имени видна: оба «Python» с подсказкой", set(hints) >= {"py", "fake"}),
        ("имя на двух аккаунтах — оба кандидаты с подсказкой",
         {"twin1", "twin2"} <= set(hints)),
        ("без исключения — кандидат без подсказки", "x" in candidates and "x" not in hints),
        ("логин без подписки — лишний", [o["login"] for o in stale] == ["gone"]),
        ("логин на взаимного не лишний", all(o["login"] != "mutual" for o in stale)),
        ("имя, ни с кем не совпавшее, названо", [o["name"] for o in unused] == ["Ушедший"]),
    ]
    text = body(candidates, names, matched, hints, stale, unused,
                len(following), len(followers))
    cases += [
        ("в теле маркер, ссылка с логином и подсказка",
         MARKER in text and "[X](https://github.com/x) · `x`" in text
         and "впишите логин `fake`" in text),
        ("чужое имя — текст: упоминание погашено, разметка экранирована",
         "@victim" not in text and "@\u2060victim" in text and "\\]\\(x\\)" in text),
        ("пустая разность — «расхождений нет»",
         "Расхождений нет" in body([], {}, [], {}, [], [], 1, 1)),
    ]
    for name, good in cases:
        if not good:
            broken.append(name)
        print(f"  {'верно' if good else 'СБОЙ '} — {name}")

    with tempfile.TemporaryDirectory(dir=checks.runner_temp()) as place:
        bad = pathlib.Path(place) / "exceptions.json"
        for said, raw in (("без причины", '{"exceptions": [{"name": "X"}]}'),
                          ("строкой вместо объекта", '{"exceptions": ["Python"]}'),
                          ("с полем не строкой", '{"exceptions": [{"login": 1, "why": "т"}]}')):
            bad.write_text(raw, encoding="utf-8")
            try:
                load_exceptions(bad)
                broken.append(f"запись {said} не отвергнута")
            except ValueError:
                print(f"  верно — запись {said} отвергнута разбором (исход 2)")

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
        candidates, matched, hints, stale = compare(following, followers, names, exceptions)
        unused = unused_hints(exceptions, hints)
        text = body(candidates, names, matched, hints, stale, unused,
                    len(following), len(followers))
        said = sync(text, bool(candidates), args.dry_run)
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as refusal:
        print(checks.annotate("error", f"сверка подписок не отработала — {refusal}"),
              file=sys.stderr)
        return 2
    print(f"подписан на {len(following)}, подписчиков {len(followers)}; без взаимности "
          f"{len(candidates)} (из них с подсказкой по имени {len(hints)}), исключений "
          f"сработало {len(matched)}, лишних {len(stale)}; {said}")
    return 1 if candidates else 0


if __name__ == "__main__":
    raise SystemExit(main())
