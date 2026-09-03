#!/usr/bin/env python3
"""Стоп-кран снимает механизм, когда снимать его больше не о чем.

ЗАЧЕМ. Изменение открывает прогон `open-pr` и ставит `hold`: автомерж здесь по
умолчанию, а тело в момент открытия ещё пустое. Дальше окно заполняет тело и
снимает метку — и вот этот последний шаг держался ПАМЯТЬЮ. 28 августа он подвёл
на изменении, которое чинило красную общую ветку: изменение стояло готовым,
проверки зелёные, и ждало только того, что кто-то вспомнит.

Шаг, который работает, пока кто-то не забудет, механизмом не является.

СИГНАЛ ГОТОВНОСТИ — ОТСУТСТВИЕ МАРКЕРА В ТЕЛЕ, а не зелёные проверки сами по
себе. Причина в том, что зелёное говорит «сломать не сломали», а не «работа
доделана»: тело изменения — часть работы, и пустое тело при зелёных проверках
это готовность только по форме.

`open-pr` кладёт в тело `<!-- hold: тело не заполнено -->`. Окно, заполняя тело,
пишет его целиком — маркер уходит вместе со старым текстом, и отдельного жеста
не нужно. Тот же жест остаётся способом ПРИДЕРЖАТЬ: строка `<!-- hold: причина -->`
в теле держит метку сколько угодно долго, и причина при этом читается, а не
хранится в чужой голове.

ПОЧЕМУ МЕХАНИЗМ НЕ СПОРИТ С ЧЕЛОВЕКОМ. Вернуть `hold` рукой без маркера значило
бы объявить войну: следующий прогон снял бы её снова. Поэтому решение принимается
по ТЕЛУ, которое правит человек, а не по метке, которую правят обе стороны.

ОШИБАЕТСЯ В БЕЗОПАСНУЮ СТОРОНУ. Не «слил недоделанное», а «не снял с готового»:
маркер на месте — держим, проверки не зелёные — держим, метки нет — не трогаем.

Исходы: 0 — сделано или делать нечего; 1 — решение не применено; 2 — не отработал.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

import checks

#: Маркер удержания. Всё, что после двоеточия, — причина, и она читается.
HOLD_MARKER = re.compile(r"<!--\s*hold:\s*(.*?)\s*-->", re.S)

#: Метка конвейера, которую снимает этот механизм. Метки содержания он не
#: трогает: они принадлежат автору (правило 064).
HOLD_LABEL = "hold"


#: Исполнитель, у которого нет окна. Имя то же, что в .github/authors.txt, и
#: смысл тот же: коммит составил прогон площадки, а не человек и не окно.
PIPELINE_AUTHOR = "github-actions[bot]"

#: Имя трейлера соавторства. Разбор — общий, из scripts/checks.py: хвостовой
#: блок, а не любая строка (правило 156).
COAUTHOR = "co-authored-by"


def marker_needed(commit_body: str) -> bool:
    """Нужен ли маркер «тело не заполнено» изменению с таким телом коммита.

    Маркер — обещание, что тело допишут. У ветки, которую ведёт прогон, тела
    дописывать некому: суточную пересборку никто не читает и не редактирует,
    и маркер там означал бы стоп-кран навсегда.

    Признак — не имя ветки, а ФАКТ о коммите: его составил прогон площадки,
    и он сам назвал себя трейлером. Имя ветки сюда не годится: переключатель
    по имени отменяет операцию молча, стоит префиксу разойтись (правило 147),
    а здесь цена молчания — либо вставшая пересборка, либо изменение, уехавшее
    без тела.

    ЗАЧЕМ ЭТО ПОНАДОБИЛОСЬ. До 31 августа изменение для ветки пересборки
    открывали ДВА механизма: `metrics.yml` — сам, `open-pr.yml` — по пушу той
    же ветки. Работало это на удаче: `metrics` успевал первым. Когда 29 августа
    не успел, `open-pr` попытался открыть изменение для уже слитой ветки и
    покраснел («No commits between main and chore/metrics», #98). Обратный
    порядок был не лучше, а хуже и тише: открой `open-pr` первым — пересборка
    встала бы с `hold`, которого некому снять.
    """
    named = checks.trailers(commit_body or "").get(COAUTHOR, [])
    pipeline = [name for name in named if PIPELINE_AUTHOR in name]
    # Маркер не нужен, только когда прогон — ЕДИНСТВЕННЫЙ исполнитель. Стоит
    # рядом оказаться окну, и тело допишет оно: пропустить маркер здесь значило
    # бы пустить в общую ветку изменение без тела, а это ошибка в опасную
    # сторону, в отличие от лишнего маркера.
    return not (pipeline and len(pipeline) == len(named))


#: Исходы прогона, которые НЕ считаются провалом. Отменённое не есть ошибка
#: (правило 078), пропущенное — тем более: у витрины прогон от метки конвейера
#: пропускается намеренно. Но и успехом они не являются, поэтому одного
#: отсутствия провалов для «зелено» мало — нужен хотя бы один настоящий успех.
NOT_A_FAILURE = frozenset({"SUCCESS", "SKIPPED", "CANCELLED", "NEUTRAL", ""})


def _when(run: dict) -> str:
    """Время прогона для сравнения свежести. Оба написания — своё и площадки."""
    for key in ("completedAt", "completed_at", "startedAt", "started_at"):
        value = run.get(key)
        if value:
            return str(value)
    return ""


def _latest_per_check(rollup: list[dict]) -> list[dict]:
    """По одному прогону на имя проверки — самый свежий.

    Ответ площадки перечисляет ВСЕ прогоны на коммите, включая те, что уже
    переигранны. Устаревший провал в этом списке означал бы, что стоп-кран
    держится вечно: на #106 первый `PR check` упал на неполной классификации,
    метку зоны поставили, второй прогон стал зелёным — а провалившийся никуда
    из списка не делся.

    Площадка в защите ветки считает так же: у проверки с одним именем
    учитывается последняя. Здесь это повторено, а не изобретено.

    Порядок ввода не важен: сравнивается время, а при его отсутствии
    побеждает более поздний в списке — тот же порядок, в каком его отдаёт
    площадка.
    """
    latest: dict[object, dict] = {}
    for position, run in enumerate(rollup):
        name = (run.get("name") or run.get("context") or "").strip()
        # Безымянная запись не схлопывается ни с чем: имя здесь ключ, и его
        # отсутствие означает «неизвестно, та же это проверка или другая».
        # Схлопнуть их вместе значило бы выбросить чужой исход.
        key: object = name or (position, None)
        known = latest.get(key)
        if known is None or _when(run) >= _when(known):
            latest[key] = run
    return list(latest.values())


def checks_state(rollup: list[dict], ignore: frozenset[str] = frozenset()) -> str:
    """Состояние проверок изменения: ``success`` · ``pending`` · ``failure``.

    Спрашивается там, где событие говорит про ТЕЛО, а не про прогон: у
    `pull_request_target: edited` исхода проверок в событии нет вовсе, и взять
    его можно только у площадки.

    ТРИ ИСХОДА, А НЕ ДВА (правило 039). «Не провалено» и «зелено» — разные
    вещи: на первом head #103 все прогоны оказались отменены, провалов не было
    ни одного, и решение «зелено» слило бы изменение, проверка которого не
    отработала вовсе. Поэтому успех требует хотя бы одного настоящего
    ``SUCCESS``.

    Незавершённое перевешивает всё: пока хоть один прогон бежит, ответ
    ``pending`` — механизм ошибается в безопасную сторону, оставляя стоп-кран.

    СЕБЯ СПРАШИВАЮЩИЙ НЕ СЧИТАЕТ, И БЕЗ ЭТОГО МЕХАНИЗМ НЕ РАБОТАЛ ВОВСЕ.
    Ответ площадки перечисляет ВСЕ проверки изменения, включая прогон, который
    этот вопрос и задаёт: спрашивая о себе, он всегда видит себя
    незавершённым — ``pending``, стоп-кран остаётся, и так каждый раз. Замер на
    #106: прогон от редактирования тела отработал «успешно» и не снял ничего.
    Имена, которые надо пропустить, передаёт вызывающий: скрипт не знает, из
    какого прогона его позвали.
    """
    if not rollup:
        # Пустой список — не «зелено», а «спросить не у кого». Автомерж читает
        # такое как «не стартовало», и мы читаем так же.
        return "pending"
    passed = False
    for run in _latest_per_check(rollup):
        name = (run.get("name") or run.get("context") or "").strip()
        if name in ignore:
            continue
        status = (run.get("status") or "").upper()
        conclusion = (run.get("conclusion") or "").upper()
        state = (run.get("state") or "").upper()
        if status and status != "COMPLETED":
            return "pending"
        if state and state in {"PENDING", "EXPECTED"}:
            return "pending"
        verdict = conclusion or state
        if verdict not in NOT_A_FAILURE:
            return "failure"
        if verdict == "SUCCESS":
            passed = True
    return "success" if passed else "pending"


def decide(body: str, labels: set[str], checks_ok: bool) -> tuple[str, str]:
    """Что сделать со стоп-краном: ``release`` · ``keep`` · ``nothing``.

    Порядок проверок — не вкусовой. «Метки нет» стоит первым, иначе механизм
    рассуждал бы о состоянии, которого не касается. Маркер стоит выше проверок,
    потому что придержать намеренно можно и на зелёном: зелёное говорит «не
    сломали», а не «доделали».
    """
    if HOLD_LABEL not in labels:
        return "nothing", "стоп-крана нет — трогать нечего"
    if not (body or "").strip():
        # Пустое тело — не «заполнено», а «нечего читать». Механизм ошибается в
        # безопасную сторону: не «слил недоделанное», а «оставил ждать».
        return "keep", "тело пустое — читать нечего"
    held = HOLD_MARKER.search(body)
    if held:
        why = held.group(1).strip() or "причина не названа"
        return "keep", f"тело держит стоп-кран: {why}"
    if not checks_ok:
        return "keep", "проверки ещё не зелёные"
    return "release", "тело заполнено, проверки зелёные — держать больше нечем"


def selftest() -> int:
    """Прогоняет через решение то, что оно обязано отпустить и обязано удержать.

    Набор двусторонний (правило 140), и вторая сторона здесь дороже первой:
    ложное снятие сливает недоделанное, а ложное удержание всего лишь оставляет
    изменение ждать человека — то есть возвращает состояние, которое было до
    этого механизма.
    """
    FILLED = "## Что сделано\n\nПодробное тело изменения."
    FRESH = FILLED + "\n\n<!-- hold: тело не заполнено -->"
    cases = [
        ("тело заполнено, проверки зелёные", FILLED, {"hold", "bug"}, True, "release"),
        ("тело ещё от прогона", FRESH, {"hold", "bug"}, True, "keep"),
        ("придержано намеренно, с причиной",
         FILLED + "\n<!-- hold: ждём слова владельца по политике -->", {"hold"}, True, "keep"),
        ("придержано без причины", FILLED + "\n<!-- hold: -->", {"hold"}, True, "keep"),
        ("проверки ещё не зелёные", FILLED, {"hold", "bug"}, False, "keep"),
        ("стоп-крана нет вовсе", FILLED, {"bug"}, True, "nothing"),
        ("стоп-крана нет, но и тело пустое", FRESH, {"bug"}, False, "nothing"),
        ("тело пустой строкой", "", {"hold"}, True, "keep"),
        ("тело из одних пробелов", "   \n  ", {"hold"}, True, "keep"),
        ("маркер в несколько строк",
         FILLED + "\n<!-- hold:\n  причина в две строки\n-->", {"hold"}, True, "keep"),
    ]
    broken: list[str] = []
    for name, body, labels, ok, expected in cases:
        got, why = decide(body, labels, ok)
        if got != expected:
            broken.append(f"{name}: ожидалось {expected}, вышло {got} — {why}")
        print(f"  {got:<8} — {name}")

    # Отказ обязан называть предмет: удержание без причины ничем не отличается
    # от удержания по забывчивости, если причину не напечатать (правило 083).
    _, why = decide(FILLED + "\n<!-- hold: спорная политика -->", {"hold"}, True)
    if "спорная политика" not in why:
        broken.append("удержание не называет причину, записанную в теле")

    # ── состояние проверок, когда событие про тело, а не про прогон ────────
    # Три исхода, и каждый прогоняется (правило 145). Обе ошибки названы:
    # ложное «зелено» сливает изменение, чья проверка не отработала; ложное
    # «ждём» оставляет стоп-кран, и это дешевле.
    #
    # У ПОДДЕЛКИ ЗДЕСЬ ЕСТЬ ИСТОЧНИК, И ОН СНЯТ С ЖИВОЙ СТОРОНЫ (правило 170).
    # Формы ДВЕ, и обе настоящие: `gh pr view --json statusCheckRollup` отдаёт
    # GraphQL-форму в ВЕРХНЕМ регистре (`"conclusion": "SUCCESS"`), а REST
    # `/commits/{sha}/check-runs` — ту же запись в НИЖНЕМ
    # (`"conclusion": "success"`), снято на коммите 6a8be4e витрины:
    #     name='build' status='completed' conclusion='success'
    # Регистр здесь нормализуется, но до 3 сентября набор гонялся ТОЛЬКО на
    # верхней форме: зелёное на ней доказывало согласованность кода с
    # представлением автора о площадке, а не с площадкой.
    OK = {"status": "COMPLETED", "conclusion": "SUCCESS"}
    state_cases = [
        ("успех один", [OK], "success"),
        ("успех рядом с отменённым", [OK, {"status": "COMPLETED", "conclusion": "CANCELLED"}], "success"),
        ("успех рядом с пропущенным", [OK, {"status": "COMPLETED", "conclusion": "SKIPPED"}], "success"),
        ("одни отменённые — проверка не отработала",
         [{"status": "COMPLETED", "conclusion": "CANCELLED"},
          {"status": "COMPLETED", "conclusion": "SKIPPED"}], "pending"),
        ("прогон ещё бежит", [OK, {"status": "IN_PROGRESS", "conclusion": None}], "pending"),
        ("прогон в очереди", [{"status": "QUEUED", "conclusion": None}], "pending"),
        ("провал рядом с успехом", [OK, {"status": "COMPLETED", "conclusion": "FAILURE"}], "failure"),
        ("провал по времени", [{"status": "COMPLETED", "conclusion": "TIMED_OUT"}], "failure"),
        ("проверок нет вовсе — спросить не у кого", [], "pending"),
        ("старая форма: контекст со state", [{"state": "SUCCESS"}], "success"),
        ("старая форма: контекст ждёт", [{"state": "PENDING"}], "pending"),
        ("старая форма: контекст провален", [{"state": "FAILURE"}], "failure"),
        # Форма REST, снятая с живого ответа: тот же исход в нижнем регистре.
        ("ответ REST: успех в нижнем регистре",
         [{"status": "completed", "conclusion": "success"}], "success"),
        ("ответ REST: провал в нижнем регистре",
         [{"status": "completed", "conclusion": "failure"}], "failure"),
        ("ответ REST: ещё бежит",
         [{"status": "in_progress", "conclusion": None}], "pending"),
    ]
    for name, rollup, expected in state_cases:
        got = checks_state(rollup)
        if got != expected:
            broken.append(f"состояние проверок, {name}: ожидалось {expected}, вышло {got}")
        print(f"  {got:<8} — состояние проверок: {name}")

    # Свежесть: у проверки с одним именем считается последняя, как и в защите
    # ветки. Устаревший провал иначе держал бы стоп-кран вечно.
    def run(name, concl, when, status="COMPLETED"):
        return {"name": name, "status": status, "conclusion": concl, "completedAt": when}

    fresh_cases = [
        ("переигранный провал перекрыт успехом",
         [run("PR check", "FAILURE", "09:23"), run("PR check", "SUCCESS", "09:25")], "success"),
        ("свежий провал после успеха",
         [run("PR check", "SUCCESS", "09:20"), run("PR check", "FAILURE", "09:26")], "failure"),
        ("порядок в списке не решает — решает время",
         [run("PR check", "SUCCESS", "09:25"), run("PR check", "FAILURE", "09:23")], "success"),
        ("времени нет — побеждает последний в списке",
         [{"name": "PR check", "status": "COMPLETED", "conclusion": "FAILURE"},
          {"name": "PR check", "status": "COMPLETED", "conclusion": "SUCCESS"}], "success"),
        ("разные проверки не схлопываются",
         [run("PR check", "SUCCESS", "09:25"), run("другая", "FAILURE", "09:20")], "failure"),
        ("свежий перезапуск ещё бежит",
         [run("PR check", "SUCCESS", "09:20"),
          run("PR check", None, "09:26", status="IN_PROGRESS")], "pending"),
    ]
    for name, rollup, expected in fresh_cases:
        got = checks_state(rollup)
        if got != expected:
            broken.append(f"свежесть проверок, {name}: ожидалось {expected}, вышло {got}")
        print(f"  {got:<8} — свежесть проверок: {name}")

    # Спрашивающий не считает себя. Без этого механизм не работал вовсе:
    # прогон видел себя незавершённым и держал стоп-кран каждый раз.
    SELF = {"name": "release-hold", "status": "IN_PROGRESS", "conclusion": None}
    self_cases = [
        ("свой прогон отсеян — остальное зелено", [SELF, dict(OK, name="PR check")],
         frozenset({"release-hold"}), "success"),
        ("свой прогон НЕ отсеян — вечное ожидание", [SELF, dict(OK, name="PR check")],
         frozenset(), "pending"),
        ("отсев не прячет чужой провал",
         [SELF, {"name": "PR check", "status": "COMPLETED", "conclusion": "FAILURE"}],
         frozenset({"release-hold"}), "failure"),
        ("отсев не прячет чужое ожидание",
         [SELF, {"name": "PR check", "status": "QUEUED", "conclusion": None}],
         frozenset({"release-hold"}), "pending"),
        ("после отсева не осталось ничего — спросить не у кого",
         [SELF], frozenset({"release-hold"}), "pending"),
        ("старая форма: имя лежит в context",
         [{"context": "release-hold", "state": "PENDING"}, {"context": "ci", "state": "SUCCESS"}],
         frozenset({"release-hold"}), "success"),
    ]
    for name, rollup, ignore, expected in self_cases:
        got = checks_state(rollup, ignore)
        if got != expected:
            broken.append(f"отсев спрашивающего, {name}: ожидалось {expected}, вышло {got}")
        print(f"  {got:<8} — отсев спрашивающего: {name}")

    # Решение о стоп-кране обязано принимать этот ответ буквально: «pending» и
    # «failure» держат, и только «success» отпускает.
    BODY = "тело заполнено"
    for state, want in (("success", "release"), ("pending", "keep"), ("failure", "keep")):
        verdict, _ = decide(BODY, {"hold"}, state == "success")
        if verdict != want:
            broken.append(f"стоп-кран при проверках «{state}»: ожидалось {want}, вышло {verdict}")
        print(f"  {verdict:<8} — стоп-кран при проверках «{state}»")

    # ── кому нужен маркер «тело не заполнено» ──────────────────────────────
    # Обе стороны, и обе ошибки названы: лишний маркер останавливает
    # пересборку навсегда, недостающий пускает изменение без тела.
    BOT = "Co-authored-by: github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>"
    WINDOW = "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
    marker_cases = [
        ("коммит окна — тело допишут", f"Разбор правки.\n\n{WINDOW}", True),
        ("коммит прогона — дописывать некому", f"Пересобранные числа.\n\n{BOT}", False),
        ("тело без трейлеров вовсе", "Просто сообщение.", True),
        ("тело пустое", "", True),
        ("оба трейлера — окно тоже участвовало, тело допишут",
         f"Правка.\n\n{WINDOW}\n{BOT}", True),
        ("имя прогона в прозе, а не трейлером",
         "объясняем, почему github-actions[bot] дописывается площадкой", True),
    ]
    for name, body, expected in marker_cases:
        got = marker_needed(body)
        if got is not expected:
            broken.append(f"маркер, {name}: ожидалось "
                          f"{'нужен' if expected else 'не нужен'}, вышло наоборот")
        print(f"  {'нужен    ' if got else 'не нужен '} — маркер: {name}")

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: стоп-кран снимается только с доделанного")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--body-file", help="файл с телом изменения")
    parser.add_argument("--labels", default="", help="метки через запятую")
    parser.add_argument("--checks", default="", help="исход обязательных проверок")
    parser.add_argument("--ignore-check", action="append", default=[],
                        help="имя проверки, которую не спрашивать: прогон, "
                             "задающий вопрос, всегда видит себя незавершённым")
    parser.add_argument("--checks-state", action="store_true",
                        help="состояние проверок изменения: ответ площадки "
                             "(statusCheckRollup) читается из stdin, вердикт "
                             "печатается словом")
    parser.add_argument("--marker-needed", action="store_true",
                        help="нужен ли маркер «тело не заполнено»: тело коммита "
                             "читается из stdin, ответ печатается словом")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if args.checks_state:
        try:
            rollup = json.loads(sys.stdin.read() or "[]")
        except ValueError as e:
            print(checks.annotate("error", f"не отработал: ответ площадки не разобран — {e}"),
                  file=sys.stderr)
            return 2
        if not isinstance(rollup, list):
            print(checks.annotate("error", "не отработал: ожидался список проверок"),
                  file=sys.stderr)
            return 2
        print(checks_state(rollup, frozenset(args.ignore_check)))
        return 0
    if args.marker_needed:
        # Ответ печатается словом, а не кодом возврата: коды здесь заняты
        # смыслом (0 — сделано, 1 — не применено, 2 — не отработал), и
        # «маркер не нужен» это не отказ (правило 039).
        print("yes" if marker_needed(sys.stdin.read()) else "no")
        return 0
    if not args.body_file:
        print(checks.annotate("error", "не отработал: не задан --body-file"),
              file=sys.stderr)
        return 2
    try:
        body = open(args.body_file, encoding="utf-8").read()
    except OSError as e:
        print(checks.annotate("error", f"не отработал: тело не прочитано — {e}"),
              file=sys.stderr)
        return 2

    labels = {name.strip() for name in args.labels.split(",") if name.strip()}
    verdict, why = decide(body, labels, args.checks.strip().lower() == "success")
    print(f"{verdict}: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
