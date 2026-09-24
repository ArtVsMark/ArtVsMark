#!/usr/bin/env python3
"""Переоформляет правку dependabot от имени владельца, с ботом в соавторах.

ЗАЧЕМ. Автором squash-коммита площадка ставит автора ИЗМЕНЕНИЯ (замер в
.rules/README.md § Атрибуция коммитов). Изменение dependabot открывает сам бот,
и его правка легла бы в `main` за подписью `dependabot[bot]`, тогда как
соглашение витрины — автор владелец, исполнитель трейлером (правило 123).

Гейт каталога ловит это ещё на изменении: автором стоит имя, которое в
.github/authors.txt числится СОАВТОРОМ. Так #209 простояло с 14 сентября, и за
всё время с появления гейта ни одно обновление зависимостей не слилось.

ПОЧЕМУ ПЕРЕОФОРМЛЕНИЕ, А НЕ ПОБЛАЖКА В ГЕЙТЕ. Второй путь — раздел «машины» в
списке, где боту разрешено быть автором, — ослабил бы правило у четырёх
проектов сразу, а в истории `main` появились бы коммиты за подписью бота.
Решение владельца 24 сентября: вариант A, как у суточной пересборки. Там автором
стоит владелец, а прогон площадки назван трейлером (`metrics.yml`), — здесь то
же самое, только исполнитель другой.

ЧТО ДЕЛАЕТ. Для каждого открытого изменения бота берёт его собственную правку
(разность от точки ветвления, без влитого `main`), кладёт её на свежий `main`
коммитом владельца с трейлером бота и пушит в ветку ``chore/deps-<номер>``
токеном владельца. Изменение из этой ветки открывает `agent-pr` — тем же путём,
что и любое другое, и тело у него окончательное: дописывать его некому.

Изменение самого бота не закрывается: бот закроет его сам, когда обновление
окажется в `main`. Закрой его руками — и при провале переоформленного
изменения обновление потерялось бы до следующего выпуска.

ГРАНИЦА, КОТОРАЯ ДЕЛАЕТ СТРОКИ ОСВОБОЖДЕНИЯ ПРАВДОЙ. Коммит несёт
«Журнал: не требуется» и «Соседи: нет» — решений за сдвигом пинов нет. Это
верно, только пока правка бота и есть сдвиг пинов, поэтому трогать она вправе
лишь файлы прогонов. Правка шире — находка, а не переоформление: иначе через
этот прогон в `main` уехало бы что угодно с освобождением от двух гейтов.

Реализует правила каталога: 123 (атрибуция на итоговой истории), 051 (с машины
не спрашивают того, чего ей неоткуда взять), 039 (три исхода).

Запуск::

    python scripts/reauthor_deps.py              # переоформить и запушить
    python scripts/reauthor_deps.py --dry-run    # всё, кроме пуша
    python scripts/reauthor_deps.py --selftest

Исходы: 0 — переоформлено или нечего; 1 — находка: правка бота шире сдвига
пинов или не легла на свежий `main`; 2 — не отработал: площадка или git не
ответили.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

import checks

API = "https://api.github.com"
REPO = os.environ.get("GITHUB_REPOSITORY", "ArtVsMark/ArtVsMark")

#: Кто предлагает правку и как он назван в трейлере. Адрес — тот, что в
#: .github/authors.txt: гейт каталога сверяет строку целиком.
BOT = "dependabot[bot]"
COAUTHOR = "dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>"

#: Автор коммита — владелец, та же подпись, что у суточной пересборки.
OWNER_NAME = "ArtVsMark"
OWNER_EMAIL = "arvs.markitanov@gmail.com"

#: Ветка переоформленной правки. Префикс обязан стоять в
#: scripts/checks.py::MACHINE_BRANCHES — иначе гейты спросят с машины слаг задачи
#: и след сессии; самопроверка сверяет это, а не надеется.
BRANCH_PREFIX = "chore/deps-"

#: Что правка бота вправе трогать. Бот настроен на одну экосистему —
#: github-actions (.github/dependabot.yml), — и его правка это пины в прогонах.
ALLOWED = re.compile(r"^\.github/workflows/[^/]+\.ya?ml$")

#: Строки, которые гейты спрашивают с коммита, трогающего поведение. Пишутся
#: здесь один раз и за всех: решения за сдвигом пинов нет, и это верно ровно в
#: границе ALLOWED.
JOURNAL_WAIVER = "Журнал: не требуется — пины сдвинул dependabot, решения за правкой нет"
NEIGHBOURS = "Соседи: нет — сдвиг пинов действий, признаков витрины не менялось"

EXIT_OK, EXIT_FINDING, EXIT_BROKEN = 0, 1, 2


def _api(path: str) -> object:
    """GET к площадке; токен — из окружения, как у соседних сторожей."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    request = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _git(*args: str, stdin: str | None = None) -> str:
    """git с явной кодировкой; отказ — исключение, его разбирает вызывающий."""
    return subprocess.run(["git", *args], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", check=True).stdout


def bot_changes(changes: list[dict]) -> list[dict]:
    """Открытые изменения бота из его собственных веток.

    Ветка проверяется вместе с автором: изменение, которое бот открыл бы из
    чужой ветки, переоформлять нечего — правка там не его.
    """
    return [c for c in changes
            if (c.get("user") or {}).get("login") == BOT
            and str((c.get("head") or {}).get("ref", "")).startswith("dependabot/")]


def outside(paths: list[str]) -> list[str]:
    """Файлы правки вне границы сдвига пинов."""
    return [p for p in paths if not ALLOWED.match(p)]


def quoted(text: str) -> str:
    """Текст бота цитатой, без его трейлеров.

    ЦИТАТОЙ, А НЕ КАК ЕСТЬ. У бота в теле строки вида «dependency-name: …» и
    свой «Signed-off-by»: без цитаты первые могли бы стать хвостовым блоком
    трейлеров, а второй — чужим трейлером в нашем коммите. Знак цитаты в начале
    строки выводит их из-под разбора (правило 156).
    """
    lines = [line for line in text.strip().splitlines()
             if not re.match(r"^\s*Signed-off-by:", line, re.I)]
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(f"> {line}".rstrip() for line in lines).strip()


def compose(number: int, original: str) -> str:
    """Сообщение коммита переоформленной правки.

    ``original`` — сообщения КОММИТОВ бота, а не описание его изменения:
    описание у dependabot несёт журнал выпусков зависимости HTML-разметкой на
    сотни строк, и первый живой прогон на #209 увёз бы его в историю `main`.
    Сообщение коммита у бота короткое и называет ровно то, что сдвинуто.
    """
    return "\n\n".join([
        f"deps(ci): обновление зависимостей от dependabot — изменение #{number}",
        f"Правку предложил dependabot в #{number}. Автором она переоформлена на "
        "владельца, а бот назван соавтором — так же, как суточная пересборка "
        "называет прогон площадки: автором squash-коммита площадка ставит автора "
        "изменения, и правка бота легла бы в main за его подписью (123).",
        "Составил прогон deps-reauthor; изменение откроет agent-pr по этому пушу. "
        "Тело окончательное: дописывать его некому. Изменение бота закроется само, "
        "когда обновление окажется в main.",
        "Исходное сообщение бота:\n\n" + quoted(original),
        f"{JOURNAL_WAIVER}\n{NEIGHBOURS}",
        f"Co-authored-by: {COAUTHOR}",
    ]) + "\n"


def reauthor(change: dict, dry_run: bool) -> tuple[int, str]:
    """Переоформляет одно изменение бота. Исход и строка для вывода."""
    number, ref = change["number"], change["head"]["ref"]
    branch = f"{BRANCH_PREFIX}{number}"
    _git("fetch", "--no-tags", "origin", "main:refs/remotes/origin/main",
         f"+{ref}:refs/remotes/origin/{ref}")
    source = f"refs/remotes/origin/{ref}"
    # Три точки — от точки ветвления: в ветке бота бывают влитые `main`
    # (владелец подтягивал #209 кнопкой), и их содержимое правкой бота не является.
    paths = [p for p in _git("diff", "--name-only", f"origin/main...{source}").splitlines() if p]
    if not paths:
        return EXIT_OK, f"#{number}: правка уже в main — переоформлять нечего"
    wide = outside(paths)
    if wide:
        return EXIT_FINDING, (f"#{number}: правка шире сдвига пинов — "
                              f"{checks.tail(wide, 5)}; не переоформляется, решает человек")
    patch = _git("diff", "--binary", f"origin/main...{source}")
    _git("checkout", "-B", branch, "origin/main")
    try:
        _git("apply", "--index", "-", stdin=patch)
    except subprocess.CalledProcessError as refused:
        _git("reset", "--hard", "origin/main")
        return EXIT_FINDING, (f"#{number}: правка бота не легла на свежий main — "
                              f"{checks.clip(refused.stderr.strip(), 200)}; бот перестроит её сам")
    # Сообщения собственных коммитов бота: влитые `main` сюда не входят, их
    # составляла площадка по кнопке владельца, а не бот.
    original = _git("log", "--no-merges", "--format=%B", f"origin/main..{source}").strip()
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt",
                                     delete=False) as message:
        message.write(compose(number, original))
    _git("-c", f"user.name={OWNER_NAME}", "-c", f"user.email={OWNER_EMAIL}",
         "commit", "--quiet", "-F", message.name)
    os.unlink(message.name)
    # Тот же результат уже на площадке — пушить незачем: повторный пуш будит
    # прогоны и проверки ради ничего.
    try:
        _git("fetch", "--no-tags", "origin", f"+{branch}:refs/remotes/origin/{branch}")
        same = subprocess.run(["git", "diff", "--quiet", f"origin/{branch}", "HEAD"],
                              capture_output=True).returncode == 0
    except subprocess.CalledProcessError:
        same = False
    if same:
        return EXIT_OK, f"#{number}: {branch} уже несёт ту же правку — пуш не нужен"
    if dry_run:
        return EXIT_OK, f"#{number}: собрано в {branch}, пуш пропущен (--dry-run)"
    _git("push", "--force", "origin", f"HEAD:refs/heads/{branch}")
    return EXIT_OK, f"#{number}: переоформлено в {branch}; изменение откроет agent-pr"


