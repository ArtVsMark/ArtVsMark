#!/usr/bin/env python3
"""Разбирает неудачное обращение к площадке: состояние это или поломка.

ИНЦИДЕНТ. На [#64] шаг `automerge` упал на первом же обращении:

    GraphQL: API rate limit already exceeded for user ID 86671904.
    ##[error]Process completed with exit code 1.

Гейты изменения были зелёные. Личный токен владельца просто исчерпал часовой
бюджет запросов — то есть отказал **источник**, а не изменение.

ПОЧЕМУ ЭТО ТУПИК, А НЕ ПРОСТО КРАСНОЕ. Красное на `automerge` переводит
изменение в `unstable`, а нестабильному площадка отказывает включить автомерж —
и конвейером, и рукой. Шаг, существующий **ради** включения автомержа, своим
падением делает включение невозможным. Выход остаётся один — новое событие
`pull_request`, хотя чинить в изменении нечего.

КЛАСС ОШИБКИ. Исчерпанный бюджет — состояние, а не поломка изменения. Правило
051: предупреждать о вероятном, запрещать достоверное. В том же прогоне этот
класс уже разобран правильно для другого повода — ненастроенный секрет даёт
`::warning::` и выход, а не отказ. У исчерпанного лимита обработки не было.

ТРИ ИСХОДА, А НЕ ДВА (правило 039):

* ``ok``     — источник ответил, разбирать нечего;
* ``state``  — источник не ответил: бюджет запросов, сеть, пятисотка. Это
  предупреждение и пропуск: утверждать про изменение здесь нечего;
* ``broken`` — источник ответил отказом: нет прав, нет такого изменения,
  испорченный токен. Это красное, и оно называет причину.

ПОЧЕМУ НЕРАЗОБРАННЫЙ ОТКАЗ — КРАСНЫЙ. Соблазн есть обратный: раз красное здесь
заводит в тупик, пусть неизвестное тоже будет предупреждением. Так нельзя.
Молчаливый пропуск на незнакомом отказе означает, что сломанный конвейер
выглядит работающим, а автомерж просто никогда не включается. Поэтому
неизвестное красное — и печатает вывод целиком, не притворяясь диагнозом.

ГРАНИЦЫ. Порядок разбора не косметика: у площадки исчерпанный лимит приезжает
кодом **403**, тем же, что и отказ в правах. Состояние проверяется первым,
иначе «rate limit exceeded» прочтётся как «нет доступа», и предупреждение снова
станет отказом.

Здесь только разбор: печатается одна строка ``исход: причина``, код возврата
всегда 0. Что делать с исходом — решает вызывающий шаг, потому что формулировка
предупреждения принадлежит шагу, а не разбору.

[#64]: https://github.com/ArtVsMark/ArtVsMark/pull/64
"""

from __future__ import annotations

import argparse
import re
import sys

import checks

#: Источник не ответил. Разбирается ПЕРВЫМ: исчерпанный лимит приходит тем же
#: кодом 403, что и отказ в правах, и при обратном порядке прочтётся отказом.
SOURCE_SILENT: tuple[tuple[str, str], ...] = (
    (r"rate limit", "исчерпан бюджет запросов площадки"),
    (r"abuse detection|submitted too quickly", "площадка придержала частые запросы"),
    (r"http 5\d\d|bad gateway|service unavailable|server error",
     "площадка ответила пятисоткой"),
    (r"i/o timeout|context deadline exceeded|client\.timeout|timed out",
     "обращение не уложилось в срок"),
    (r"dial tcp|connection reset|connection refused|tls handshake|"
     r"no such host|could not resolve host|unexpected eof",
     "сеть не донесла запрос"),
)

#: Источник ответил отказом. Причина названа — это красное.
REAL_REFUSAL: tuple[tuple[str, str], ...] = (
    (r"bad credentials|http 401", "токен не принят"),
    (r"resource not accessible|must have admin|not authorized|http 403",
     "токену не хватает прав"),
    (r"could not resolve to a|no pull requests found|http 404",
     "площадка не знает такого изменения"),
)


