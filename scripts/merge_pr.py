#!/usr/bin/env python3
"""Сливает PR витрины, пересобирая сообщение коммита слияния.

Зачем. Проверка атрибуции на конечной истории `main` показала, что по
первопредкам её нет вовсе: GitHub пишет своё «Merge pull request #N from …», и
трейлеры коммитов ветки в него не попадают. Кто делал изменение, видно только
если провалиться во вторую ветку слияния — а смотрят обычно первую.

Поэтому сообщение собирается здесь: заголовок PR, перечень работ и трейлеры,
снятые с коммитов ветки без повторов. Автор коммита слияния — владелец токена,
которым запущен скрипт; для витрины это владелец репозитория.

Запуск::

    python scripts/merge_pr.py 19             # показать сообщение и слить
    python scripts/merge_pr.py 19 --dry-run   # только показать
    python scripts/merge_pr.py --when-green   # слить все готовые PR

``--when-green`` пропускает черновики, PR с меткой ``hold`` и всё, у чего
проверки не зелёные. Отсутствие проверок зелёным НЕ считается: пустой список
означает «не стартовало», а не «всё хорошо».
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

REPO = os.environ.get("SHOWCASE_REPO", "ArtVsMark/ArtVsMark")
API = "https://api.github.com"
HOLD = "hold"


def _api(path: str, method: str = "GET", payload: dict | None = None) -> object:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("нет GH_TOKEN — слияние требует токена с правом записи")
    request = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if payload is not None else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
    return json.loads(body) if body else {}


def commit_message(number: int) -> tuple[str, str]:
    """Заголовок и тело коммита слияния.

    Трейлеры собираются со всех коммитов ветки и склеиваются без повторов:
    одно и то же соавторство, повторённое в каждом коммите, в итоговом
    сообщении должно остаться одной строкой.
    """
    pull = _api(f"/repos/{REPO}/pulls/{number}")
    commits = _api(f"/repos/{REPO}/pulls/{number}/commits?per_page=100")

    works, trailers = [], []
    for commit in commits:
        lines = commit["commit"]["message"].splitlines()
        works.append(lines[0])
        for line in lines[1:]:
            if ":" in line and line.split(":", 1)[0] in ("Co-Authored-By", "Claude-Session"):
                if line not in trailers:
                    trailers.append(line)

    title = f"{pull['title']} (#{number})"
    body = []
    if len(works) > 1:
        body += [f"* {work}" for work in works] + [""]
    body.append(f"Ветка: {pull['head']['ref']}")
    if trailers:
        body += [""] + trailers
    return title, "\n".join(body)


def checks_are_green(sha: str) -> tuple[bool, str]:
    """Зелены ли проверки на коммите.

    Пустой список проверок зелёным не считается: условие «нет красных и нет
    ожидающих» истинно и на пустом множестве, а означает оно «не стартовало».
    """
    runs = _api(f"/repos/{REPO}/commits/{sha}/check-runs?per_page=100")["check_runs"]
    if not runs:
        return False, "проверок нет — это «не стартовало», а не «всё хорошо»"
    bad = [r["name"] for r in runs if r["conclusion"] not in ("success", "skipped", "neutral")]
    return not bad, "зелено" if not bad else f"не зелены: {', '.join(sorted(set(bad)))}"


def merge(number: int, dry_run: bool = False) -> int:
    title, body = commit_message(number)
    print(f"--- сообщение слияния PR #{number} ---\n{title}\n\n{body}\n---")
    if dry_run:
        return 0
    try:
        result = _api(
            f"/repos/{REPO}/pulls/{number}/merge",
            method="PUT",
            payload={"commit_title": title, "commit_message": body, "merge_method": "merge"},
        )
    except urllib.error.HTTPError as error:
        raise SystemExit(f"слияние PR #{number} отклонено: {error.code} {error.read().decode()[:200]}")
    print(f"PR #{number} слит: {result.get('sha', '')[:10]}")
    return 0


def when_green(dry_run: bool = False) -> int:
    merged = 0
    for pull in _api(f"/repos/{REPO}/pulls?state=open&per_page=50"):
        number = pull["number"]
        if pull["draft"]:
            print(f"#{number}: черновик — пропуск")
            continue
        if any(label["name"] == HOLD for label in pull["labels"]):
            print(f"#{number}: метка {HOLD} — пропуск")
            continue
        green, why = checks_are_green(pull["head"]["sha"])
        if not green:
            print(f"#{number}: {why} — пропуск")
            continue
        merge(number, dry_run)
        merged += 1
    print(f"слито: {merged}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    rest = [a for a in args if not a.startswith("--")]
    if "--when-green" in args:
        return when_green(dry_run)
    if not rest:
        print(__doc__)
        return 1
    return merge(int(rest[0]), dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
