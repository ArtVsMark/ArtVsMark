#!/usr/bin/env python3
"""Прогон витрины не бежал дольше срока — и это видно, а не молчит.

ИНЦИДЕНТ. 28 августа суточная сборка не запустилась ни разу: площадка не
гарантирует `schedule`, при нагрузке она его просто не ставит. Витрина сутки
показывала вчерашние числа и не выдавала этого ничем — пропущенный прогон не
красит ничего, потому что его нет. Заметил владелец, а не механизм.

ЗАМЕР, А НЕ ОПАСЕНИЕ: за девять дней жизни сборки пропущен один. Не редкость,
которой можно пренебречь.

ЧЕМ ЭТОТ СТОРОЖ ОТЛИЧАЕТСЯ ОТ ОТМЕТКИ НА СТРАНИЦЕ. Витрина подписана «data as
of <дата>» — это день, когда числа последний раз ИЗМЕНИЛИСЬ. Здесь другой
вопрос: бежала ли сборка вообще. Числа могут не меняться сутки законно, а вот
сборка, не бежавшая двое суток, — уже поломка. Два вопроса, два ответа; сводить
их в один значило бы потерять оба.

ЗА ЧЕМ ОН ХОДИТ. За суточной сборкой чисел и за прогоном змейки. Второй
добавлен 8 сентября не по инциденту, а по названному пробелу: критерий «ветка
`output` отдаётся» был объявлен в .rules/roles.md и проверен разово и вручную.
Своего сторожа заводить не пришлось — вопрос «бежал ли прогон» тот же самый, а
разное у них только тело задачи (правило 090: общая утилита выше обоих).

ЧЕГО ОН НЕ МОЖЕТ. Он сам живёт на расписании и уязвим ровно тем же. Два
независимых расписания пропускаются одновременно реже, чем одно, — но «реже» это
не «никогда», и обещать здесь нечего. Поэтому он идёт ВТОРЫМ рубежом, а первым
стоит отметка на самой странице: та не зависит от прогонов вовсе.

ЧЕГО ОН НЕ ДЕЛАЕТ. Не закрывает задачу, когда сборка снова пошла. Закрытие —
жест человека: он говорит «я посмотрел», а механизм такого сказать не может.
Взято у дежурного по общей ветке в каталоге (playbook, scripts/main_red.py):
там это решение уже принято и объяснено, и своего «почему» здесь не пишется
(правило 153).

Запуск::

    python scripts/staleness.py [--workflow metrics.yml|snake.yml] [--hours 36] [--dry-run]

Исходы: 0 — сборка свежая; 1 — просрочена, задача заведена или обновлена;
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

#: За чем сторож ходит. Прогонов у витрины два, и молчат они о РАЗНОМ: один
#: приносит числа, второй — змейку на полотне активности. Свести их в один
#: вопрос значило бы потерять оба ответа (правило 039), а вести одну задачу на
#: двоих — переписывать её по кругу: две поломки, одно тело, каждый прогон
#: затирает чужую.
#:
#: ЗМЕЙКА ПОПАЛА СЮДА ПО НАЗВАННОМУ ПРОБЕЛУ, А НЕ ПО ИНЦИДЕНТУ. Критерий
#: профиля «ветка `output` отдаётся» жил в .rules/roles.md проверенным разово и
#: вручную: сборка читает змейку молча, и её пропажу видно только глазом — на
#: полотне вместо движения ровный календарь. Своего механизма заводить не
#: пришлось: вопрос «бежал ли прогон» здесь тот же самый.
WATCHED = {
    "metrics.yml": {
        "subject": "витрина",
        "title": "Витрина не обновлялась дольше {hours} часов",
        "what": "Прогон `{workflow}` не приносил свежих чисел дольше {hours} часов.",
        "harm": "Витрина показывает живые числа и выглядит одинаково свежей "
                "независимо от того, когда они собраны. Подпись «data as of» под "
                "плитками — первый рубеж: она показывает, когда числа менялись. "
                "Этот сторож — второй: он отвечает на другой вопрос, бежала ли "
                "сборка вообще.",
    },
    "snake.yml": {
        "subject": "змейка",
        "title": "Змейка не пересобиралась дольше {hours} часов",
        "what": "Прогон `{workflow}` не обновлял ветку `output` дольше {hours} часов.",
        "harm": "Змейка вклеивается в полотно активности из ветки `output`, и "
                "молчание источника сборка переживает молча: полотно рисует "
                "собственный календарь. Битой картинки при этом не появляется — "
                "и потому пропажу не видно ничем, кроме этого сторожа.",
    },
}


def marker(workflow: str) -> str:
    """По этой строке задача находится снова — своя у каждого прогона.

    Заголовок для этого не годится: его правят руками, и тогда прогон завёл бы
    вторую задачу вместо обновления. Имя прогона внутри маркера разводит две
    задачи: без него сторож змейки переписывал бы задачу о числах.
    """
    return (f"<!-- staleness:{workflow}: не удаляйте, "
            f"по этой строке задача находится снова -->")

#: Порог по умолчанию. Сборка суточная, значит сутки молчания — норма, а
#: полтора — уже нет.
#:
#: ЗАПАС В ДВЕНАДЦАТЬ ЧАСОВ ВЗЯТ ПО ЗАМЕРУ, А НЕ НА ГЛАЗ. Расписание площадки
#: плавает сильно: девять прогонов пришлись на 04:54–05:06, а один — на 15:20,
#: то есть разброс до одиннадцати часов. При пороге в сутки промежуток
#: 27.08 15:20 → 29.08 04:23 дал бы ложную просрочку на ИСПРАВНОЙ сборке, а
#: ложный отказ здесь дороже пропуска: сторож, кричащий на здоровое, приучает
#: закрывать его задачи не глядя.
#:
#: ЦЕНА ЭТОГО ЗАПАСА НАЗВАНА: просрочка замечается через полтора суток, то есть
#: МЕДЛЕННЕЕ человека — сегодняшний пропуск владелец увидел через сутки. Поэтому
#: сторож и не первый рубеж: первым стоит подпись «data as of» на самой
#: странице, которая видна сразу и не зависит от прогонов вовсе.
DEFAULT_HOURS = 36


def _api(path: str, method: str = "GET", payload: dict | None = None) -> object:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode() if payload else None,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response) if response.status != 204 else None


def last_success(workflow: str) -> dt.datetime | None:
    """Время последнего успешного прогона, либо ``None``.

    ``None`` — это «успешных прогонов нет вовсе», и решение по нему принимает
    вызывающий: у молодого прогона это норма, у живущего месяц — поломка
    (правило 010).
    """
    runs = _api(f"/repos/{REPO}/actions/workflows/{workflow}"
                f"/runs?status=success&per_page=1")
    entries = runs.get("workflow_runs", []) if isinstance(runs, dict) else []
    if not entries:
        return None
    return dt.datetime.fromisoformat(entries[0]["created_at"].replace("Z", "+00:00"))


def verdict(last: dt.datetime | None, now: dt.datetime, hours: int) -> tuple[bool, str]:
    """Просрочена ли сборка и что именно сказать.

    Вынесено из ``main``, чтобы проверять на подставном времени, не ходя в API
    и не дожидаясь настоящей просрочки.
    """
    if last is None:
        return True, ("успешных прогонов нет вовсе — прогон либо ни разу не "
                      "отработал, либо падает каждый раз")
    age = (now - last).total_seconds() / 3600
    when = last.strftime("%Y-%m-%d %H:%M UTC")
    if age > hours:
        return True, (f"последний удачный прогон — {when}, то есть "
                      f"{age:.0f} ч назад при пороге {hours} ч")
    return False, f"последний удачный прогон — {when}, {age:.0f} ч назад"


def body(reason: str, workflow: str, hours: int) -> str:
    """Тело задачи: что случилось, чем это грозит и что делать.

    Чем грозит — своё у каждого прогона: устаревшие числа и пропавшая змейка
    ломают разное, и общий абзац сказал бы про обе неправду.
    """
    watched = WATCHED[workflow]
    return "\n".join([
        marker(workflow),
        "",
        watched["what"].format(workflow=workflow, hours=hours),
        "",
        f"**{reason}.**",
        "",
        "## Чем это грозит",
        "",
        watched["harm"],
        "",
        "## Что делать",
        "",
        "1. Посмотреть вкладку прогонов: сборка падает или не запускается вовсе?",
        "2. Если не запускается — площадка не гарантирует `schedule`; ручная "
        "кнопка есть у каждого прогона, ей можно догнать.",
        "3. Если падает — причина в аннотации упавшего шага.",
        "",
        "Задача **не закрывается механизмом**: он не может сказать «я посмотрел». "
        "Закрывает человек.",
    ])


def sync_issue(reason: str, workflow: str, hours: int, dry: bool) -> str:
    """Заводит или обновляет ОДНУ задачу. Возвращает, что сделано."""
    found = _api(f"/repos/{REPO}/issues?state=open&per_page=100")
    own = marker(workflow)
    existing = next((i for i in found if own in (i.get("body") or "")), None)
    text = body(reason, workflow, hours)
    if dry:
        return f"вхолостую: {'обновил бы' if existing else 'завёл бы'} задачу"
    if existing:
        _api(f"/repos/{REPO}/issues/{existing['number']}", "PATCH", {"body": text})
        return f"задача #{existing['number']} обновлена"
    made = _api(f"/repos/{REPO}/issues", "POST",
                {"title": WATCHED[workflow]["title"].format(hours=hours),
                 "body": text, "labels": ["bug"]})
    return f"задача #{made['number']} заведена"


def selftest() -> int:
    """Прогоняет через сторож то, что он обязан отвергнуть и обязан пропустить.

    Время подставное: дожидаться настоящей просрочки значило бы проверять
    механизм раз в двое суток, то есть не проверять (правило 140).
    """
    now = dt.datetime(2026, 8, 28, 12, 0, tzinfo=dt.timezone.utc)
    hour = dt.timedelta(hours=1)
    cases = [
        ("сборка бежала час назад", now - hour, False),
        ("сборка бежала сутки назад — в пределах порога", now - 24 * hour, False),
        ("ровно на пороге — ещё не просрочка", now - 36 * hour, False),
        ("на час позже порога — просрочка", now - 37 * hour, True),
        ("двое суток молчания", now - 48 * hour, True),
        ("успешных прогонов нет вовсе", None, True),
    ]
    broken = []
    for name, last, must_flag in cases:
        stale, why = verdict(last, now, DEFAULT_HOURS)
        if stale is not must_flag:
            broken.append(f"{name}: ожидалось {'просрочка' if must_flag else 'норма'}")
        print(f"  {'просрочка' if stale else 'норма    '} — {name}")

    # Отказ обязан НАЗЫВАТЬ предмет: «устарело» без даты и без порога — это
    # сигнал, по которому нечего проверить (правило 158).
    _, why = verdict(now - 48 * hour, now, DEFAULT_HOURS)
    if "2026-08-26" not in why or "36" not in why:
        broken.append(f"отказ не называет ни даты, ни порога: {why!r}")

    # Тело задачи говорит, ЧЕГО сигнал не значит, и чем этот рубеж отличается
    # от подписи на странице (правило 056).
    text = body(why, "metrics.yml", DEFAULT_HOURS)
    if marker("metrics.yml") not in text or "data as of" not in text:
        broken.append("тело задачи не несёт маркера или не разводит два рубежа")

    # ── два прогона, две задачи ────────────────────────────────────────────
    # Сторож ходит за числами и за змейкой. Общий маркер свёл бы их в одну
    # задачу, и каждый прогон затирал бы чужую поломку своей.
    if marker("metrics.yml") == marker("snake.yml"):
        broken.append("маркер общий на два прогона: задачи затрут друг друга")
    snake = body(why, "snake.yml", DEFAULT_HOURS)
    snake_checks = [
        ("тело змейки несёт свой маркер", marker("snake.yml") in snake),
        ("тело змейки не подписано чужим", marker("metrics.yml") not in snake),
        ("тело змейки называет предмет — ветку `output`", "`output`" in snake),
        ("тело змейки называет свою беду, а не чужую",
         "data as of" not in snake and "полотно" in snake),
        ("заголовки задач разные",
         WATCHED["snake.yml"]["title"] != WATCHED["metrics.yml"]["title"]),
    ]
    for name, ok in snake_checks:
        if not ok:
            broken.append(f"змейка: {name} — не выполнено")
        print(f"  {'да ' if ok else 'НЕТ'}      — {name}")

    # Прогон, о котором сторожу нечего сказать, роняет его на разборе тела:
    # задача без предмета хуже отсутствующей.
    try:
        body(why, "unknown.yml", DEFAULT_HOURS)
        broken.append("незнакомый прогон разобран молча — задача выйдет без предмета")
    except KeyError:
        print("  да       — незнакомый прогон не разбирается молча")

    if broken:
        print(checks.annotate("error", "самопроверка провалена"), file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: сторож отвергает то, что обязан, и называет предмет")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workflow", default="metrics.yml")
    parser.add_argument("--hours", type=int, default=DEFAULT_HOURS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    if args.workflow not in WATCHED:
        # Сторож умеет сказать про прогон, ЧЕМ его молчание грозит. Про
        # незнакомый он такого не знает, и завёл бы задачу без предмета —
        # отказ с причиной здесь честнее (правило 158).
        print(checks.annotate("error", f"сторож не отработал: про прогон "
                              f"{args.workflow} ему нечего сказать. Знает: "
                              f"{', '.join(sorted(WATCHED))}"), file=sys.stderr)
        return 2

    try:
        last = last_success(args.workflow)
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        # Третий исход: молчание площадки — не то же, что молчание сборки, и
        # склеить их значило бы завести задачу о поломке, которой нет (039).
        print(checks.annotate("error", f"сторож не отработал: площадка не ответила "
                              f"про {args.workflow} — {e}"), file=sys.stderr)
        return 2

    subject = WATCHED[args.workflow]["subject"]
    stale, why = verdict(last, dt.datetime.now(dt.timezone.utc), args.hours)
    if not stale:
        print(f"{subject} свежая: {why}")
        return 0

    try:
        done = sync_issue(why, args.workflow, args.hours, args.dry_run)
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        print(checks.annotate("error", f"сторож не отработал: задача не заведена — {e}"),
              file=sys.stderr)
        return 2

    print(checks.annotate("warning", f"{subject} устарела: {why}"))
    print(f"  {done}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