def classify(code: int, output: str) -> tuple[str, str]:
    """Исход обращения и его причина.

    ``code`` — код возврата ``gh``, ``output`` — его вывод вместе с потоком
    ошибок: причина отказа приезжает именно туда.
    """
    if code == 0:
        return "ok", "источник ответил"

    text = output.lower()
    for pattern, reason in SOURCE_SILENT:
        if re.search(pattern, text):
            return "state", reason
    for pattern, reason in REAL_REFUSAL:
        if re.search(pattern, text):
            return "broken", reason

    first = next((line.strip() for line in output.splitlines() if line.strip()), "")
    return "broken", f"отказ не разобран (код {code}): {checks.clip(first, 200) or 'вывода нет'}"


def selftest() -> int:
    """Прогоняет через разбор то, что он обязан отнести к каждому из трёх исходов.

    Правило 140, и обе его стороны. Набор из одних «обязан отвергнуть» не видит
    ложного отказа, а он здесь дороже пропуска вдвойне: ложное красное на этом
    шаге не просто шумит, а запирает изменение в `unstable`.

    Тексты — настоящие, как их печатает ``gh``, а не пересказ: разбор ищет
    подстроку, и пересказанный образец подтвердил бы только сам себя.
    """
    cases = (
        ("успех", 0, "автомерж включён", "ok"),
        ("бюджет запросов исчерпан — тот самый отказ с #64", 1,
         "GraphQL: API rate limit already exceeded for user ID 86671904.", "state"),
        ("бюджет запросов, форма REST", 1,
         "HTTP 403: API rate limit exceeded for user ID 86671904. "
         "(https://api.github.com/repos/ArtVsMark/ArtVsMark/pulls/64)", "state"),
        ("вторичный лимит", 1,
         "HTTP 403: You have exceeded a secondary rate limit.", "state"),
        ("пятисотка", 1, "HTTP 502: Bad gateway (https://api.github.com/graphql)", "state"),
        ("сеть не донесла", 1,
         'Get "https://api.github.com/": dial tcp: lookup api.github.com: no such host', "state"),
        ("срок вышел", 1, "context deadline exceeded (Client.Timeout exceeded)", "state"),
        ("токен испорчен", 1, "HTTP 401: Bad credentials (https://api.github.com/graphql)", "broken"),
        ("прав не хватает", 1,
         "HTTP 403: Resource not accessible by integration "
         "(https://api.github.com/repos/ArtVsMark/ArtVsMark/pulls/64)", "broken"),
        ("нет такого изменения", 1,
         "GraphQL: Could not resolve to a PullRequest with the number of 999.", "broken"),
        ("отказ не разобран", 1, "something went sideways", "broken"),
        ("отказ без вывода", 1, "", "broken"),
    )

    broken: list[str] = []
    for name, code, output, expected in cases:
        verdict, reason = classify(code, output)
        if verdict != expected:
            broken.append(f"{name}: ожидалось {expected}, вышло {verdict} — {reason}")
        print(f"  {verdict:<6} — {name}")

    # Ловушка порядка проверяется отдельно и по имени: «403 + rate limit» обязан
    # быть состоянием, а не отказом в правах. Именно этот случай ломается первым,
    # если списки поменять местами, — и ломается молча.
    verdict, _ = classify(1, "HTTP 403: API rate limit exceeded")
    if verdict != "state":
        broken.append("403 с лимитом прочитан отказом в правах — списки переставлены местами")

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: разбор отличает состояние от поломки")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--code", type=int, default=0, help="код возврата gh")
    parser.add_argument("--selftest", action="store_true", help="прогнать самопроверку")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    verdict, reason = classify(args.code, sys.stdin.read())
    print(f"{verdict}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
