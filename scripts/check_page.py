#!/usr/bin/env python3
"""Запреты витрины, которые можно проверить, — проверяются, а не читаются.

ЗАЧЕМ. В своде витрины восемь критических запретов, и до сих пор четыре из них
держались гейтами, а четыре — чтением. Замер по всем действующим вердиктам
(HISTORY.md § «Чем держатся вердикты») показал, что это не исключение, а норма:
из 72 вердиктов у 23 не бежит ничего, у 37 механизм бежит, но нарушение проходит
молча. Правило, которое можно сделать механическим, не оставляют в своде — и
этот скрипт снимает три запрета из четырёх незакрытых.

ЧЕТВЁРТЫЙ ОСТАЁТСЯ НЕПРОВЕРЯЕМЫМ, И ЭТО НАЗВАНО: «не утверждать на витрине то,
чего читатель не может проверить» и «не везти в одном PR несколько тем» машине
не даются — судить о проверяемости утверждения и о единстве темы нечем
(правило 057). Они остаются в своде именно как названные, а не забытые.

ЧТО ПРОВЕРЯЕТСЯ И ПОЧЕМУ ИМЕННО ТАК:

* ``<details>`` на витрине. Раздел под ним четыре обзора подряд назвали
  «обещанием без продолжения»: там, где страницу читают текстом, он схлопывается
  в заголовок без содержимого. Проверяется дословным вхождением — тег либо есть,
  либо нет, гадать не о чем;

* изображения только свои и значки. Решение владельца: гифки и картинки самого
  проекта на витрину не берутся. Проверяется источником: всё, что не ``assets/``
  и не объявленный хост значков, — находка. Список хостов узкий намеренно, его
  расширяют осознанно;

* ссылки на номерные задачи в объясняющем тексте. Витрина держится в пределах
  страницы: номер задачи ничего не говорит постороннему читателю и устаревает
  вместе с задачей. Ссылка на трекер целиком при этом законна — запрещён номер,
  а не адрес;

* язык артефактов. Витрина по-английски с русским разделом в конце, служебное
  по-русски. Порог доли кириллицы — 50%, и он не выдуман: замер на 2026-08-27
  дал 6% у витрины и 70–94% у служебных файлов. Нарушение выглядит как файл,
  написанный не на том языке, то есть даёт значение у другого края, а не рядом
  с порогом.

Исходы: 0 — чисто; 1 — есть находки; 2 — проверка не отработала.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Витрина. Единственный файл, который читает посторонний.
PAGE = "README.md"

#: Служебные документы: их читают владелец и окно, и они по-русски.
SERVICE = ("HISTORY.md", "CLAUDE.md", ".rules/README.md", ".rules/roles.md")

#: Заголовок русского пересказа. Его отсутствие — не оформление: без него
#: страница перестаёт быть двуязычной, а это обещание свода.
RUSSIAN_SECTION = "По-русски"

#: Откуда витрине можно брать изображения. Свои — из `assets/`, их рисует
#: сборка. Остальное — значки объявленных хостов.
ALLOWED_IMAGE_HOSTS = ("img.shields.io", "raw.githubusercontent.com")

#: Ссылка на НОМЕРНУЮ задачу или изменение. Адрес трекера целиком не запрещён.
NUMBERED_TRACKER = re.compile(r"github\.com/[\w.-]+/[\w.-]+/(?:issues|pull)/\d+")

#: Источники изображений: и `src`, и `srcset` — второй легко забыть, а картинка
#: приезжает через него ровно так же.
IMAGE_SRC = re.compile(r'(?:src|srcset)="([^"]+)"')

#: Порог доли кириллицы. Обоснование — в докстроке: замер развёл языки на 6% и
#: 70–94%, и порог стоит между ними, а не «на глаз».
CYRILLIC_SHARE = 50


def cyrillic_share(text: str) -> int:
    """Доля кириллицы среди букв, в процентах."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0
    cyrillic = sum(1 for c in letters if "а" <= c.lower() <= "я" or c.lower() == "ё")
    return cyrillic * 100 // len(letters)


def audit_page(page: str) -> list[str]:
    """Находки на витрине: спойлер, чужие картинки, номерные задачи, язык."""
    found: list[str] = []

    if "<details" in page:
        found.append("на витрине <details>: там, где страницу читают текстом, "
                     "он схлопывается в заголовок без содержимого")

    if ".gif" in page.lower():
        found.append("на витрине гифка: решение владельца — гифки и картинки "
                     "самого проекта на витрину не берутся")

    for src in IMAGE_SRC.findall(page):
        first = src.split()[0].split("?")[0]
        if first.startswith(("./assets/", "assets/")):
            continue
        if any(host in first for host in ALLOWED_IMAGE_HOSTS):
            continue
        found.append(f"изображение не из assets/ и не объявленный хост значков: {first}")

    for link in sorted(set(NUMBERED_TRACKER.findall(page))):
        found.append(f"ссылка на номерную задачу в тексте витрины: {link} — "
                     "номер ничего не говорит постороннему и устаревает вместе с задачей")

    if RUSSIAN_SECTION not in page:
        found.append(f"на витрине нет раздела «{RUSSIAN_SECTION}»: двуязычие — "
                     "обещание свода, а не оформление")
    elif cyrillic_share(page) >= CYRILLIC_SHARE:
        found.append(f"витрина написана по-русски ({cyrillic_share(page)}% кириллицы): "
                     "её читает англоязычный посетитель профиля")

    return found


