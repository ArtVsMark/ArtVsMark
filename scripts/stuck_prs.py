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

Исходы: 0 — застрявших и мигнувших нет; 1 — есть застрявшее изменение или
прогон, позеленевший не с первой попытки (124), и задача по нему заведена или
обновлена;
2 — сторож не отработал (площадка не ответила, ответ не разобран).
"""

import argparse
import datetime as dt
import os
import sys
import urllib.error

import checks

REPO = os.environ.get("SHOWCASE_REPO", "ArtVsMark/ArtVsMark")

#: Порог, за которым готовое изменение считается застрявшим. Замер выше:
#: обычное слияние 20–60 секунд, застревания 9,5 минут и 5 часов.
STUCK_MINUTES = 5

#: Обязательная проверка. Имя РАБОТЫ, а не прогона: в защите ветки правило
#: записано именно по нему, и расхождение этих имён однажды сделало несливаемым
#: каждое изменение. Копия имени работы из .github/workflows/pr-check.yml:
#: объявляет его прогон, питон YAML не импортирует; переименуют работу — меняется
#: и эта строка, и `workflows:` в release-hold.yml (071).
REQUIRED = "PR check"

#: Метка «придержано намеренно» — scripts/checks.py::HOLD_LABEL. Придержанное
#: изменение не застряло — оно ждёт человека, и жаловаться на него значит звать
#: его смотреть на то, что он сам и поставил.

#: По этой строке задача находится снова. Одна задача на весь предмет: вторая
#: означала бы, что о том же кричат дважды.
MARKER = "<!-- stuck-prs: не удаляйте, по этой строке задача находится снова -->"

#: Второй предмет сторожа — мигание (124): прогон, позеленевший не с первой
#: попытки. Своя задача и свой маркер: застрявшее изменение и мигающая проверка
#: чинятся по-разному, и одна задача на оба смешала бы адресатов.
FLAKY_MARKER = "<!-- flaky-runs: не удаляйте, по этой строке задача находится снова -->"

#: Окно, за которое спрашиваются успешные прогоны. Сторож ходит дважды в час,
#: и сутки покрывают его с запасом, а задача обновляется, а не множится:
#: тот же прогон в следующем окне — та же строка, не новая находка.
FLAKY_HOURS = 24


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
    if checks.HOLD_LABEL in labels:
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


def flaky(run: dict) -> str | None:
    """Прогон, ставший зелёным не с первой попытки, — находка о мигании (124).

    ПРИЗНАК ОТДАЁТ ПЛОЩАДКА: номер попытки (``run_attempt``) лежит в самом
    прогоне. Зелёное со второго раза — не «прошло», а «прошло, когда
    повторили»: дефект, который в следующий раз может и не пройти. Списать его
    на случайность значило бы перестать его видеть.

    Не находка: первая попытка, неуспешный исход (у красного свой адресат —
    изменение или дежурный по общей ветке), отменённый прогон.
    """
    if run.get("conclusion") != "success":
        return None
    attempt = run.get("run_attempt") or 1
    if attempt <= 1:
        return None
    return (f"«{checks.clip(str(run.get('name', '?')), 40)}» на "
            f"{str(run.get('head_branch', '?'))} — зелёная с попытки {attempt}: "
            f"{run.get('html_url', '')}")


def required_verdict(number: int) -> str | None:
    """Исход обязательной проверки на голове изменения, либо ``None``.

    ``None`` означает «записи с таким именем на голове нет» — ровно случай
    #142, и он ОТЛИЧЁН от «есть и красная»: первое чинится пробуждением
    прогона, второе — правкой кода.

    Считается ПОСЛЕДНЯЯ запись с этим именем: на одной голове их бывает
    несколько, и отменённая среди них не отменяет зелёную.
    """
    head = checks.rest(f"/repos/{REPO}/pulls/{number}")
    runs = checks.rest_list(
        f"/repos/{REPO}/commits/{head['head']['sha']}/check-runs?per_page=100",
        key="check_runs")
    entries = [r for r in runs if r.get("name") == REQUIRED]
    if not entries:
        return None
    # Последняя запись — общая свёртка scripts/checks.py (214).
    return checks.latest_by_name(entries)[0].get("conclusion")


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


def flaky_body(found: list[str], hours: int) -> str:
    """Тело задачи о мигании: что мигнуло и почему это не «прошло»."""
    lines = [
        FLAKY_MARKER,
        "",
        "Прогон **позеленел не с первой попытки**, и это заметил механизм.",
        "",
        "Зелёное со второго раза — не «прошло», а «прошло, когда повторили»:",
        "дефект на месте и в следующий раз может не пройти вовсе (124). Номер",
        "попытки отдаёт площадка, и списывать его на случайность значит",
        "перестать видеть частоту.",
        "",
        "Разбирается причина первой попытки — её лог лежит у прогона, — а не",
        "сам факт повтора.",
        "",
        "Задача ведётся одна: пока открыта, следующие прогоны обновляют её тело.",
        "Закройте её сами — закрытие говорит «я посмотрел».",
        "",
        f"## Мигнуло за последние {hours} ч",
        "",
    ]
    lines += [f"- {line}" for line in found]
    return "\n".join(lines) + "\n"


def reread(sent: str, returned: object) -> str:
    """Опубликованное перечитывается по ответу на запись (188). Пусто — то же.

    Расхождение — предупреждение площадки, а не исход: задача заведена, и
    сторож своё сделал; узнать надо, что текст в ней не тот (051).
    """
    differs = checks.published_differs(sent, returned)
    if not differs:
        return ""
    print(checks.annotate("warning", differs))
    return " — НО ОПУБЛИКОВАНА НЕ ТАК, КАК ОТПРАВЛЕНА"


def sync_issue(found: list[str], minutes: int, dry: bool) -> str:
    """Заводит или обновляет ОДНУ задачу о застрявших. Возвращает, что сделано."""
    return _sync(MARKER, "Изменение готово и не слито дольше порога",
                 body(found, minutes), dry)


def sync_flaky(found: list[str], hours: int, dry: bool) -> str:
    """Заводит или обновляет ОДНУ задачу о мигании. Возвращает, что сделано."""
    return _sync(FLAKY_MARKER, "Прогон позеленел не с первой попытки",
                 flaky_body(found, hours), dry)


def _sync(marker: str, title: str, text: str, dry: bool) -> str:
    """Одна задача на предмет: находится по маркеру, тело перечитывается (188)."""
    issues = checks.rest_list(f"/repos/{REPO}/issues?state=open&per_page=100")
    existing = next((i for i in issues if marker in (i.get("body") or "")), None)
    if dry:
        return f"вхолостую: {'обновил бы' if existing else 'завёл бы'} задачу"
    if existing:
        done = checks.rest(f"/repos/{REPO}/issues/{existing['number']}", "PATCH", {"body": text})
        return f"задача #{existing['number']} обновлена" + reread(text, done)
    made = checks.rest(f"/repos/{REPO}/issues", "POST",
                 {"title": title, "body": text, "labels": ["bug"]})
    return f"задача #{made['number']} заведена" + reread(text, made)


def selftest() -> int:
    """Прогоняет через сторож то, что он обязан отвергнуть и обязан пропустить.

    Набор двусторонний (правило 140), и ложный отказ здесь дороже пропуска:
    сторож, кричащий о нормальном слиянии, приучает не смотреть на его задачу.
    """
    broken: list[str] = []
    now = dt.datetime(2026, 9, 8, 20, 0, tzinfo=dt.UTC)

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

    # ── мигание (124) ──────────────────────────────────────────────────────
    # Соседи признака поимённо: первая попытка, красное, отменённое, попытка
    # не указана вовсе — не находка; зелёное со второй и с третьей — находка.
    flaky_cases = [
        ("зелёная со второй попытки", {"conclusion": "success", "run_attempt": 2}, True),
        ("зелёная с третьей", {"conclusion": "success", "run_attempt": 3}, True),
        ("зелёная с первой", {"conclusion": "success", "run_attempt": 1}, False),
        ("красная со второй — свой адресат", {"conclusion": "failure", "run_attempt": 2}, False),
        ("отменённая", {"conclusion": "cancelled", "run_attempt": 2}, False),
        ("попытка не указана — первая", {"conclusion": "success"}, False),
    ]
    for name, run, expected in flaky_cases:
        got = flaky({"name": REQUIRED, "head_branch": "agent/x", "html_url": "u", **run})
        if bool(got) != expected:
            broken.append(f"мигание, {name}: ожидалось {expected}, вышло {got!r}")
        print(f"  {'найдено ' if got else 'пропущено'} — мигание: {name}")
    said = flaky({"name": REQUIRED, "head_branch": "agent/x", "html_url": "https://r/1",
                  "conclusion": "success", "run_attempt": 2})
    for part in (REQUIRED, "agent/x", "попытки 2", "https://r/1"):
        if part not in (said or ""):
            broken.append(f"мигание: находка не называет {part!r}")
    text = flaky_body([said or ""], FLAKY_HOURS)
    if FLAKY_MARKER not in text or MARKER in text:
        broken.append("мигание: тело задачи несёт не свой маркер — задачи смешаются")

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

    now = dt.datetime.now(dt.UTC)
    try:
        opened = checks.rest_list(f"/repos/{REPO}/pulls?state=open&per_page=100")
        found = []
        for short in opened:
            # Список изменений не несёт mergeable_state — его отдаёт только
            # запрос по одному. Ходим по одному и туда же за проверкой.
            full = checks.rest(f"/repos/{REPO}/pulls/{short['number']}")
            reason = stuck(full, required_verdict(short["number"]), now, args.minutes)
            if reason:
                found.append(reason)
        # Окно по времени создания — фильтр площадки: обход всей истории
        # прогонов страницами ради суток был бы тысячей лишних запросов.
        since = (now - dt.timedelta(hours=FLAKY_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        runs = checks.rest_list(
            f"/repos/{REPO}/actions/runs?status=success&created=>={since}&per_page=100",
            key="workflow_runs")
        blinked = [line for line in map(flaky, runs) if line]
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as refusal:
        # Третий исход: площадка не ответила. Чинит это тот, кто запускает, а не
        # автор изменения, и красным становится прогон, а не находка (039).
        print(checks.annotate("error", f"сторож не отработал: площадка не ответила "
                              f"— {refusal}"), file=sys.stderr)
        return 2

    print(f"мигание: успешных прогонов за {FLAKY_HOURS} ч {len(runs)}, "
          f"не с первой попытки {len(blinked)}")
    if not found and not blinked:
        print(f"застрявших изменений нет: открытых {len(opened)}, "
              f"порог {args.minutes} мин")
        return 0

    if found:
        print(checks.annotate("warning", f"готовы и не слиты: {len(found)}"))
        for line in found:
            print(f"  • {line}")
    if blinked:
        print(checks.annotate("warning", f"позеленели не с первой попытки: {len(blinked)}"))
        for line in blinked:
            print(f"  • {line}")
    try:
        if found:
            print(sync_issue(found, args.minutes, args.dry_run))
        if blinked:
            print(sync_flaky(blinked, FLAKY_HOURS, args.dry_run))
    except (urllib.error.URLError, OSError, ValueError, KeyError) as refusal:
        print(checks.annotate("error", f"находка есть, а адресата нет: задача не "
                              f"заведена — {refusal}"), file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
