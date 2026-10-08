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
  с порогом;

* ссылки из витрины в её же производные (089). Картинка сборки — законная
  цель ``src``: так производное показывают. Ссылка на него — ``href``,
  разметочная ссылка или сноска — уводит читателя на копию вместо источника.
  Производные перечислимы: ветки, которые сборка пишет сама. Обратные ссылки
  проектов сюда — предмет на чужой стороне, и он не наш;

* объём прозы витрины и свода (023, 029). Предел в СЛОВАХ, а не в строках:
  переливка абзацев число не меняет. Считается то, что читают глазами, —
  без тегов, комментариев-маркеров и адресов ссылок. Что именно оставить на
  странице и что унести по ссылке, гейт не судит: это суждение об аудитории
  (182), он держит только бюджет.

Исходы: 0 — чисто; 1 — есть находки; 2 — проверка не отработала.
"""

import pathlib
import re
import sys

import checks

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

#: ФОРМЫ ПРЕДМЕТОВ СТРАНИЦЫ ВЗЯТЫ ЗАМЕРОМ И ЧИТАЮТСЯ ВСЕ (правило 206). Замер 29
#: сентября по README.md: `<img src="` — 18, `<source srcset="` — 36; markdown-
#: картинок `![](…)`, картинок по сноске `![][ref]`, атрибутов в одинарных
#: кавычках, `<details>` в любом регистре и коротких ссылок `#N` — ноль. Прежде
#: гейт читал две формы из семи — ровно те, что стоят сегодня, — и
#: `![demo](https://github.com/user-attachments/…)` проходил его целиком.

#: Ссылка на НОМЕРНУЮ задачу или изменение — полным адресом или коротко `#N`:
#: площадка превращает `#42` на странице профиля в ссылку на задачу 42 этого же
#: репозитория. Адрес трекера целиком не запрещён.
NUMBERED_TRACKER = re.compile(r"github\.com/[\w.-]+/[\w.-]+/(?:issues|pull)/\d+"
                              r"|(?<![&\w/#])#\d+\b")

#: Спойлер — в любом регистре: HTML его не различает.
DETAILS = re.compile(r"<details\b", re.I)

#: Источники изображений: и `src`, и `srcset` — второй легко забыть, а картинка
#: приезжает через него ровно так же. Кавычки любые, пробелы у `=` допустимы.
IMAGE_SRC = re.compile(r"""(?:src|srcset)\s*=\s*["']([^"']+)["']""", re.I)

#: Картинка разметкой Markdown: `![подпись](адрес)` и по сноске `![подпись][метка]`
#: с определением `[метка]: адрес` ниже.
MD_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)")
MD_IMAGE_REF = re.compile(r"!\[[^\]]*\]\[([^\]]*)\]")
MD_REF_DEF = re.compile(r"^[ \t]*\[([^\]]+)\]:\s*<?(\S+?)>?(?:\s|$)", re.M)

#: Картинка на странице и её атрибуты. Разбирается тег целиком, а не отдельные
#: атрибуты по всему тексту: у соседних картинок они перепутались бы местами.
IMAGE_TAG = re.compile(r"<img\b[^>]*>", re.I)
ATTR_SRC = re.compile(r"""\bsrc\s*=\s*["']([^"']*)["']""", re.I)
ATTR_ALT = re.compile(r"""\balt\s*=\s*["']([^"']*)["']""", re.I)

#: Подпись ВНУТРИ картинки. Она же — источник alt для собранных картинок, и
#: другого у него нет.
ARIA_LABEL = re.compile(r"""\baria-label\s*=\s*["']([^"']*)["']""")

#: Порог доли кириллицы. Обоснование — в докстроке: замер развёл языки на 6% и
#: 70–94%, и порог стоит между ними, а не «на глаз».
CYRILLIC_SHARE = 50

#: Предел английской части витрины в словах прозы (023). ЧИСЛО ИЗ ПРАВИЛА, А НЕ
#: ИЗ ЗАМЕРА: «первые пять минут» при 200 словах в минуту — тысяча слов; так же
#: его переводит check_prose каталога. Русский пересказ не считается: его читает
#: другой читатель, и пять минут англоязычного посетителя он не тратит. Замер на
#: включении (2026-10-08): 719 слов — запас 281.
PAGE_WORDS = 1000

#: Свод окна — налог на каждый старт: он попадает в контекст целиком (029).
CHARTER = "CLAUDE.md"

#: Предел свода в словах прозы. ИЗ РЯДА ПРАВОК, А НЕ ИЗ ПРАВИЛА: правило времени
#: не задаёт. Замер по всей истории CLAUDE.md на 2026-10-08: 487 → 2585 слов за
#: 29 правок, вверх 24, вниз ОДНА (−7 слов 22 августа); с 17 сентября +380
#: (2205 → 2585). Ряд снимается функцией prose_words по `git log -- CLAUDE.md`. Предел 3000 даёт около месяца роста нынешним темпом — не храповик на
#: сегодняшнем числе, а срок, к которому рост оплачивается выносом в канон, а не
#: новой строкой. Сосед — проект механизмов держит AGENTS.md пределом 2300.
#: Поднять предел законно, но правкой этого числа с замером, а не молча.
CHARTER_WORDS = 3000

#: Что глазами не читается. Порядок снятия значим: сначала теги (в их атрибутах
#: адреса без пробела перед «>», и голая ссылка съела бы закрывающую скобку),
#: потом адрес ссылки вместе с разделителем, потом голая ссылка — обратный
#: порядок у каталога посчитал 833 слова как 611.
HTML_TAG = re.compile(r"<!--.*?-->|</?[A-Za-z][^<>]*>", re.S)
LINK_ADDRESS = re.compile(r"\]\([^)]*\)")
BARE_URL = re.compile(r"https?://\S+")

#: Производные витрины — ветки, которые пишет сборка, а не человек. Тот же
#: перечень `agent-pr.yml` исключает из открытия изменений (кроме main):
#: копия намеренная, обе стороны называют одно — что в ветке не правят руками.
DERIVED_BRANCHES = ("assets", "output", "badges")

#: Адрес производного: файл ветки сборки по сырому адресу или страница ветки.
DERIVED_URL = re.compile(
    r"(?:raw\.githubusercontent\.com/ArtVsMark/ArtVsMark/"
    r"|github\.com/ArtVsMark/ArtVsMark/(?:blob|tree|raw)/)"
    rf"(?:{'|'.join(DERIVED_BRANCHES)})(?:[/?#]|$)", re.I)

#: Формы ССЫЛКИ, а не картинки, — названы поимённо (210): атрибут href в любых
#: кавычках, разметочная ссылка без «!» перед ней, ссылка по сноске.
HREF = re.compile(r"""\bhref\s*=\s*["']([^"']*)["']""", re.I)
MD_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(\s*<?([^)\s>]+)")
MD_LINK_REF = re.compile(r"(?<![!\]])\[[^\]]*\]\[([^\]]*)\]")

#: Начало строки заголовка русского пересказа: всё выше — английская часть.
RUSSIAN_HEADING = re.compile(rf"^#+[^\n]*{RUSSIAN_SECTION}", re.M)


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

    if DETAILS.search(page):
        found.append("на витрине <details>: там, где страницу читают текстом, "
                     "он схлопывается в заголовок без содержимого")

    if ".gif" in page.lower():
        found.append("на витрине гифка: решение владельца — гифки и картинки "
                     "самого проекта на витрину не берутся")

    refs = {label.lower(): url for label, url in MD_REF_DEF.findall(page)}
    sources = (IMAGE_SRC.findall(page) + MD_IMAGE.findall(page)
               + [refs.get((label or "").lower(), f"[{label}]")
                  for label in MD_IMAGE_REF.findall(page)])
    for src in sources:
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


def audit_alt(page: str, assets: dict[str, str]) -> list[str]:
    """Подпись картинки на странице сходится с подписью внутри картинки.

    ЗАЧЕМ ЭТО ГЕЙТ. У собранных картинок ``alt`` проставляет сама сборка из их
    ``aria-label`` (build_metrics.py::sync_alt) — разъехаться там нечему.
    Рукодельные — шапка, печатающаяся строка, разделитель — правятся человеком,
    и их подписи сверялись РАЗОВО И ВРУЧНУЮ: критерий профиля «изображения и
    доступность» в .rules/roles.md был объявлен, а спрашивать его было некому.

    ЧТО ИМЕННО СВЕРЯЕТСЯ, И ПОЧЕМУ ИМЕННО ЭТО:

    * ``alt`` есть у каждой картинки. Без атрибута читатель со скринридером
      получает имя файла, и это не «почти подпись», а другой текст;

    * подписи совпадают дословно. Две подписи об одном предмете — два места,
      где одно и то же расходится молча (правило 022);

    * подпись пустая ТОЛЬКО у декоративной. Картинка без ``aria-label``
      объявлена декорацией — тогда и на странице у неё пустой ``alt``. Обратное
      тоже находка: подписанная картинка с пустым ``alt`` теряет подпись;

    * у пары тем подпись одна. Страница показывает светлый вариант через
      ``<source>``, а ``alt`` берёт у тёмного: разъехавшись, они дали бы
      светлому читателю подпись от чужой картинки.
    """
    found: list[str] = []

    for tag in IMAGE_TAG.findall(page):
        src = ATTR_SRC.search(tag)
        if src is None:
            continue
        name = src.group(1).split("?")[0].rsplit("/", 1)[-1]
        if not src.group(1).split("?")[0].startswith(("./assets/", "assets/")):
            continue
        if name not in assets:
            found.append(f"на витрине картинка {name}, которой нет в assets/")
            continue
        alt = ATTR_ALT.search(tag)
        if alt is None:
            found.append(f"{name}: у картинки нет alt — читатель со скринридером "
                         "получит имя файла, а не подпись")
            continue
        inside = ARIA_LABEL.search(assets[name])
        if inside is None:
            if alt.group(1):
                found.append(f"{name}: на странице подпись есть, внутри картинки "
                             "aria-label нет — либо она декоративная и alt пустой, "
                             "либо подпись переезжает внутрь")
        elif alt.group(1) != inside.group(1):
            found.append(f"{name}: подпись на странице разошлась с aria-label "
                         f"внутри картинки — {alt.group(1)!r} против "
                         f"{inside.group(1)!r}")

    for name, body in sorted(assets.items()):
        if not name.endswith("-dark.svg"):
            continue
        pair = name.replace("-dark.svg", "-light.svg")
        if pair not in assets:
            continue
        here, there = ARIA_LABEL.search(body), ARIA_LABEL.search(assets[pair])
        if (here is None) != (there is None):
            found.append(f"{name} и {pair}: подпись есть только у одной из тем — "
                         "страница берёт alt у тёмной, а показать может светлую")
        elif here is not None and here.group(1) != there.group(1):
            found.append(f"{name} и {pair}: подписи тем разошлись — "
                         f"{here.group(1)!r} против {there.group(1)!r}")

    return found


def audit_service(name: str, text: str) -> list[str]:
    """Находки в служебном документе: он по-русски, его читают владелец и окно."""
    share = cyrillic_share(text)
    if share < CYRILLIC_SHARE:
        return [f"{name}: служебный документ не по-русски ({share}% кириллицы) — "
                "его читают владелец и окно, а не посетитель профиля"]
    return []


def prose_words(text: str) -> int:
    """Сколько слов документа читает человек: без тегов и адресов ссылок."""
    text = HTML_TAG.sub(" ", text)
    text = LINK_ADDRESS.sub("] ", text)
    return len(BARE_URL.sub(" ", text).split())


def audit_derived_links(page: str) -> list[str]:
    """Ссылки витрины на её же производные (089). Картинки не судятся."""
    refs = {label.lower(): url for label, url in MD_REF_DEF.findall(page)}
    targets = (HREF.findall(page) + MD_LINK.findall(page)
               + [refs.get(label.lower(), "") for label in MD_LINK_REF.findall(page)])
    return [f"ссылка из витрины в её производное: {url} — читатель уходит на копию, "
            "собранную сборкой, вместо источника; производное показывают картинкой, "
            "а ссылаются на то, из чего оно собрано (089)"
            for url in sorted(set(targets)) if DERIVED_URL.search(url)]


def english_part(page: str) -> str:
    """Витрина до заголовка русского пересказа; без него — целиком."""
    heading = RUSSIAN_HEADING.search(page)
    return page[: heading.start()] if heading else page


def audit_prose(page: str, charter: str) -> list[str]:
    """Находки по объёму: английская часть витрины (023) и свод окна (029)."""
    found: list[str] = []
    if (said := prose_words(english_part(page))) > PAGE_WORDS:
        found.append(f"{PAGE}: английская часть выросла до {said} слов при пределе "
                     f"{PAGE_WORDS} — это «первые пять минут» при 200 словах в минуту. "
                     "Подробности уносятся по ссылке в проект (023)")
    if (said := prose_words(charter)) > CHARTER_WORDS:
        found.append(f"{CHARTER}: свод вырос до {said} слов при пределе {CHARTER_WORDS} — "
                     "он читается целиком при старте каждого окна. Рост оплачивается "
                     "выносом пересказа в канон, а не подъёмом предела молча (029)")
    return found


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
        # Формы, которых прежний гейт не видел (206): картинка проходила целиком.
        ("спойлер заглавными", ok_page + "<DETAILS><summary>x</summary>y</DETAILS>", True),
        ("картинка разметкой", ok_page + "![demo](https://github.com/user-attachments/assets/x)", True),
        ("картинка по сноске", ok_page + "![demo][d]\n\n[d]: https://example.com/a.png\n", True),
        ("атрибут в одинарных кавычках", ok_page + "<img src='https://example.com/a.png' alt='a'>", True),
        ("пробелы вокруг знака равенства", ok_page + '<img src = "https://example.com/a.png" alt="a">', True),
        ("короткая ссылка на задачу", ok_page + "Closed in #42.", True),
        ("своя картинка разметкой — законна", ok_page + "![шапка](./assets/header-dark.svg)", False),
        ("цвет и якорь — не ссылка на задачу", ok_page + "color #58A6FF, see [x](#section)", False),
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

    # ── ссылки в производные ───────────────────────────────────────────────
    # Каждая форма ссылки и каждая ветка сборки — отдельным случаем; живая
    # половина — картинка из той же ветки и ссылка на ЧУЖУЮ ветку фактов.
    raw = "https://raw.githubusercontent.com/ArtVsMark/ArtVsMark/assets/stack-dark.svg"
    link_cases = [
        ("картинка из ветки сборки — законна", f'<img src="{raw}" alt="x">', False),
        ("srcset из ветки сборки — законен", f'<source srcset="{raw}">', False),
        ("картинка разметкой — законна", f"![x]({raw})", False),
        ("ссылка href на сырой адрес", f'<a href="{raw}">x</a>', True),
        ("href в одинарных кавычках", f"<a href='{raw}'>x</a>", True),
        ("разметочная ссылка", f"[x]({raw})", True),
        ("ссылка по сноске", f"[x][s]\n\n[s]: {raw}\n", True),
        ("страница ветки output",
         '<a href="https://github.com/ArtVsMark/ArtVsMark/tree/output">x</a>', True),
        ("файл ветки badges",
         "[x](https://github.com/ArtVsMark/ArtVsMark/blob/badges/f.json)", True),
        ("факты ЧУЖОГО проекта — его источник, не наша копия",
         '<a href="https://github.com/ArtVsMark/Stepik-Python-Grader/blob/badges/f.json">x</a>',
         False),
        ("ветка с похожим началом — не производное",
         "[x](https://github.com/ArtVsMark/ArtVsMark/tree/assets-old)", False),
        ("картинка по сноске — законна", f"![x][s]\n\n[s]: {raw}\n", False),
    ]
    for name, page, must_reject in link_cases:
        found = audit_derived_links(page)
        if bool(found) is not must_reject:
            broken.append(f"производные, {name}: ожидалось "
                          f"{'отказ' if must_reject else 'пропуск'}, вышло — {found}")
        print(f"  {'отвергнут' if found else 'пропущен '} — производные: {name}")
    if not any("stack-dark.svg" in line for line in audit_derived_links(f"[x]({raw})")):
        broken.append("отказ на ссылке в производное не называет адрес")

    # ── объём прозы ────────────────────────────────────────────────────────
    # Граница считается и с той, и с другой стороны: ровно на пределе — пропуск.
    # Формы того, что не читается глазами, названы поимённо: тег, маркер-
    # комментарий, адрес ссылки, голая ссылка, тег с адресом вплотную к «>».
    words = lambda n: " ".join(["word"] * n)  # noqa: E731
    ru = f"\n### {RUSSIAN_SECTION}\n"
    prose_cases = [
        ("витрина ровно на пределе", words(PAGE_WORDS) + ru, "", False),
        ("витрина на слово больше", words(PAGE_WORDS + 1) + ru, "", True),
        ("русский пересказ не считается", words(PAGE_WORDS) + ru + words(500), "", False),
        ("теги и маркеры не слова",
         words(PAGE_WORDS) + '<!--m:x--><img src="https://h/a.svg?v=1" alt="a b c">' + ru, "", False),
        ("адрес ссылки не слово", words(PAGE_WORDS - 1) + " [x](https://a/b c)" + ru, "", False),
        ("голая ссылка не слово", words(PAGE_WORDS) + " https://a/b" + ru, "", False),
        ("свод ровно на пределе", ru, words(CHARTER_WORDS), False),
        ("свод на слово больше", ru, words(CHARTER_WORDS + 1), True),
    ]
    for name, page, charter, must_reject in prose_cases:
        found = audit_prose(page, charter)
        if bool(found) is not must_reject:
            broken.append(f"объём, {name}: ожидалось "
                          f"{'отказ' if must_reject else 'пропуск'}, вышло — {found}")
        print(f"  {'отвергнут' if found else 'пропущен '} — объём: {name}")
    if prose_words("a [b](https://x/y) c") != 3:
        broken.append("адрес ссылки слипся со словом: счёт зависит от порядка замен")

    # ── подписи картинок ───────────────────────────────────────────────────
    # Набор двусторонний (правило 140). Живая половина здесь не формальность:
    # гейт, ругающийся на исправную страницу, краснит каждое изменение подряд —
    # а красное фоном обесценивает настоящее.
    said = "Шапка витрины"
    art = {"header-dark.svg": f'<svg aria-label="{said}"><text>x</text></svg>',
           "header-light.svg": f'<svg aria-label="{said}"><text>x</text></svg>',
           "divider-dark.svg": "<svg><path d=\"M0 0\"/></svg>",
           "divider-light.svg": "<svg><path d=\"M0 0\"/></svg>"}
    ok_alt = (f'<img src="./assets/header-dark.svg?v=1" alt="{said}">\n'
              '<img src="./assets/divider-dark.svg?v=1" alt="">\n')
    alt_cases = [
        ("подписи сходятся, декоративный без подписи", ok_alt, art, False),
        ("подпись на странице разошлась с картинкой",
         ok_alt.replace(said, "Другая шапка", 1), art, True),
        ("alt пропал вовсе",
         '<img src="./assets/header-dark.svg?v=1" width="100%">', art, True),
        ("декоративный вдруг подписан",
         '<img src="./assets/divider-dark.svg?v=1" alt="разделитель">', art, True),
        ("подписанная картинка с пустым alt",
         '<img src="./assets/header-dark.svg?v=1" alt="">', art, True),
        ("подписи тем разошлись", ok_alt,
         {**art, "header-light.svg": '<svg aria-label="Header"><text>x</text></svg>'}, True),
        ("подпись есть только у одной темы", ok_alt,
         {**art, "header-light.svg": "<svg><text>x</text></svg>"}, True),
        ("на витрине картинка, которой нет в дереве",
         '<img src="./assets/missing-dark.svg" alt="нет такой">', art, True),
        # Чужая картинка сюда не относится: её подпись проставляет сборка, а
        # источник судит audit_page. Ложный отказ здесь стоил бы дороже.
        ("значок с чужого хоста не судится подписью",
         '<img src="https://img.shields.io/badge/x-y-1F6FEB" alt="значок">', art, False),
    ]
    for name, page, assets, must_reject in alt_cases:
        found = audit_alt(page, assets)
        if bool(found) is not must_reject:
            broken.append(f"подписи, {name}: ожидалось "
                          f"{'отказ' if must_reject else 'пропуск'}, вышло — {found}")
        print(f"  {'отвергнут' if found else 'пропущен '} — подписи: {name}")

    # Отказ обязан называть картинку: находка без имени — отказ, по которому
    # нечего чинить (правило 158).
    if not any("header-dark.svg" in line
               for line in audit_alt(ok_alt.replace(said, "Другая", 1), art)):
        broken.append("отказ на разошедшейся подписи не называет картинку")

    # Отказ обязан НАЗЫВАТЬ предмет: находка без имени — это отказ, по которому
    # нечего чинить (правило 158).
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
        page = (ROOT / PAGE).read_text(encoding="utf-8")
        # Рукодельные картинки — те, что лежат в дереве: собранные с переездом
        # в ветку `assets` (правило 160) здесь больше не хранятся, и списка
        # имён для них не нужно.
        assets = {path.name: path.read_text(encoding="utf-8")
                  for path in sorted((ROOT / "assets").glob("*.svg"))}
        charter = (ROOT / CHARTER).read_text(encoding="utf-8")
        found = audit_page(page) + audit_alt(page, assets) + audit_prose(page, charter)
        found += audit_derived_links(page)
        for name in SERVICE:
            found += audit_service(name, (ROOT / name).read_text(encoding="utf-8"))
    except OSError as e:
        print(f"проверка не отработала: {e}", file=sys.stderr)
        return 2

    if found:
        print(checks.annotate("error", f"запреты витрины нарушены: {len(found)}"), file=sys.stderr)
        for line in found:
            print(f"  • {line}", file=sys.stderr)
        print("\n  Эти запреты держались чтением свода и теперь держатся здесь."
              "\n  Если запрет устарел — меняют свод и этот гейт вместе, а не обходят.",
              file=sys.stderr)
        return 1

    print(f"запреты витрины соблюдены: {PAGE}, {len(assets)} рукодельных картинки "
          f"и {len(SERVICE)} служебных документа; объём — витрина "
          f"{prose_words(english_part(page))}/{PAGE_WORDS}, "
          f"свод {prose_words(charter)}/{CHARTER_WORDS} слов")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
