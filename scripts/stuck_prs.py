#!/usr/bin/env python3
"""Изменение готово и не слито — сказать это вслух, а не ждать молча.

ИНЦИДЕНТ, ТОЧНЕЕ ТРИ. Дважды за смену 7 сентября и ещё раз 8-го изменение
вставало **не из-за красного**: событие площадки не доходило, и автоматика
ждала того, чего больше не будет.

* **#142** — обязательной проверки не создавалось вовсе: защита ветки ждала
  имени, которого никто не создаст. События ``opened`` и ``reopened`` прогон не
  разбудили, помогло только ``synchronize``;
* **#146** — проверка позеленела в 13:31:18, автомерж включён, конфликтов нет,
  а ``mergeable_state`` застыл на ``blocked`` и не менялся **пять часов**;
* **#183** — то же самое и **девять с половиной минут**; расклинило снятием и
  возвратом метки содержания.

ПОЧЕМУ ЭТО НЕ ЧИНИТСЯ ОЖИДАНИЕМ. Изменение при этом ГОТОВО — зелёное, без
конфликтов, с включённым автомержем. Снаружи это неотличимо от «ещё бежит»:
список проверок выглядит обычным, красного нет, и заметить можно только сверкой
времён. Сторож свежести ловит остановку суточной сборки, дежурный по общей ветке
— красную общую ветку; здесь и сборка идёт, и ветка зелёная.

ПОРОГ ВЗЯТ ЗАМЕРОМ, А НЕ НА ГЛАЗ. Слияние у витрины проходит за 20–60 секунд —
так слились #175, #177, #178, #179, #180, #182 и #188 за одну смену. Застревания
длились 9,5 минут и 5 часов. Порог в ``STUCK_MINUTES`` минут лежит между ними с
запасом в обе стороны: разрыв не пограничный, и подбирать его тоньше нечего.

ЧТО СТОРОЖ ДЕЛАЕТ И ЧЕГО НЕ ДЕЛАЕТ. Он **говорит**, а не толкает. Расклинить
изменение можно снятием и возвратом метки — но делать это за человека значило бы
прятать частоту, с которой площадка теряет состояние, а именно её и надо видеть,
чтобы решить, нужен ли обход вообще. Он и не закрывает свою задачу: закрытие —
жест человека, «я посмотрел», а механизм такого сказать не может (взято у
сторожа свежести, там это решение уже объяснено).

ЧЕМ ОН УЯЗВИМ. Он сам на расписании и уязвим ровно тем же, чем всё остальное на
расписании. Это второй рубеж, а не первый: первый — глаза владельца, и сегодня
именно они нашли #146.

Запуск::

    python scripts/stuck_prs.py [--minutes 5] [--dry-run]

Исходы: 0 — застрявших нет; 1 — есть, задача заведена или обновлена;
2 — сторож не отработал (площадка не ответила, ответ не разобран).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

import checks

REPO = os.environ.get("SHOWCASE_REPO", "ArtVsMark/ArtVsMark")
API = "https://api.github.com"

#: Порог, за которым готовое изменение считается застрявшим. Замер выше:
#: обычное слияние 20–60 секунд, застревания 9,5 минут и 5 часов.
STUCK_MINUTES = 5

#: Обязательная проверка. Имя РАБОТЫ, а не прогона: в защите ветки правило
#: записано именно по нему, и расхождение этих имён однажды сделало несливаемым
#: каждое изменение.
REQUIRED = "PR check"

#: Метка конвейера, означающая «придержано намеренно». Придержанное изменение
#: не застряло — оно ждёт человека, и жаловаться на него значит звать его
#: смотреть на то, что он сам и поставил.
HOLD = "hold"

#: По этой строке задача находится снова. Одна задача на весь предмет: вторая
#: означала бы, что о том же кричат дважды.
MARKER = "<!-- stuck-prs: не удаляйте, по этой строке задача находится снова -->"


def _api(path: str) -> object:
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
        return json.load(response) if response.status != 204 else None


def _post(path: str, method: str, payload: dict) -> object:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode(),
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response) if response.status != 204 else None


def stuck(change: dict, checked: str | None, now: dt.datetime,
          minutes: int) -> str | None:
    """Причина, по которой изменение считается застрявшим, либо ``None``.

    Вынесено из похода в сеть, чтобы набор судил РАЗБОР, а не площадку
    (правило 150): дожидаться настоящего застревания значило бы проверять
    терпение, а не механизм.

    УСЛОВИЯ ПЕРЕЧИСЛЕНЫ ПОИМЁННО, и каждое отсеивает свой законный случай:

    * ``hold`` — придержано намеренно, ждёт человека, а не площадку;
    * автомерж выключен — значит сливать никто и не собирался;
    * обязательная проверка не зелёная — это другой предмет, у него свой
      адресат, и жаловаться здесь значило бы кричать о красном дважды;
    * конфликт (``dirty``) — тоже другой предмет, чинится правкой ветки;
    * состояние менялось недавно — площадка ещё считает.
    """
    labels = {label.get("name") for label in change.get("labels", [])}
    if HOLD in labels:
        return None
    if not change.get("auto_merge"):
        return None
    if checked != "success":
        return None
    if change.get("mergeable_state") == "dirty":
        return None
    touched = dt.datetime.fromisoformat(change["updated_at"].replace("Z", "+00:00"))
    idle = (now - touched).total_seconds() / 60
    if idle < minutes:
        return None
    return (f"#{change['number']} «{checks.clip(change['title'], 60)}» — "
            f"{REQUIRED} зелёная, автомерж включён, конфликтов нет, "
            f"а состояние не менялось {idle:.0f} мин "
            f"(состояние: {change.get('mergeable_state', '—')})")


def required_verdict(number: int) -> str | None:
    """Исход обязательной проверки на голове изменения, либо ``None``.

    ``None`` означает «записи с таким именем на голове нет» — ровно случай
    #142, и он ОТЛИЧЁН от «есть и красная»: первое чинится пробуждением
    прогона, второе — правкой кода.

    Считается ПОСЛЕДНЯЯ запись с этим именем: на одной голове их бывает
    несколько, и отменённая среди них не отменяет зелёную.
    """
    head = _api(f"/repos/{REPO}/pulls/{number}")
    runs = _api(f"/repos/{REPO}/commits/{head['head']['sha']}/check-runs?per_page=100")
    entries = [r for r in (runs.get("check_runs", []) if isinstance(runs, dict) else [])
               if r.get("name") == REQUIRED]
    if not entries:
        return None
    latest = max(entries, key=lambda r: r.get("started_at") or "")
    return latest.get("conclusion")


def body(found: list[str], minutes: int) -> str:
    """Тело задачи: что стоит, почему это находка и что с этим делать."""
    lines = [
        MARKER,
        "",
        "Изменение **готово и не слито**, и это заметил механизм, а не человек.",
        "",
        "Зелёное на изменении обычно означает «сейчас сольётся»: у витрины это",
        f"занимает 20–60 секунд. Ниже — изменения, у которых `{REQUIRED}` зелёная,",
        "автомерж включён, конфликтов нет, а состояние не менялось дольше",
        f"**{minutes} минут**. Снаружи это неотличимо от «ещё бежит».",
        "",
        "**Что обычно помогает.** Снять и вернуть метку содержания: событие",
        "`labeled` заставляет площадку пересчитать состояние. Так расклинило",
        "изменения #146 и #183.",
        "",
        "**Сторож этого не делает сам** — намеренно. Толкать за площадку значило",
        "бы прятать частоту, с которой она теряет состояние, а видеть её нужно:",
        "именно она решает, стоит ли заводить обход вообще.",
        "",
        "Задача ведётся одна: пока открыта, следующие прогоны обновляют её тело.",
        "Закройте её сами — закрытие говорит «я посмотрел», а механизм такого",
        "сказать не может.",
        "",
        "## Что стоит сейчас",
        "",
    ]
    lines += [f"- {line}" for line in found]
    return "\n".join(lines) + "\n"


def sync_issue(found: list[str], minutes: int, dry: bool) -> str:
    """Заводит или обновляет ОДНУ задачу. Возвращает, что сделано."""
    issues = _api(f"/repos/{REPO}/issues?state=open&per_page=100")
    existing = next((i for i in issues if MARKER in (i.get("body") or "")), None)
    text = body(found, minutes)
    if dry:
        return f"вхолостую: {'обновил бы' if existing else 'завёл бы'} задачу"
    if existing:
        _post(f"/repos/{REPO}/issues/{existing['number']}", "PATCH", {"body": text})
        return f"задача #{existing['number']} обновлена"
    made = _post(f"/repos/{REPO}/issues", "POST",
                 {"title": "Изменение готово и не слито дольше порога",
                  "body": text, "labels": ["bug"]})
    return f"задача #{made['number']} заведена"


def selftest() -> int:
    """Прогоняет через сторож то, что он обязан отвергнуть и обязан пропустить.

    Набор двусторонний (правило 140), и ложный отказ здесь дороже пропуска:
    сторож, кричащий о нормальном слиянии, приучает не смотреть на его задачу.
    """
    broken: list[str] = []
    now = dt.datetime(2026, 9, 8, 20, 0, tzinfo=dt.timezone.utc)

    def change(minutes_ago: int, **over) -> dict:
        seen = now - dt.timedelta(minutes=minutes_ago)
        base = {"number": 7, "title": "заголовок", "labels": [],
                "auto_merge": {"merge_method": "squash"},
                "mergeable_state": "blocked",
                "updated_at": seen.isoformat().replace("+00:00", "Z")}
        return {**base, **over}

    # Соседи признака «застряло» перебраны поимённо: каждое условие отсеивает
    # СВОЙ законный случай, и набор проверяет их по одному.
    cases = [
        ("готово и стоит дольше порога", change(30), "success", True),
        ("стоит, но меньше порога", change(1), "success", False),
        ("придержано меткой hold", change(30, labels=[{"name": "hold"}]), "success", False),
        ("автомерж выключен", change(30, auto_merge=None), "success", False),
        ("обязательная проверка красная", change(30), "failure", False),
        ("обязательной проверки нет вовсе", change(30), None, False),
        ("конфликт с общей веткой", change(30, mergeable_state="dirty"), "success", False),
        ("зелёное и уже сливается", change(30, mergeable_state="clean"), "success", True),
    ]
    for name, made, checked, expected in cases:
        got = stuck(made, checked, now, STUCK_MINUTES)
        if bool(got) != expected:
            broken.append(f"{name}: ожидалось находок {expected}, вышло {bool(got)}")
        print(f"  {'найдено ' if got else 'пропущено'} — {name}")

    # Находка НАЗЫВАЕТ предмет: номер, заголовок и сколько стоит. «Что-то
    # застряло» — сигнал, по которому нечего проверить (правило 039).
    said = stuck(change(42), "success", now, STUCK_MINUTES)
    for part in ("#7", "42 мин", REQUIRED):
        if part not in said:
            broken.append(f"находка не называет {part!r}: {said}")
    print(f"  назван    — предмет: {checks.clip(said, 70)}")

    # Тело задачи несёт и находки, и способ расклинить, и то, что сторож его
    # намеренно не применяет: иначе человек прочтёт «сломалось» без «что делать».
    text = body([said], STUCK_MINUTES)
    for part in (MARKER, "#7", "labeled", "не делает сам", "Закройте её сами"):
        if part not in text:
            broken.append(f"тело задачи не несёт {part!r}")
    print("  да  — тело задачи: находка, способ, граница и кто закрывает")

    if broken:
        print(checks.annotate("error", "самопроверка провалена"), file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: сторож отличает застрявшее от нормального")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--minutes", type=int, default=STUCK_MINUTES,
                        help=f"порог в минутах (по умолчанию {STUCK_MINUTES})")
    parser.add_argument("--dry-run", action="store_true", help="не трогать задачу")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    now = dt.datetime.now(dt.timezone.utc)
    try:
        opened = _api(f"/repos/{REPO}/pulls?state=open&per_page=50")
        found = []
        for short in opened:
            # Список изменений не несёт mergeable_state — его отдаёт только
            # запрос по одному. Ходим по одному и туда же за проверкой.
            full = _api(f"/repos/{REPO}/pulls/{short['number']}")
            reason = stuck(full, required_verdict(short["number"]), now, args.minutes)
            if reason:
                found.append(reason)
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as refusal:
        # Третий исход: площадка не ответила. Чинит это тот, кто запускает, а не
        # автор изменения, и красным становится прогон, а не находка (039).
        print(checks.annotate("error", f"сторож не отработал: площадка не ответила "
                              f"— {refusal}"), file=sys.stderr)
        return 2

    if not found:
        print(f"застрявших изменений нет: открытых {len(opened)}, "
              f"порог {args.minutes} мин")
        return 0

    print(checks.annotate("warning", f"готовы и не слиты: {len(found)}"))
    for line in found:
        print(f"  • {line}")
    try:
        print(sync_issue(found, args.minutes, args.dry_run))
    except (urllib.error.URLError, OSError, ValueError, KeyError) as refusal:
        print(checks.annotate("error", f"находка есть, а адресата нет: задача не "
                              f"заведена — {refusal}"), file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