def audit_service(name: str, text: str) -> list[str]:
    """Находки в служебном документе: он по-русски, его читают владелец и окно."""
    share = cyrillic_share(text)
    if share < CYRILLIC_SHARE:
        return [f"{name}: служебный документ не по-русски ({share}% кириллицы) — "
                "его читают владелец и окно, а не посетитель профиля"]
    return []


def selftest() -> int:
    """Прогоняет через гейт то, что он обязан отвергнуть и обязан пропустить.

    Набор двусторонний (правило 140). Ложный отказ здесь дороже пропуска: гейт,
    ругающийся на живую витрину, начинают обходить, а обойдённый гейт не держит
    уже ничего.
    """
    ok_page = ('# Профиль\n<img src="./assets/header-dark.svg?v=1" alt="шапка">\n'
               '<img src="https://img.shields.io/badge/x-y-1F6FEB" alt="значок">\n'
               "Text in English about the projects.\n"
               "[tracker](https://github.com/ArtVsMark/ArtVsMark/issues)\n"
               "### По-русски\nКраткий пересказ страницы.\n")
    cases = [
        ("витрина как есть", ok_page, False),
        ("спойлер вернулся", ok_page + "<details><summary>x</summary>y</details>", True),
        ("гифка", ok_page + '<img src="./assets/demo.gif" alt="демо">', True),
        ("картинка с чужого хоста", ok_page + '<img src="https://example.com/a.png" alt="a">', True),
        ("картинка через srcset", ok_page + '<source srcset="https://example.com/b.png">', True),
        ("номерная задача в тексте",
         ok_page + "см. https://github.com/ArtVsMark/ArtVsMark/issues/42", True),
        ("номерное изменение в тексте",
         ok_page + "см. https://github.com/ArtVsMark/ArtVsMark/pull/7", True),
        ("адрес трекера целиком — законен", ok_page, False),
        ("русский раздел пропал", ok_page.replace("### По-русски", "### In Russian"), True),
        ("витрина написана по-русски",
         '<img src="./assets/h.svg" alt="ш">\n### По-русски\nВся страница по-русски, целиком и полностью.', True),
    ]
    broken: list[str] = []
    for name, page, must_reject in cases:
        found = audit_page(page)
        if bool(found) is not must_reject:
            broken.append(f"{name}: ожидалось {'отказ' if must_reject else 'пропуск'}, "
                          f"вышло наоборот — {found}")
        print(f"  {'отвергнут' if found else 'пропущен '} — {name}")

    service = [
        ("служебный по-русски", "Журнал. Что сломалось и чем закрыли, подробно и по делу.", False),
        ("служебный по-английски", "The changelog of what broke and how it was fixed.", True),
    ]
    for name, text, must_reject in service:
        found = audit_service("x.md", text)
        if bool(found) is not must_reject:
            broken.append(f"{name}: ожидалось {'отказ' if must_reject else 'пропуск'}, вышло наоборот")
        print(f"  {'отвергнут' if found else 'пропущен '} — {name}")

    # Отказ обязан НАЗЫВАТЬ предмет: находка без имени — это отказ, по которому
    # нечего чинить (правило 083).
    named = audit_page(ok_page + '<img src="https://example.com/a.png" alt="a">')
    if not any("example.com/a.png" in line for line in named):
        broken.append("отказ на чужой картинке не называет её адрес")

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: гейт отвергает то, что обязан, и называет предмет")
    return 0


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()

    try:
        found = audit_page((ROOT / PAGE).read_text(encoding="utf-8"))
        for name in SERVICE:
            found += audit_service(name, (ROOT / name).read_text(encoding="utf-8"))
    except OSError as e:
        print(f"проверка не отработала: {e}", file=sys.stderr)
        return 2

    if found:
        print("запреты витрины нарушены:", file=sys.stderr)
        for line in found:
            print(f"  • {line}", file=sys.stderr)
        print("\n  Эти запреты держались чтением свода и теперь держатся здесь."
              "\n  Если запрет устарел — меняют свод и этот гейт вместе, а не обходят.",
              file=sys.stderr)
        return 1

    print(f"запреты витрины соблюдены: {PAGE} и {len(SERVICE)} служебных документа")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