def selftest() -> int:
    """Прогоняет через механизм то, что он обязан отобрать и отвергнуть.

    Набор спрашивает сами гейты — метку, стоп-кран, журнал, соседей, трейлеры, —
    а не повторяет их условия (правило 150): поменяется признак там, и случай
    здесь продолжит спрашивать функцию.
    """
    import check_journal                                          # noqa: PLC0415
    import check_labels                                           # noqa: PLC0415
    import check_neighbours                                       # noqa: PLC0415
    import hold                                                   # noqa: PLC0415

    broken: list[str] = []

    def change(login: str, ref: str) -> dict:
        return {"number": 1, "user": {"login": login}, "head": {"ref": ref}}

    pick_cases = [
        ("изменение бота из его ветки", change(BOT, "dependabot/github_actions/x"), True),
        ("изменение владельца", change("ArtVsMark", "agent/x"), False),
        ("бот из чужой ветки — правка не его", change(BOT, "agent/x"), False),
        ("похожее имя — не бот", change("dependabot", "dependabot/github_actions/x"), False),
    ]
    for name, item, expected in pick_cases:
        got = bool(bot_changes([item]))
        if got is not expected:
            broken.append(f"отбор, {name}: ожидалось {expected}, вышло {got}")
        print(f"  {'взято    ' if got else 'пропущено'} — отбор: {name}")

    path_cases = [
        ("пин в прогоне", [".github/workflows/pr-check.yml"], []),
        ("правка скрипта — шире сдвига пинов", ["scripts/a.py"],
         ["scripts/a.py"]),
        ("вложенный каталог прогонов — не прогон",
         [".github/workflows/sub/x.yml"], [".github/workflows/sub/x.yml"]),
        ("настройка самого бота — не пин", [".github/dependabot.yml"],
         [".github/dependabot.yml"]),
    ]
    for name, paths, expected in path_cases:
        got = outside(paths)
        if got != expected:
            broken.append(f"граница, {name}: ожидалось {expected}, вышло {got}")
        print(f"  {'отвергнуто' if got else 'принято   '} — граница: {name}")

    # Сообщение проверяется ГЕЙТАМИ, которые его потом и прочтут.
    body = ("Bumps the actions group.\n\n---\nupdated-dependencies:\n"
            "- dependency-name: x\n  dependency-type: direct:production\n...\n\n"
            "Соседи: так бот не пишет, но цитата обязана это выдержать\n\n"
            "Signed-off-by: dependabot[bot] <support@github.com>")
    message = compose(209, f"chore(ci): bump x from 1 to 2\n\n{body}")
    subject, _, rest = message.partition("\n")
    said = checks.trailers(message)
    message_cases = [
        ("метка по заголовку — dependencies",
         check_labels.label_for_subject(subject) == "dependencies"),
        ("соавтор — один, и это бот",
         said.get("co-authored-by") == [COAUTHOR]),
        ("чужой Signed-off-by не уехал трейлером", "signed-off-by" not in said),
        ("стоп-кран снимается без тела: дописывать некому",
         hold.marker_needed(message) is False),
        ("журнал освобождён строкой с причиной",
         bool(check_journal.WAIVER.search(message))),
        ("о соседях сказано ровно одной строкой, и она наша",
         [m.group("said") for m in check_neighbours.ANSWER.finditer(message)]
         == [NEIGHBOURS.split(":", 1)[1].strip()]),
        ("ветка машинная для гейтов",
         any(f"{BRANCH_PREFIX}209".startswith(n) for n in checks.MACHINE_BRANCHES)),
    ]
    for name, ok in message_cases:
        if not ok:
            broken.append(f"сообщение: {name} — не выполнено\n{message}")
        print(f"  {'да ' if ok else 'НЕТ'} — сообщение: {name}")

    if broken:
        print(checks.annotate("error", "самопроверка провалена"), file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return EXIT_FINDING
    print("самопроверка пройдена: отбор, граница и сообщение держат объявленное")
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="всё, кроме пуша")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()

    try:
        changes = _api(f"/repos/{REPO}/pulls?state=open&per_page=100")
    except (urllib.error.URLError, OSError, ValueError) as silent:
        print(checks.annotate("error", f"не отработал: список изменений не прочитан — {silent}"),
              file=sys.stderr)
        return EXIT_BROKEN
    mine = bot_changes(changes if isinstance(changes, list) else [])
    if not mine:
        print("открытых изменений dependabot нет — переоформлять нечего")
        return EXIT_OK

    worst = EXIT_OK
    for item in mine:
        try:
            code, said = reauthor(item, args.dry_run)
        except subprocess.CalledProcessError as refused:
            code, said = EXIT_BROKEN, (f"#{item['number']}: git не отработал — "
                                       f"{checks.clip(' '.join(refused.cmd), 60)}: "
                                       f"{checks.clip((refused.stderr or '').strip(), 200)}")
        if code == EXIT_OK:
            print(said)
        else:
            print(checks.annotate("error" if code == EXIT_BROKEN else "warning", said),
                  file=sys.stderr)
        worst = max(worst, code)
    return worst


if __name__ == "__main__":
    sys.exit(main())
