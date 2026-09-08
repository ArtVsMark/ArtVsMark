#!/usr/bin/env python3
"""Собирает метрики витрины из живых источников и рисует её картинки.

Числа на странице профиля устаревают молча: релиз v1.11.0 вышел через четыре
часа после того, как в README было вписано «11 releases shipped». Поэтому они
не вписываются руками, а измеряются — раз в сутки, из репозиториев, которые их
и порождают.

Что откуда берётся:

* число тестов, число тест-модулей, экспериментальные версии Python и проверок
  на PR — из ``facts.json``, который грейдер публикует о себе сам (ветка
  ``badges``, см. ``grader_facts``). Раньше витрина считала это сама: клонировала
  чужой репозиторий ради двух подсчётов, разбирала чужой ``ci.yml`` регулярным
  выражением и оценивала проверки медианой по семи PR. Знание о чужом устройстве
  жило здесь и молча устарело бы от переноса каталога на той стороне;
* обязательные проверки, число ОС и версий Python — из ruleset защиты ветки
  ``main``. Список правил ветки (``/rules/branches/main``) читается **без прав
  admin**, в отличие от самого объекта ruleset: имена обязательных контекстов
  там есть, и «11 обязательных» больше не приходится держать в памяти;
* релизов — длиной списка релизов. Номер последней версии витрина не
  повторяет: его показывает живой бейдж PyPI, а два места для одного числа —
  это два места, где оно может разойтись;
* покрытие и карточки глоссария — из ветки ``badges`` грейдера: его CI уже
  публикует эти числа как shields-endpoint JSON, и иначе их не получить —
  нужен прогон тестов и установленный пакет;
* пул ``good first issue`` — прямым запросом к трекеру, а НЕ из бейджа рядом с
  предыдущими двумя: бейдж обновляет CI грейдера, и между его прогонами число
  отстаёт. Витрина показывала 3, когда открытых было 4;
* правил в каталоге — полем ``count`` его машиночитаемого экспорта. Оттуда же
  берутся их номера: правило, которого ещё нет в ``.rules/bindings.json``,
  дописывается туда со статусом ``unreviewed``. Раньше
  витрина клонировала каталог целиком и считала файлы сама — то есть держала
  у себя копию чужого определения правила. Определения совпадали до первого
  чужого изменения, а разошлись бы молча: оба числа выглядят правдоподобно;
* порядок проектов в таблице — по времени последнего пуша, закреплённый
  первым. Список живёт данными в ``projects.json``, а не разметкой в README:
  порядок, расставленный руками, — та же память автора, что и число,
  вписанное руками. Показываются первые ``featured_limit``; сколько проектов
  осталось за потолком, сборка пишет под таблицей — урезанная выдача обязана
  говорить, что она урезана.

Чего здесь НЕТ и почему: пустой список обходов защиты ветки. GitHub отдаёт
``bypass_actors`` только админу репозитория, у ``GITHUB_TOKEN`` витрины таких
прав нет. Непроверяемое число на плитке выглядит как измеренное, поэтому оно
снято с картинки: утверждение живёт в тексте витрины как утверждение, а не как
метрика.

Исходы: 0 — собралось; 1 — не собралось с названной причиной;
2 — источник не ответил. Третий не молчит (правило 039): отказ чужого
сервера и наша поломка чинятся разными людьми.
"""

from __future__ import annotations

import base64
import contextlib
import datetime as dt
import hashlib
import functools
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape

# Путь добавляется явно: без него `import checks` держится на том, из какого
# каталога запустили, и ломается, едва модуль импортируют, а не запускают.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import checks  # noqa: E402

REPO = "ArtVsMark/Stepik-Python-Grader"
API = "https://api.github.com"
# Экспорт каталога правил: обычный HTTP по «сырой» ссылке — ни API площадки, ни
# клона, ни токена. Так его и задумал контракт: подключиться может кто угодно.
RULES_EXPORT = "https://raw.githubusercontent.com/ArtVsMark/Engineering-Incidents-Playbook/main/export/rules.json"
RULES_SCHEMA = "1"  # мажор ВЫГРУЗКИ ПРАВИЛ, который умеет читать эта сборка
# Заготовка ответа потребителя у каталога. Отсюда берётся версия формата
# ОТВЕТА — того файла, который витрина ведёт у себя. Это НЕ версия выгрузки
# правил, и ключ `schema` у них общий только по имени (правило 164).
ANSWER_CONTRACT = "https://raw.githubusercontent.com/ArtVsMark/Engineering-Incidents-Playbook/main/templates/bindings.json"
# Факты грейдера, опубликованные им самим (его PR #1411). До этого витрина
# считала их сама: клонировала репозиторий ЦЕЛИКОМ ради двух подсчётов по
# tests/, разбирала чужой ci.yml регулярным выражением и оценивала число
# проверок медианой по семи последним PR — потому что снаружи точного ответа
# не видно. Внутри он есть, и теперь издатель считает, а потребитель читает.
#
# Цена была не в расходе, а в связанности: знание о том, где у грейдера лежат
# тесты и как устроена его матрица, жило здесь. Перенеси он каталог — у витрины
# молча изменилось бы число, а не сломалась сборка.
FACTS_PATH = ".github/badges/facts.json"
FACTS_SCHEMA = "1"  # мажор ЧУЖОГО контракта, который умеет читать эта сборка
# Порог устаревания фактов. Не «сколько живёт число», а «за сколько молчание
# издателя перестаёт быть тишиной выходных»: файл пересобирается на каждом пуше
# в main, витрина собирается ежесуточно. Две недели без пуша у активного
# соседа — это остановка его прогона либо остановка проекта, и человеку стоит
# знать о любой из них. Порог назван здесь, а не спрятан в условии.
FACTS_STALE_DAYS = 14
ROOT = pathlib.Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects.json"
# Куда витрина ссылается за производными картинками. Они пересобираются чаще,
# чем идут изменения, и в дереве общей ветки не хранятся (правило 160): ветку
# `assets` раскладывает и публикует `metrics.yml`. Форма адреса не выбрана, а
# взята с уже работающего: змейка живёт в ветке `output` и приезжает на витрину
# ровно так же — `raw` отдаёт SVG с `content-type: image/svg+xml`.
ASSETS_BRANCH = "https://raw.githubusercontent.com/ArtVsMark/ArtVsMark/assets"
# Ссылка на картинку витрины в ЛЮБОЙ из двух форм: относительной (рукодельное
# лежит в дереве) и по ветке (производное). Обе нужны одному выражению: сборка
# читает README, который сама же и переписала, и должна узнавать собственный
# вывод — иначе первый переезд ссылки стал бы последним.
ASSET_LINK = re.compile(
    rf"(?:\./assets/|{re.escape(ASSETS_BRANCH)}/)(?P<name>[a-z0-9-]+)\.svg(?:\?v=[0-9a-f]+)?"
)
# Ответ витрины каталогу: что здесь принято, что отклонено, чего нет предмета.
BINDINGS = ROOT / ".rules/bindings.json"
# Потолок «Current focus». Двигается только вниз: рост означает, что уборку
# заменили правкой ограничителя.
FOCUS_LIMIT = 5
FONT = "Inter,Segoe UI,Helvetica,Arial,sans-serif"


#: Куда прикрепляется адрес отказавшего источника. Отдельное имя, а не текст
#: сообщения: у ``HTTPError`` текст собирается из кода и причины, и дописывать
#: туда адрес значило бы подменять чужой разбор своим.
SOURCE_URL = "source_url"


@contextlib.contextmanager
def naming(url: str):
    """Обращение к чужому источнику, отказ которого называет адрес.

    Третий исход печатал причину без предмета: «источник не ответил — HTTP
    Error 403: Forbidden», и какой именно из двадцати с лишним источников
    отказал, в сообщении не было. Окно, стартовавшее 31 августа, дважды прогнало
    гейт и дважды не смогло понять, где чинить; адрес пришлось восстанавливать
    подменой ``urlopen``. Причина без предмета отправляет чинить не туда —
    вопрос «чужой отказ или наш» без адреса не решается вовсе (правила 039 и
    151).

    КЛАСС ОТКАЗА НЕ ПОДМЕНЯЕТСЯ, и это не осторожность, а цена ошибки. Первая
    редакция поднимала свой ``SourceRefused``, и штатное отсутствие значка —
    ``404``, который ловят ``except HTTPError`` в двух местах, — перестало
    ловиться: сборка упала на проекте, у которого значков нет по замыслу.
    Поэтому адрес прикрепляется атрибутом к самому отказу, а сам отказ летит
    дальше как есть.

    Разбор ответа обёрнут вместе с обращением намеренно: ``ValueError`` от
    битого JSON — тоже третий исход по объявлению, и адрес ему нужен ровно
    так же. Внутренний адрес не перебивается внешним: ближний к отказу
    точнее.
    """
    try:
        yield
    except (urllib.error.URLError, OSError, ValueError, KeyError) as refusal:
        if getattr(refusal, SOURCE_URL, None) is None:
            try:
                setattr(refusal, SOURCE_URL, url)
            except AttributeError:  # экзотика вроде исключений со __slots__
                pass
        raise


def _get(url: str, authenticated: bool = True) -> bytes:
    """Загрузка. ``authenticated=False`` — для не-API источников.

    Заголовок ``Authorization`` посылается не всюду: ``raw.githubusercontent.com``
    отвечает на него 404 — токен для него чужой, и вместо содержимого приходит
    «нет такого файла».
    """
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **(
                {"Authorization": f"Bearer {t}"}
                if authenticated and (t := os.environ.get("GH_TOKEN"))
                else {}
            ),
        },
    )
    with naming(url), urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _api(path: str) -> object:
    with naming(f"{API}{path}"):
        return json.loads(_get(f"{API}{path}"))


#: Сама витрина. В списке проектов её нет — она их показывает, — но её код
#: тоже написан, и в следе технологий он считается наравне с остальными.
SHOWCASE = "ArtVsMark/ArtVsMark"

#: Владелец витрины. Отсюда берутся профильные числа — те, что описывают не
#: отдельный репозиторий, а инженерную работу целиком.
OWNER = "ArtVsMark"

#: Сколько дней календаря вкладов показывает витрина. Год — не круглое число, а
#: то, что отдаёт сама площадка: `contributionsCollection` без дат возвращает
#: последние 365 дней, и брать другой отрезок значило бы считать самим.
CONTRIB_DAYS = 365


def _graphql(query: str) -> dict:
    """Ответ GraphQL-API площадки. Второй вход, и он назван (правило 001).

    ЗАЧЕМ ВТОРОЙ, ЕСЛИ У REST ОДИН. Календарь вкладов REST не отдаёт вовсе:
    ``contributionsCollection`` живёт только в GraphQL, и обойти это нечем —
    считать вклады по событиям нельзя, `/users/*/events` хранит 90 дней и
    урезан по числу записей. Это не вторая труба к тем же данным, а
    единственная к другим: у REST и GraphQL здесь непересекающиеся предметы.

    ОКНУ ЭТОТ ВХОД ЗАКРЫТ, и это названо, а не обойдено. Прокси сессии отвечает
    «only the pinned set of PR-review operations is served» — то есть проверить
    запрос отсюда нельзя, его проверит первый живой прогон. Поэтому разбор
    ответа целиком покрыт набором на подделках, а отказ считается третьим
    исходом: картинка не рисуется, прежняя остаётся (правило 039).
    """
    body = json.dumps({"query": query}).encode("utf-8")
    request = urllib.request.Request(
        f"{API}/graphql", data=body,
        headers={"Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "artvsmark-profile"})
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with naming(f"{API}/graphql"), urllib.request.urlopen(request, timeout=30) as response:
        answer = json.loads(response.read())
    if "errors" in answer:
        # Ошибка GraphQL приезжает с кодом 200 — молча принять её значило бы
        # показать пустые числа как измеренные.
        raise SystemExit(f"GraphQL ответил ошибкой: {answer['errors'][0].get('message', '?')}")
    return answer["data"]



@functools.lru_cache(maxsize=None)
def repo_meta(repo: str) -> dict:
    """Карточка репозитория — один запрос на прогон, а не по одному на читателя.

    Её читают двое: ранжирование проектов (``pushed_at``) и счёт задач для
    новичка (``open_issues_count`` минус открытые PR). Оба обращались сами, и
    замер показал ровно это: 36 обращений за прогон, из них четыре — вторая
    карточка тех же четырёх проектов.

    ЧТО ЭТО НЕ ЧИНИТ, И ЭТО ВАЖНЕЕ ЭКОНОМИИ. Задача #65 предполагала, что расход
    сборки и есть причина исчерпанного бюджета на #64. Замер премису отверг:
    сборка ходит штатным ``GITHUB_TOKEN`` репозитория, а падали шаги на
    ``MERGE_QUEUE_TOKEN`` — личном токене владельца. Это разные бюджеты, и
    четыре сэкономленных запроса не защищают от того отказа ничем. Здесь
    гигиена, а не починка: защита от исчерпания — разбор исходов в
    ``scripts/gh_outcome.py``, а не экономия.

    Кэш живёт в пределах процесса и умирает вместе с ним: сборка короткая, и
    карточка за её время не меняется.
    """
    return _api(f"/repos/{repo}")


def badge(name: str) -> str:
    """Значение живого бейджа грейдера из ветки ``badges``.

    Бейджи публикуются отдельной веткой (issue #1235 грейдера), а не в ``main``,
    поэтому берутся не из клона рабочего дерева, а по ссылке на ветку.

    Читается через contents-API, а НЕ через ``raw.githubusercontent.com``:
    raw отвечает 404 на запрос с заголовком ``Authorization`` — токен для него
    чужой, и вместо содержимого приходит «нет такого файла». Отладка этого
    стоит дорого: URL в браузере открывается, а сборка падает. Заодно contents
    отдаёт свежий файл, тогда как raw держит свой кэш.
    """
    payload = _api(f"/repos/{REPO}/contents/.github/badges/{name}.json?ref=badges")
    return json.loads(base64.b64decode(payload["content"]))["message"]



def repo_activity(repo: str) -> str:
    """Время последнего пуша — ключ сортировки проектов.

    Ошибка чтения здесь не проглатывается: репозиторий, ставший приватным или
    переименованный, — это битая ссылка на витрине, и узнать о ней лучше от
    упавшей сборки, чем от посетителя.
    """
    return repo_meta(repo)["pushed_at"]


#: Категории ранжирования акцента. Порядок в кортеже — только порядок показа;
#: вес у всех пяти одинаковый, и это решение, а не умолчание: взвешивать
#: значило бы вписать в витрину число, которого никто не измерял.
FEATURED_FIELDS = ("stars", "commits", "issues", "releases", "prs")

#: Сколько проектов показывает баннер. Потолок, а не настройка: его снижают,
#: но не повышают — иначе «акцент» перестаёт быть акцентом.
FEATURED_ACCENTS = 4

#: Один акцент держится столько секунд. Паузы по наведению не будет: страницу
#: профиля читает Markdown, картинка вставлена через <img> и событий не
#: получает. Названо здесь, потому что в задаче #43 это стояло требованием.
ACCENT_SECONDS = 15


def _count(path: str) -> int:
    """Длина коллекции, считанная по заголовку ``Link``, а не выкачиванием.

    ``per_page=1`` плюс номер последней страницы — это один запрос вместо
    семнадцати для репозитория с 1664 коммитами.

    Приём работает не везде, и молчать об этом нельзя. Часть эндпойнтов
    площадки перешла на курсорную разбивку: там в ``Link`` есть только
    ``rel="next"`` со ссылкой ``after=…``, а последней страницы нет вовсе.
    Первая редакция в этом случае возвращала длину страницы — то есть
    **единицу** вместо сорока шести, и делала это молча. Теперь такой ответ
    роняет сборку: посчитать нельзя, а правдоподобное число хуже отказа
    (правила 039 и 075).
    """
    request = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {t}"} if (t := os.environ.get("GH_TOKEN")) else {}),
        },
    )
    with naming(f"{API}{path}"), urllib.request.urlopen(request, timeout=30) as response:
        link = response.headers.get("Link", "")
        body = json.loads(response.read())
    last = re.search(r'[?&]page=(\d+)>;\s*rel="last"', link)
    if last:
        return int(last.group(1))
    if 'rel="next"' in link:
        raise RuntimeError(
            f"{path}: страниц больше одной, но последней в Link нет — "
            "курсорная разбивка, посчитать по номеру страницы нельзя"
        )
    # Единственная страница: её длина и есть ответ.
    return len(body)


def project_stats(repo: str) -> dict[str, int]:
    """Пять измеренных категорий проекта.

    Открытые задачи считаются вычитанием, а не полем ``open_issues_count``:
    площадка кладёт в него и изменения тоже. У грейдера это 46 против 45
    настоящих — тот же класс ошибки, из-за которого витрина однажды показывала
    три задачи для новичка при четырёх открытых.

    Поиск площадки для этого не годится: у него своё ограничение частоты и своя
    выдача, а вычитание двух счётчиков даёт точный ответ на тех же
    репозиторных запросах.
    """
    meta = repo_meta(repo)
    # `open_issues_count` — единственный счётчик задач, который площадка отдаёт
    # числом. Считать их разбивкой нельзя: эндпойнт задач курсорный.
    open_prs = _count(f"/repos/{repo}/pulls?state=open&per_page=1")
    return {
        "stars": meta["stargazers_count"],
        "commits": _count(f"/repos/{repo}/commits?per_page=1"),
        "issues": meta["open_issues_count"] - open_prs,
        "releases": _count(f"/repos/{repo}/releases?per_page=1"),
        "prs": _count(f"/repos/{repo}/pulls?state=all&per_page=1"),
    }


#: Запрос календаря вкладов. Без дат площадка отдаёт последние 365 дней сама —
#: считать отрезок за неё значило бы завести второе определение года.
#:
#: Логин подставляется через json.dumps, а не форматированием: имя приезжает
#: из данных, и склеивать запрос со строкой значит писать инъекцию собственными
#: руками. Здесь оно наше, но образец копируют, а не читают.
CONTRIB_QUERY = """
query {
  user(login: %s) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def contribution_days(login: str = OWNER) -> tuple[int, list[tuple[str, int]]]:
    """Вклады за год: всего и по дням. Дни идут по возрастанию даты.

    Число «всего» берётся у площадки, а не суммируется из дней: сумма — второе
    определение той же величины, и разойтись они могут молча (правило 090).
    """
    data = _graphql(CONTRIB_QUERY % json.dumps(login))
    calendar = data["user"]["contributionsCollection"]["contributionCalendar"]
    days = [(day["date"], day["contributionCount"])
            for week in calendar["weeks"] for day in week["contributionDays"]]
    return calendar["totalContributions"], sorted(days)


def streaks(days: list[tuple[str, int]], today: str = "") -> tuple[int, int]:
    """Текущая и самая длинная серия дней с вкладами.

    ЧТО СЧИТАЕТСЯ ТЕКУЩЕЙ СЕРИЕЙ. Дни идут подряд до СЕГОДНЯ; если сегодня
    вкладов ещё нет, серия считается по вчерашний день и не обрывается. Это не
    поблажка: календарь площадки заполняется с задержкой, и обрывать серию в
    полдень значило бы показывать ноль там, где работа идёт.

    ПУСТОЙ КАЛЕНДАРЬ — НОЛЬ, А НЕ ОШИБКА: у нового профиля вкладов может не
    быть вовсе, и это состояние, а не сбой (правило 027).

    Хвост календаря обрезается по `today`, потому что площадка отдаёт неделю
    целиком — включая дни, которые ещё не наступили. Считать их нулями значило
    бы обрывать серию будущим.
    """
    if not days:
        return 0, 0
    today = today or dt.date.today().isoformat()
    past = [(date, count) for date, count in days if date <= today]
    if not past:
        return 0, 0

    longest = run = 0
    previous: dt.date | None = None
    for date, count in past:
        current = dt.date.fromisoformat(date)
        run = run + 1 if count and previous and (current - previous).days == 1 else (1 if count else 0)
        longest = max(longest, run)
        previous = current

    # Текущая серия: считаем назад от последнего дня. Ноль сегодня серию не
    # рвёт — рвёт ноль вчера.
    tail = list(reversed(past))
    if tail and tail[0][1] == 0:
        tail = tail[1:]
    current_run = 0
    expected: dt.date | None = None
    for date, count in tail:
        day = dt.date.fromisoformat(date)
        if count == 0 or (expected is not None and day != expected):
            break
        current_run += 1
        expected = day - dt.timedelta(days=1)
    return current_run, longest


def owned_stars(login: str = OWNER) -> tuple[int, int]:
    """Звёзды и число публичных репозиториев ВЛАДЕЛЬЦА, без форков.

    Форки исключены намеренно: их звёзды принадлежат исходному проекту, и
    складывать их значило бы приписывать себе чужое. Постранично, потому что
    страница по умолчанию — тридцать записей, а витрина не знает заранее,
    сколько их будет завтра.
    """
    stars = repos = 0
    page = 1
    while True:
        chunk = _api(f"/users/{login}/repos?per_page=100&type=owner&page={page}")
        if not chunk:
            break
        for repo in chunk:
            if repo.get("fork"):
                continue
            repos += 1
            stars += repo.get("stargazers_count", 0)
        if len(chunk) < 100:
            break
        page += 1
    return stars, repos


def language_reach(repos: list[str]) -> list[tuple[str, int]]:
    """Языки по ЧИСЛУ репозиториев, а не по объёму кода. Наибольший охват первым.

    ПОЧЕМУ НЕ ПО БАЙТАМ, КАК ДЕЛАЮТ ТИПОВЫЕ КАРТОЧКИ. Замер по нашим пяти
    репозиториям: Python — 10 313 K, JavaScript — 259 K, HTML и CSS вместе —
    172 K, остальное 8 K. Круговая диаграмма из этого выходит на 96% одним
    сектором и не сообщает ничего, кроме языка, на котором пишут. Задача #139
    исключила top-languages из первой версии ровно по этой причине: объём кода
    не отражает инженерную работу.

    ОХВАТ ОТВЕЧАЕТ НА ДРУГОЙ ВОПРОС — в скольких проектах язык вообще
    встречается. У него нет ложной точности процентов: «Python в 5 из 5, HTML в
    3 из 5» — утверждение, которое читатель может проверить, открыв проекты.
    """
    reach: dict[str, int] = {}
    for repo in repos:
        for language in _api(f"/repos/{repo}/languages"):
            reach[language] = reach.get(language, 0) + 1
    return sorted(reach.items(), key=lambda pair: (-pair[1], pair[0]))


def profile_stats() -> dict[str, object]:
    """Профильные числа витрины. Ключ отсутствует — значит источник промолчал.

    СОБИРАЕТСЯ В ОДНОМ МЕСТЕ, ПОТОМУ ЧТО РИСУЕТСЯ ОДНОЙ КАРТИНКОЙ. Разложить
    сбор по вызовам рисовальщика значило бы ходить в сеть из рисования — и
    получить картинку, которая наполовину нарисована, наполовину упала.
    """
    profile = _api(f"/users/{OWNER}")
    stars, owned = owned_stars()
    total, days = contribution_days()
    current, longest = streaks(days)
    return {
        "repos": profile.get("public_repos", owned),
        "followers": profile.get("followers", 0),
        "stars": stars,
        "contributions": total,
        "streak": current,
        "longest": longest,
        "days": days,
    }


def rank_featured(stats: dict[str, dict[str, int]]) -> list[str]:
    """Порядок акцентов: сумма мест по каждой категории, меньше — выше.

    Почему сумма мест, а не сумма значений: категории несоизмеримы. У грейдера
    1664 коммита и 2 звезды; сложив их, получим «коммиты», переименованные в
    рейтинг. Место отвечает на единственный вопрос, который здесь имеет
    смысл, — который из проектов по этой категории впереди.

    Равные значения делят место поровну, иначе на итог начинает влиять порядок
    в списке проектов, а он к делу не относится. При полном равенстве мест
    порядок задаётся именем — лишь бы он не менялся от прогона к прогону.
    """
    places: dict[str, float] = {repo: 0.0 for repo in stats}
    for field in FEATURED_FIELDS:
        values = sorted({s[field] for s in stats.values()}, reverse=True)
        place = {value: index for index, value in enumerate(values)}
        for repo, s in stats.items():
            places[repo] += place[s[field]]
    return sorted(places, key=lambda repo: (places[repo], repo))


#: Потолок описания в баннере. Считан от ширины картинки: 932 точки под текст
#: при кегле 15 — это около ста двадцати знаков. Обрезать описание молча нельзя:
#: витрина держит правило «урезанная выдача обязана сказать, что она урезана», а
#: описание — не то место, где такую приписку поставишь. Поэтому длиннее потолка
#: это отказ сборки, а не многоточие. Потолок двигается только вниз (050).
TAGLINE_LIMIT = 110


def accent_label(accents: list[dict]) -> str:
    """Подпись картинки: всё, что в ней нарисовано, словами.

    Текстовому читателю достаётся только эта строка, и она обязана нести не
    один кадр из четырёх, а все: название, описание, показатели, стек и числа.
    Тише всех на этой витрине врал именно ``alt``.
    """
    parts = []
    for accent in accents:
        pieces = [f"{accent['title']} — {accent['tagline'].rstrip('.')}"]
        if accent["badges"]:
            pieces.append(", ".join(f"{name} {value}" for name, value, _ in accent["badges"]))
        pieces.append(", ".join(f"{accent['stats'][f]} {f}" for f in FEATURED_FIELDS))
        # Второй ряд и полоса правил — часть той же картинки, и подпись обязана
        # нести их тоже: текстовому читателю достаётся только она.
        if accent.get("made"):
            pieces.append(", ".join(f"{value.replace(chr(0x2009), ' ')} {label}"
                                    for value, label in accent["made"]))
        rules = accent.get("rules")
        if rules:
            shares = ", ".join(f"{name} {value}"
                               for name, value in ordered_mechanisms(rules["mechanisms"]))
            tail = f"rules held by: {shares}"
            if rules.get("answered"):
                tail += f"; {rules['answered']} answered"
            if rules.get("trails"):
                tail += f", {rules['trails']} linked to issues"
            pieces.append(tail)
        elif "rules" in accent:
            # Пробел называется, а не выравнивается: «не подключён» и «правил
            # ноль» звучат по-разному и в подписи тоже.
            pieces.append("not connected to the rules catalogue yet")
        pieces.append(accent["stack"])
        parts.append(". ".join(pieces))
    return " · ".join(parts)


#: Числа блока «кто это»: что проект измерил о собственной работе. Порядок
#: закрыт — он же порядок показа, и разъехаться им негде.
MADE_FIELDS = (("tests", "functions", "tests"),
               ("tests", "modules", "test modules"),
               ("checks_per_pr", "count", "checks per PR"))


#: Цвет доли по механизму. Словарь ЧУЖОЙ и растёт: за две недели к четырём
#: значениям добавилось пятое. Поэтому у незнакомого механизма есть свой цвет —
#: доля показывается, а не исчезает из полосы молча.
MECHANISM_TONES = {
    "dark": {"gate": "#3FB950", "pipeline": "#58A6FF", "document": "#8B949E",
             "code": "#D2A8FF", "none": "#F85149", "_": "#6E7681"},
    "light": {"gate": "#1A7F37", "pipeline": "#0969DA", "document": "#8C959F",
              "code": "#8250DF", "none": "#CF222E", "_": "#6E7781"},
}

#: Порядок долей в полосе: от механизма к его отсутствию. Механизм, которого
#: здесь нет, встаёт после известных — порядок задан, но не закрыт.
MECHANISM_ORDER = ("gate", "pipeline", "code", "document", "none")


def ordered_mechanisms(mechanisms: dict[str, int]) -> list[tuple[str, int]]:
    """Доли в показанном порядке: известные по списку, прочие следом по имени."""
    known = [(name, mechanisms[name]) for name in MECHANISM_ORDER if name in mechanisms]
    rest = sorted((n, v) for n, v in mechanisms.items() if n not in MECHANISM_ORDER)
    return known + rest


def project_made(facts: dict) -> list[tuple[str, str]]:
    """Чем проект меряет свою работу. Пусто — он об этом не рассказывает.

    Пустой ответ и ноль — разные вещи, и разводятся здесь, а не в рисовальщике:
    ключа нет — раздела в кадре не будет вовсе; ключ есть и в нём ноль — ноль и
    покажем, потому что «тестов пока нет» это ответ, а не молчание.
    """
    made: list[tuple[str, str]] = []
    for section, key, label in MADE_FIELDS:
        value = (facts.get(section) or {}).get(key)
        if isinstance(value, (int, float)):
            made.append((f"{value:,}".replace(",", "\u2009"), label))
    return made


def project_rules(answer: dict | None) -> dict | None:
    """Чем у проекта держатся правила каталога. ``None`` — он не подключён.

    Доли берутся как есть, вместе с их именами: словарь механизмов чужой и
    растёт — за две недели к четырём значениям добавилось пятое. Свой список
    отстал бы молча, и первым это увидел бы читатель картинки (правило 022).
    """
    if not answer:
        return None
    mechanisms = answer.get("by_mechanism")
    if not isinstance(mechanisms, dict) or not mechanisms:
        return None
    return {
        "answered": answer.get("answered"),
        "trails": answer.get("trails"),
        "mechanisms": {str(k): int(v) for k, v in mechanisms.items() if isinstance(v, int)},
    }


def rules_strip(accent: dict, width: int, dark: bool, label_colour: str) -> list[str]:
    """Полоса «чем держатся правила» и два числа под ней.

    ПРОЕКТ БЕЗ ОТВЕТА НЕ ПРОПУСКАЕТСЯ, А НАЗЫВАЕТСЯ. «Не подключён» и «правил
    ноль» — разные состояния, и пустая полоса читалась бы вторым. Поэтому у
    неподключённого стоит строка словами, а не пустота (правило 046).
    """
    top, left = 250, 36
    right = width - 36
    rules = accent.get("rules")
    # ЗАГОЛОВОК БЛОКА ОБЯЗАТЕЛЕН. Полоса из цветных долей без подписи не
    # объясняет свой предмет: читателю видно, что доли разные, и непонятно,
    # чего именно. Первая редакция ушла на витрину без него — и первым это
    # заметил владелец, а не проверка.
    caption = (f'    <text x="{left}" y="{top - 12}" fill="{label_colour}" '
               f'font-family="{FONT}" font-size="11" font-weight="700" '
               f'letter-spacing="1.2">HOW ITS RULES ARE HELD</text>')
    if not rules:
        return [caption,
                f'    <text x="{left}" y="{top + 16}" fill="{label_colour}" '
                f'font-family="{FONT}" font-size="13" font-weight="600">'
                f'not connected to the rules catalogue yet</text>']

    tones = MECHANISM_TONES["dark" if dark else "light"]
    shares = ordered_mechanisms(rules["mechanisms"])
    total = sum(value for _, value in shares) or 1
    track = right - left
    out: list[str] = []
    offset = left
    for name, value in shares:
        # Полоса делится по долям, но каждая доля видима: механизм с одним
        # правилом из двухсот — тоже ответ, и стереть его в ноль пикселей
        # значило бы показать, что его нет.
        span = max(track * value / total, 3.0)
        out.append(
            f'    <rect x="{offset:.1f}" y="{top}" width="{span:.1f}" height="11" '
            f'rx="5.5" fill="{tones.get(name, tones["_"])}"/>'
        )
        offset += span + 2
    legend = " · ".join(f"{name} {value}" for name, value in shares)
    tail = [f"{rules['answered']} rules answered"] if rules.get("answered") else []
    if rules.get("trails"):
        tail.append(f"{rules['trails']} linked to issues")
    out.insert(0, caption)
    out.append(
        f'    <text x="{left}" y="{top + 32}" fill="{label_colour}" font-family="{FONT}" '
        f'font-size="13" font-weight="600">{escape(legend)}</text>'
    )
    if tail:
        out.append(
            f'    <text x="{right}" y="{top + 32}" fill="{label_colour}" font-family="{FONT}" '
            f'font-size="13" font-weight="600" text-anchor="end">'
            f'{escape(" · ".join(tail))}</text>'
        )
    return out


#: Порог контраста текста — AA по WCAG 2.1 для обычного размера. Крупный текст
#: допускает 3:1, но у витрины крупных подписей нет: числа рисуются 20–26
#: пикселями при 700 весе, и брать для них послабление значило бы гадать о том,
#: как их отмасштабирует читатель.
CONTRAST_AA = 4.5


def contrast(front: str, back: str) -> float:
    """Отношение контраста двух цветов по WCAG 2.1.

    ЗАЧЕМ ЭТО СЧИТАТЬ, А НЕ ПОМНИТЬ. Критерий «контраст в обеих темах не ниже
    AA» объявлен в .rules/roles.md профилем «изображения и доступность», и до 8
    сентября он был проверен РАЗОВО И ВРУЧНУЮ: четыре числа записаны в документ
    и с тех пор не пересчитывались ничем. Палитра при этом живёт в коде и
    правится вместе с карточками — то есть проверенное утверждение и его предмет
    разъезжались бы молча, как всякое число, вписанное руками.

    Формула взята у стандарта дословно и не упрощается: относительная яркость
    считается по каналам с гамма-коррекцией, а не по среднему.
    """
    def luminance(colour: str) -> float:
        parts = [int(colour[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= 0.03928
                  else ((value + 0.055) / 1.055) ** 2.4 for value in parts]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    light, dark = sorted((luminance(front), luminance(back)), reverse=True)
    return (light + 0.05) / (dark + 0.05)

#: Подложки, на которых текст витрины СТОИТ, по темам. Первая в паре — фон
#: страницы профиля: картинка может быть прозрачной, и тогда под текстом
#: окажется именно он.
#:
#: ЗАЧЕМ СПИСОК, А НЕ РАЗБОР ГЕОМЕТРИИ. Какой текст лежит на какой плашке,
#: видно только из координат, а считать их значило бы писать второй рисовальщик.
#: Здесь проще и строже: текст проверяется на КАЖДОЙ подложке своей темы,
#: встретившейся в картинке. Проверка от этого жёстче настоящей вёрстки — и
#: пусть: запас читаемости дешевле разбора координат.
TEXT_BACKS = {
    "dark": ("#0D1117", "#161B22"),
    "light": ("#FFFFFF", "#F6F8FA"),
}

#: Заливки, под текстом не бывающие: клетки года, дорожки полос, доли полосы
#: механизмов, каретка печатающейся строки. Их контраст — вопрос не текста, а
#: графики, и порог у него другой (1.4.11, 3:1).
#:
#: СПИСОК ЗАКРЫТ НАМЕРЕННО, И ЭТО ЕГО ГЛАВНОЕ СВОЙСТВО. Заливка, не названная
#: ни здесь, ни в ``TEXT_BACKS``, роняет сборку с вопросом «подложка или
#: графика?». Так новый цвет получает решение при появлении, а не молча
#: остаётся непроверенным: список, который можно не пополнить, держал бы ровно
#: столько, сколько помнит автор.
ART_FILLS = {
    "dark": frozenset({
        "#21262D",                                          # дорожка полосы, ось тренда
        "#0E4429", "#006D32", "#26A641", "#39D353",         # клетки года
        "#3FB950", "#58A6FF", "#D2A8FF", "#F85149",         # доли полосы механизмов
        "#8B949E", "#6E7681",                               # они же: document и незнакомый
        "#58A6FF22",                                        # заливка под тренда линией
    }),
    "light": frozenset({
        "#EAEEF2", "#EBEDF0",
        "#9BE9A8", "#40C463", "#30A14E", "#216E39",
        "#1A7F37", "#0969DA", "#8250DF", "#CF222E",
        "#8C959F", "#6E7781",
        "#0969DA1A",
    }),
}

#: Текст картинки — вместе с ``tspan``: у плашки показателя значение живёт
#: именно в нём, и своим цветом.
TEXT_TAG = re.compile(r"<(?:text|tspan)\b[^>]*>")
RECT_TAG = re.compile(r"<rect\b[^>]*>")
FILL = re.compile(r'\bfill="([^"]+)"')


def unreadable(name: str, drawing: str) -> list[str]:
    """Текст картинки, не дотягивающий до AA на подложках своей темы.

    ЗАЧЕМ ЭТО МЕХАНИЗМ, А НЕ ЗАМЕР. Критерий «контраст в обеих темах не ниже
    AA» объявлен в .rules/roles.md профилем «изображения и доступность» и до 8
    сентября держался ЧЕТЫРЬМЯ ЧИСЛАМИ, вписанными в документ руками. Палитра
    при этом живёт в коде и правится вместе с карточками: разъехаться им
    негде — они и не встречались.

    ПРОВЕРЯЕТСЯ ПРЕДМЕТ, А НЕ СПИСОК. На вход идёт нарисованная картинка,
    рукодельная или собранная, — то самое, что увидит читатель. Список цветов
    в коде здесь не источник истины, а классификатор: он отвечает только на
    вопрос «это подложка или графика».

    ЧЕГО НЕ ДЕЛАЕТ. Не судит контраст графики (1.4.11) — у неё свой порог и
    свой предмет; не читает координат, поэтому пары «текст на подложке» берутся
    все сразу; не видит цвета, пришедшего градиентом, — и потому такой текст
    отвергает, а не пропускает.
    """
    theme = next((t for t in TEXT_BACKS if name.endswith(f"-{t}")), None)
    if theme is None:
        return [f"{name}: имя картинки не называет тему — на какой подложке "
                f"её читают, отсюда не узнать"]

    found: list[str] = []
    backs = [TEXT_BACKS[theme][0]]
    for tag in RECT_TAG.findall(drawing):
        fill = FILL.search(tag)
        # Заливки нет вовсе, она градиентная или прямо объявлена пустой — под
        # таким прямоугольником остаётся то, что под ним и было: обводка без
        # заливки подложкой не становится.
        if fill is None or fill.group(1).lower() in ("none", "transparent") \
                or fill.group(1).startswith("url("):
            continue
        colour = fill.group(1).upper()
        if colour in TEXT_BACKS[theme]:
            if colour not in backs:
                backs.append(colour)
        elif colour not in ART_FILLS[theme]:
            found.append(f"{name}: заливка {colour} не расписана по ролям — "
                         f"подложка под текстом (TEXT_BACKS) или графика "
                         f"(ART_FILLS)? Пока не сказано, читаемость на ней "
                         f"никто не проверяет")

    for tag in TEXT_TAG.findall(drawing):
        fill = FILL.search(tag)
        if fill is None or not re.fullmatch(r"#[0-9A-Fa-f]{6}", fill.group(1)):
            said = "не задан" if fill is None else f"задан как {fill.group(1)}"
            found.append(f"{name}: цвет текста {said} — посчитать контраст "
                         f"нечем, а незамеченный текст хуже тусклого")
            continue
        colour = fill.group(1).upper()
        for back in backs:
            ratio = contrast(colour, back)
            if ratio < CONTRAST_AA:
                found.append(f"{name}: текст {colour} на подложке {back} даёт "
                             f"{ratio:.2f}:1 при пороге AA {CONTRAST_AA}:1")
    return found


def handmade() -> dict[str, str]:
    """Рукодельные картинки витрины: шапка, печатающаяся строка, разделитель.

    Отличаются они местом, а не видом: собранные с переездом в ветку `assets`
    (правило 160) в дереве больше не лежат, и `assets/*.svg` на диске — ровно
    те, что нарисованы человеком. Отдельного списка имён поэтому нет: список
    можно забыть пополнить, а каталог — нет.
    """
    return {path.stem: path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "assets").glob("*.svg"))}



def svg_open(width: int, height: int, label: str) -> str:
    """Открывающий тег картинки витрины: размер, роль и подпись.

    ВЫНЕСЕНО ПО ТРЕТЬЕМУ СЛУЧАЮ, а их было ПЯТЬ (правило 093). Баннер акцентов,
    плитка проекта, карточка профиля, след технологий и полотно активности
    открывались одной и той же строкой, скопированной пять раз. Обобщение
    заводится с появлением третьего случая — здесь его пропустили дважды.

    ПОДПИСЬ ОБЯЗАТЕЛЬНА, И ЭТО НЕ ПЕДАНТИЗМ. ``alt`` на странице берётся из
    ``aria-label`` самой картинки (::sync_alt), другого источника у него нет.
    Картинка, нарисованная без подписи, оставила бы alt пустым — и молча:
    разметка осталась бы верной, а читатель со скринридером получил бы
    безымянное изображение. Отказ здесь дешевле такого молчания.

    ЧЕГО ШОВ НЕ ДЕЛАЕТ. Он не трогает рукодельные картинки — шапку,
    печатающуюся строку, разделитель: их пишет человек, и у разделителя
    подписи нет НАМЕРЕННО, это декорация. Сборка их не рисует, и через этот
    вход они не проходят.
    """
    if not label.strip():
        raise ValueError("картинка витрины без aria-label: alt на странице "
                         "взять неоткуда, и пустым он станет молча")
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="{escape(label)}">')


def render_featured(accents: list[dict], dark: bool) -> str:
    """Баннер акцентов: по одному проекту за раз, переключение по таймеру.

    Анимация живёт ВНУТРИ картинки, потому что страница профиля — Markdown:
    скриптов там нет. Тот же приём уже носит печатающаяся строка витрины.

    ``prefers-reduced-motion`` уважается: при просьбе уменьшить движение
    показывается первый акцент и не двигается ничего. Без этого баннер был бы
    недоступен ровно тем, кому анимация мешает.

    ВИДИМОСТЬ ЗАДАНА АТРИБУТОМ, А НЕ ТОЛЬКО СТИЛЕМ, и это про отказ. Картинку на
    странице профиля отдаёт прокси площадки, и что именно она делает с блоком
    ``<style>``, отсюда не проверить — печатающаяся строка витрины анимирована
    SMIL, то есть доказательства про CSS у нас нет. Если стиль не доедет, при
    ``opacity`` только в классе все акценты лягут друг на друга и баннер
    превратится в кашу. С атрибутами не доехавший стиль даёт статичную картинку
    с первым акцентом — то есть худший исход остаётся читаемым.

    ССЫЛОК ЗДЕСЬ НЕТ И НЕ БУДЕТ. Внутри картинки, вставленной через ``<img>``,
    ``<a>`` не кликается вовсе. Поэтому пути внутрь проектов остаются текстом
    под баннером: это не «текст лучше», это единственное место, где они
    работают.
    """
    long = [a["title"] for a in accents if len(a["tagline"]) > TAGLINE_LIMIT]
    if long:
        raise SystemExit(
            f"описание не влезает в баннер (потолок {TAGLINE_LIMIT} знаков): {', '.join(long)}.\n"
            "  Сократите tagline в projects.json. Обрезать молча нельзя: урезанная выдача\n"
            "  обязана говорить, что она урезана, а описание — не то место, где это уместно."
        )

    width, height = 1000, 312
    cycle = ACCENT_SECONDS * len(accents)
    if dark:
        card, stroke, name_c, num_c, lab_c = "#0D1117", "#30363D", "#F0F6FC", "#58A6FF", "#7D8590"
    else:
        card, stroke, name_c, num_c, lab_c = "#FFFFFF", "#D0D7DE", "#1F2328", "#0969DA", "#636C76"

    step = 100 / len(accents)
    lines = [
        svg_open(width, height, accent_label(accents)),
        "<style>",
        f"  .accent {{ animation: accent {cycle}s linear infinite; }}",
        "  @keyframes accent {",
        f"    0% {{ opacity: 0 }} {step * 0.06:.2f}% {{ opacity: 1 }}"
        f" {step * 0.94:.2f}% {{ opacity: 1 }} {step:.2f}% {{ opacity: 0 }}"
        " 100% { opacity: 0 }",
        "  }",
        "  @media (prefers-reduced-motion: reduce) {",
        "    .accent { animation: none }",
        "  }",
        "</style>",
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="16" '
        f'fill="{card}" stroke="{stroke}"/>',
    ]
    for index, accent in enumerate(accents):
        lines.append(
            f'  <g class="accent" opacity="{1 if index == 0 else 0}" '
            f'style="animation-delay: {index * ACCENT_SECONDS}s">'
        )
        lines.append(f'    <rect x="36" y="28" width="46" height="4" rx="2" fill="{num_c}"/>')
        lines.append(
            f'    <text x="36" y="68" fill="{name_c}" font-family="{FONT}" font-size="29" '
            f'font-weight="800" letter-spacing="-0.6">{escape(accent["title"])}</text>'
        )
        lines.append(
            f'    <text x="36" y="94" fill="{lab_c}" font-family="{FONT}" font-size="15" '
            f'font-weight="500">{escape(accent["tagline"])}</text>'
        )
        # Показатели: слева направо, каждый своей ширины. Пусто — законное
        # состояние: у молодого проекта показателей может не быть вовсе, и
        # рисовать пустую плашку значило бы врать плашкой.
        offset = 36
        for label, value, tone in accent["badges"]:
            markup, badge_width = pill(offset, 112, label, value, tone, dark)
            lines.append(f"    {markup}")
            offset += badge_width + 8
        lines.append(
            f'    <text x="{width - 36}" y="129" fill="{lab_c}" font-family="{FONT}" '
            f'font-size="12.5" font-weight="600" text-anchor="end">'
            f'{escape(accent["stack"])}</text>'
        )
        numbers = "".join(
            f'<text x="{36 + column * 194}" y="172" fill="{num_c}" font-family="{FONT}" '
            f'font-size="25" font-weight="800">{accent["stats"][field]}'
            f'<tspan fill="{lab_c}" font-size="13.5" font-weight="600" dx="7">{field}</tspan>'
            "</text>"
            for column, field in enumerate(FEATURED_FIELDS)
        )
        lines.append(f"    {numbers}")

        # ВТОРОЙ РЯД — МЕЛКО. Иерархия кеглей, а не стопка блоков: крупные числа
        # остаются крупными, а то, что проект намерил о своей работе, идёт
        # вторым рядом и тише. Раздела нет — строки нет вовсе: «не рассказывает»
        # и «намерил ноль» показываются по-разному.
        if accent.get("made"):
            made = "".join(
                f'<text x="{36 + column * 194}" y="206" fill="{num_c}" font-family="{FONT}" '
                f'font-size="17" font-weight="700">{escape(value)}'
                f'<tspan fill="{lab_c}" font-size="12" font-weight="600" dx="6">'
                f'{escape(label)}</tspan></text>'
                for column, (value, label) in enumerate(accent["made"])
            )
            lines.append(f"    {made}")

        # ТРЕТИЙ БЛОК — ЧЕМ ДЕРЖАТСЯ ПРАВИЛА. Ответ каталога о проекте, а не наша
        # оценка его. Доля «ничем» показывается наравне с остальными и не
        # прячется: правило под гейтом и правило без механизма обязаны быть
        # различимы с одного взгляда — в этом весь смысл блока.
        lines.extend(rules_strip(accent, width, dark, lab_c))
        lines.append("  </g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


#: Обязательные показатели проекта. Список закрыт: показатель, которого здесь
#: нет, не спрашивается, а показатель отсюда обязан получить ответ у КАЖДОГО
#: проекта — бейдж или названную причину. Список — константа, по которой
#: проверяют, а не проза в докстроке: список, написанный и не ставший кодом,
#: витрина уже проходила на гейте меток (правило 068).
BADGE_KINDS = ("release", "ci", "coverage", "version")

#: Как показатель подписан на витрине. Имя ключа и имя на плашке — разные вещи:
#: ключ служебный, подпись читает посетитель. Держатся вместе, иначе показатель
#: без предмета подписывается ключом, а с предметом — как придётся: у витрины
#: так и вышло в первой редакции — «release» рядом с «version none».
BADGE_LABELS = {"release": "release/pypi", "ci": "CI",
                "coverage": "coverage", "version": "version"}


#: По какому слову узнаётся значок показателя. Имя целиком не годится: грейдер
#: публикует покрытие как ``coverage-combined.json``, а каталог правил — как
#: ``coverage.json``. Слово — минимум, который у обоих общий.
BADGE_MARKERS = {"coverage": "coverage", "version": "version"}


def _badge_files(repo: str, kind: str) -> list[str]:
    """Значки ПОКАЗАТЕЛЯ — в обеих ветках, где их кладут. Пусто — значка нет.

    ПОКАЗАТЕЛЬ, А НЕ «ЛЮБОЙ ЗНАЧОК». Прежняя версия фильтровала имена по слову
    ``coverage`` — всегда, каким бы ни был показатель, — и вызывалась в том
    числе проверкой версии. То есть на вопрос «публикует ли сосед версию»
    отвечала находкой файла ПОКРЫТИЯ. В докстроке при этом стояло «значок
    версии»: список был в прозе, а в коде — одно слово из двух.

    ОБЕ ВЕТКИ, А НЕ ОДНА. Значок кладут либо на отдельную ``badges``, либо
    рядом с кодом; спрашивать одну значит пропускать половину случаев.

    404 — законный ответ «такого каталога нет», а не сбой: у большинства
    репозиториев значков не бывает вовсе. Остальные коды поднимаются, иначе
    молчаливый except спрячет сеть и права (правило 039).
    """
    marker = BADGE_MARKERS[kind]
    found: list[str] = []
    for ref in ("?ref=badges", ""):
        try:
            entries = _api(f"/repos/{repo}/contents/.github/badges{ref}")
        except urllib.error.HTTPError as absent:
            if absent.code != 404:
                raise
            continue
        for entry in entries:
            if entry["type"] != "file" or marker not in entry["name"]:
                continue
            # ИМЯ НЕ ДОКАЗЫВАЕТ, ЧТО ЭТО ЗНАЧОК. У глоссария `coverage.json`
            # четыре часа был shields-значком «99.2%», а потом стал отчётом о
            # том, какая доля официального Python покрыта карточками, — другой
            # предмет под тем же именем. Значок опознаётся полем `message`,
            # которое shields и читает; ошибка чтения — «не значок», а не сбой:
            # чужой файл вправе быть чем угодно.
            path = f".github/badges/{entry['name']}" + ("?ref=badges" if ref else "")
            try:
                payload = _api(f"/repos/{repo}/contents/{path}")
                if "message" in json.loads(base64.b64decode(payload["content"])):
                    found.append(entry["name"])
            except (urllib.error.HTTPError, ValueError, KeyError):
                continue
    return sorted(set(found))


def verify_absence(repo: str, kind: str, why: str) -> str:
    """Находка, если «предмета нет» — неправда. Пусто — ответ верен.

    ВОЗВРАЩАЕТ, А НЕ ПАДАЕТ, И ЭТО ГЛАВНАЯ ПРАВКА. Прежде отказ здесь ронял
    сборку целиком: 5–7 сентября витрина трое суток не пересчитывалась, потому
    что глоссарий вернул значок покрытия на место и наш ответ «значка нет»
    устарел. Правка на той стороне была ВЕРНОЙ — а встали пересчёт всех
    тридцати чисел, публикация картинок и сторож свежести.

    Цена несоразмерна предмету: неверная плашка одного проекта не делает
    неверными остальные числа и не мешает их пересчитать. Находка красит
    проверку изменения, где её чинит окно; суточная сборка её печатает и
    досчитывает (правило 039 — исходов три, и «данные разошлись» не равно
    «сборка сломалась»).

    Отказ по показателю — такое же утверждение о чужом репозитории, как число,
    вписанное руками, и устаревает он так же молча. Так и вышло: у каталога
    правил в ответе стояло «релизов нет», а релиз был — просто помеченный
    предварительным, и `releases/latest` его не показывал. Страница получила
    плашку «release none» рядом с числом «1 releases» в одном кадре.

    Проверяется только однозначное. Пакет сюда не входит: имя пакета при отказе
    не объявлено, а искать его по имени репозитория значит ловить чужой пакет с
    похожим названием — ложный отказ дороже пропуска (правило 051). Пробел
    назван здесь, а не выровнен.
    """
    if kind == "release":
        if _api(f"/repos/{repo}/releases?per_page=1"):
            found = "выпуски есть, хотя бы один — возможно, предварительный"
        else:
            return ""
    elif kind == "ci":
        # НАЗВАННОЕ ИСКЛЮЧЕНИЕ, А НЕ ЛЮБОЕ. «Прогонов нет вовсе» перестало быть
        # верным у Claude-Code_Usage-Token 28 августа: сосед подключился к каталогу
        # правил, и у него завёлся rules-inbox — синхронизация, а не проверка
        # кода. Утверждение «CI нет» при этом осталось верным по сути и стало
        # ложным по букве.
        #
        # Гейт не судит, ЧТО делает чужой прогон: это чтение смысла. Он требует
        # назвать исключения ПОИМЁННО в самой причине и сверяет, что других нет.
        # Появится у соседа настоящий CI — имени его в причине не окажется, и
        # ответ покраснеет, как и должен (правило 158: отказ называет предмет).
        names = {w["path"].rsplit("/", 1)[-1]
                 for w in _api(f"/repos/{repo}/actions/workflows").get("workflows", [])}
        unnamed = {name for name in names if name not in why}
        if unnamed:
            found = f"прогоны в репозитории есть и в причине не названы: {', '.join(sorted(unnamed))}"
        else:
            return ""
    elif kind in BADGE_MARKERS:
        # ЗНАЧОК, А НЕ ВЕТКА. Прежде отказ выносился по существованию ветки
        # `badges`: раз она есть — «показатель публикуется». Ветка общая на все
        # показатели, и у первого же соседа, который завёл её ради одного из
        # них, ответ покраснел бы по всем четырём. Так и вышло у глоссария
        # 4 сентября: ветка появилась вместе с покрытием и фактами, версии в
        # ней нет и не планируется, а гейт требовал бы её ровно так же.
        #
        # Обе площадки, а не одна: с тех пор как значок научились класть рядом
        # с кодом, вопрос только к `badges` пропускал бы ровно тот случай, ради
        # которого проверка написана. Так вышло у каталога правил: покрытие
        # появилось в main, а ответ витрины ещё говорил «тестов нет».
        #
        # Версия попадает сюда тем же путём, что и покрытие. До 27 августа
        # непроверяемым здесь был «пакет» — у него при отказе не объявлено имя,
        # и спросить PyPI не о чем. Пакет теперь входит в «release», и его
        # отсутствие проверяется выпусками площадки.
        published = _badge_files(repo, kind)
        if published:
            found = f"значок публикуется: {', '.join(published)}"
        else:
            return ""
    else:
        return ""

    return (f"{repo}: ответ по показателю «{kind}» неверен. Записано: {why}. "
            f"На деле: {found}. Отказ — утверждение о чужом репозитории, и "
            f"устаревает он молча; замените «none» на источник значения либо "
            f"исправьте причину")


def latest_tag(repo: str) -> str | None:
    """Тег последнего выпуска, либо ``None``.

    ``releases/latest`` не видит черновиков и предварительных выпусков: у
    каталога правил единственный релиз был помечен предварительным, и эндпойнт
    отдавал 404 при существующем выпуске. Отсюда запасной путь по полному
    списку — иначе плашка говорила бы «нет выпусков» рядом с числом «1 releases»
    в той же картинке.
    """
    try:
        tag = _api(f"/repos/{repo}/releases/latest").get("tag_name")
    except urllib.error.HTTPError as absent:
        # 404 — не сбой, а «нет выпуска, который площадка считает последним».
        # Отличать от настоящей ошибки обязательно: молчаливый except спрятал бы
        # сеть и права (правило 039).
        if absent.code != 404:
            raise
        tag = None
    if tag:
        return tag
    releases = _api(f"/repos/{repo}/releases?per_page=1")
    return releases[0]["tag_name"] if releases else None


def owns_package(repo: str, info: dict) -> bool:
    """Ведёт ли пакет обратно на этот репозиторий.

    ИМЯ — НЕ ДОКАЗАТЕЛЬСТВО ПРИНАДЛЕЖНОСТИ, и это оплачено. В ответе соседа
    ``Claude-Code_Usage-Token`` стояло ``{"pypi": "claude-code-usage"}``, и на
    витрине месяц висело «release/pypi **2.0.0**». Пакет с таким именем на PyPI
    есть — только он чужой (``Maex-z9/CC_Usage``, автор Max), а у соседа
    собственный выпуск ``v0.2.0``. Ошибка не выглядела ошибкой ни секунды:
    правдоподобное число рядом с правдоподобным именем.

    Проверка идёт ОБРАТНОЙ ссылкой: у пакета в метаданных объявлен репозиторий,
    и он обязан совпасть с тем, о ком витрина рассказывает. Односторонняя связь
    «мы назвали имя» доказывает только то, что имя занято — кем угодно.

    Регистр не важен: PyPI отдаёт ссылки как их вписал издатель, а github.com
    к регистру владельца и имени безразличен.

    СРАВНИВАЕТСЯ СЕГМЕНТ ПУТИ, А НЕ ПОДСТРОКА. Первая редакция искала
    ``github.com/o/r`` вхождением — и признавала своим ``github.com/o/r-fork``,
    то есть ровно тот класс чужого, ради которого проверка и написана. Дефект
    нашёлся подделкой в наборе, а не в жизни (правило 166: проверяя ссылку,
    ищут ссылку).
    """
    links = [info.get("home_page") or ""]
    links += [str(link) for link in (info.get("project_urls") or {}).values()]
    # Хвост сегмента: конец строки, следующий сегмент пути, `.git`, якорь или
    # параметры. Дефис и буква — уже другое имя репозитория.
    pattern = re.compile(rf"github\.com/{re.escape(repo)}(?:[/#?.]|$)", re.I)
    return any(pattern.search(link) for link in links)


def pypi_version(repo: str, package: str) -> str:
    """Версия пакета в PyPI — но только если пакет принадлежит репозиторию.

    Источник чужой и объявлен ответом проекта; принадлежность проверяется, а не
    принимается на веру (правило 146: не утверждать того, чего не проверяешь).
    """
    url = f"https://pypi.org/pypi/{package}/json"
    with naming(url), urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "artvsmark-profile"}),
        timeout=30,
    ) as response:
        info = json.loads(response.read())["info"]
    if not owns_package(repo, info):
        raise SystemExit(
            f"{repo}: пакет «{package}» на PyPI не ведёт обратно на этот репозиторий.\n"
            f"  Пакет ссылается на: {info.get('project_urls') or info.get('home_page') or '—'}\n\n"
            "  Совпадения имени мало: чужой пакет с похожим названием даёт\n"
            "  правдоподобное число, и отличить его от своего читатель не может.\n"
            "  Уберите «pypi» из ответа либо назовите пакет, который объявляет\n"
            "  этот репозиторий своим."
        )
    return info["version"]


#: Поле контракта фактов, отвечающее за показатель. Читается, когда значка у
#: соседа нет: контракт `.rules/facts-contract.md` объявил `coverage_percent`
#: ровно для этого. У «version» и «release» полей нет — их публикуют значком
#: или выпуском площадки, и выдумывать им поле значило бы просить у соседей
#: работу, которой контракт не предусматривал.
FACTS_FIELD = {"coverage": "coverage_percent"}


def neighbour_facts(repo: str) -> tuple[dict, str]:
    """Факты соседа и находка о них. Оба пустые — фактов нет, и это законно.

    ОТЛИЧАЕТСЯ ОТ ``grader_facts`` ПРЕДМЕТОМ, А НЕ ВЕЖЛИВОСТЬЮ. Грейдер —
    ИЗДАТЕЛЬ чисел витрины: без его фактов страницу собирать не из чего, и
    отказ там законный. Сосед — участник таблицы: его факты дополняют показ, и
    их отсутствие — состояние проекта, а не поломка сборки (правило 039).

    Несовместимый мажор тоже находка, а не отказ: чужой проект вправе поднять
    свой формат, не спросив нас, и ронять из-за этого ВСЮ витрину — цена,
    несоразмерная предмету.
    """
    try:
        payload = _api(f"/repos/{repo}/contents/{FACTS_PATH}?ref=badges")
        facts = json.loads(base64.b64decode(payload["content"]))
    except urllib.error.HTTPError as absent:
        if absent.code != 404:
            raise
        return {}, ""
    except (ValueError, KeyError) as broken:
        return {}, f"{repo}: facts.json не разобран ({broken}) — показатели взяты без него"
    schema = str(facts.get("schema", ""))
    if schema.split(".")[0] != FACTS_SCHEMA:
        return {}, (f"{repo}: facts.json объявляет схему {schema!r}, витрина умеет "
                    f"{FACTS_SCHEMA}.x — файл не читается, показатели взяты без него")
    return facts, ""


def badge_value(repo: str, answer: dict) -> str:
    """Значение значка проекта. Две формы ответа, и обе законны:

    ``{"endpoint": "имя"}`` — значок на отдельной ветке ``badges``. Так делают
    и грейдер, и каталог правил: их CI считает число и коммитит результат мимо
    общей ветки. ``{"badge": "имя"}`` — значок в ветке по умолчанию, рядом с
    кодом.

    ФОРМУ ``badge`` СЕЙЧАС НЕ ИСПОЛЬЗУЕТ НИКТО, и это названо, а не оставлено
    умолчанием. Она заведена под каталог правил, который держал покрытие в
    общей ветке; 27 августа он унёс значки на ``badges`` окончательно
    (playbook#144), и витрина узнала об этом отказом 404 в суточной сборке.
    Форма оставлена: она законна, покрыта самопроверкой и понадобится первому
    же проекту, который положит значок рядом с кодом.

    Одну форму на обе площадки не свести: у них разный ``ref``, и угадывать его
    перебором значило бы прятать ошибку в данных за второй попыткой.

    Читается через contents-API, а НЕ через ``raw.githubusercontent.com``: raw
    отвечает 404 на запрос с заголовком ``Authorization``.
    """
    if "badge" in answer:
        path = f".github/badges/{answer['badge']}.json"
    else:
        path = f".github/badges/{answer['endpoint']}.json?ref=badges"
    payload = _api(f"/repos/{repo}/contents/{path}")
    body = json.loads(base64.b64decode(payload["content"]))
    if "message" not in body:
        # ОТКАЗ НАЗЫВАЕТ ПРЕДМЕТ (правило 158). Голый KeyError печатался как
        # «источник не ответил — 'message'»: ни репозитория, ни файла, ни того,
        # что искали. Чинить по такому отказу нечего, а случай живой — сосед
        # переиспользовал имя `coverage.json` под другой предмет.
        raise SystemExit(
            f"{repo}: файл {path.split('?')[0]} есть, но значком не является — "
            f"в нём нет поля «message», которое читает shields.\n"
            f"  Ключи файла: {', '.join(sorted(body)) or '—'}\n\n"
            "  Имя файла не доказывает, ЧТО в нём лежит. Либо назовите другой\n"
            "  значок, либо ответьте «none» с причиной.")
    return body["message"]


def live_value(repo: str, kind: str, answer: dict, facts: dict,
               findings: list[str]) -> str | None:
    """Что источники говорят о показателе ПРЯМО СЕЙЧАС. ``None`` — не говорят ничего.

    ВИТРИНА СПРАШИВАЕТ, А НЕ ПОМНИТ — В ЭТОМ ВЕСЬ СМЫСЛ ФУНКЦИИ. Раньше форма
    ответа хранилась в projects.json: `{"endpoint": "coverage"}` против
    `{"none": "причина"}`. Это КОПИЯ ЧУЖОГО ОПРЕДЕЛЕНИЯ — того самого, которое
    витрина запретила держать у себя, когда писала соседям контракт фактов
    (правило 174). Копия верна до первой правки на той стороне и расходится
    молча; за трое суток сентября она разошлась ДВАЖДЫ, и оба раза уронила
    сборку.

    Порядок источников — от точного к общему, и каждый шаг проверяем:

    1. **имя, названное в ответе** (`endpoint`/`badge`) — если сосед публикует
       значок под нестандартным именем, как `coverage-combined` у грейдера;
    2. **значок, найденный по слову показателя** — сосед завёл его сам, ответа
       у витрины про это нет;
    3. **поле контракта фактов** — `coverage_percent`, ровно то, ради чего
       контракт и писался: издатель считает, потребитель читает;
    4. ничего из этого — ``None``, и решение остаётся за записанным ответом.

    ОШИБКА ЧТЕНИЯ НА ЛЮБОМ ШАГЕ — НЕ ИСКЛЮЧЕНИЕ, А СЛЕДУЮЩИЙ ШАГ. Чужой файл
    вправе исчезнуть, переехать или сменить предмет; падать на этом значит
    отдавать чужому проекту право останавливать нашу сборку.
    """
    named = answer.get("endpoint") or answer.get("badge")
    if named:
        try:
            return badge_value(repo, answer)
        except (urllib.error.HTTPError, ValueError, KeyError, SystemExit):
            # Имя, объявленное витриной, больше не читается. Отступить молча
            # нельзя: следующий шаг найдёт значение, показатель окажется на
            # месте, и МЁРТВОЕ ИМЯ В projects.json переживёт этот прогон и все
            # следующие — ровно тем способом, каким устаревают утверждения о
            # чужих репозиториях (правило 151: молчаливый обход неотличим от
            # исправного пути).
            findings.append(
                f"{repo}: значок «{named}», объявленный в projects.json, не читается. "
                f"Витрина ищет показатель «{kind}» сама; уберите имя или поправьте его")
    for name in _badge_files(repo, kind) if kind in BADGE_MARKERS else []:
        try:
            return badge_value(repo, {"endpoint": name.removesuffix(".json")})
        except (urllib.error.HTTPError, ValueError, KeyError, SystemExit):
            continue
    field = FACTS_FIELD.get(kind)
    if field and facts.get(field) is not None:
        value = facts[field]
        # Число из фактов — доля, а не готовая надпись: единицу дописывает
        # витрина, потому что показывает её она.
        return f"{value}%" if isinstance(value, (int, float)) else str(value)
    return None


def project_badges(repo: str, answers: dict,
                   findings: list[str] | None = None) -> list[tuple[str, str, str]]:
    """Показатели проекта значениями, а не чужими картинками.

    Раньше здесь стояли бейджи ``img.shields.io`` — четыре внешние картинки на
    проект. Отказались от них по трём причинам, и ни одна не про красоту:

    * **числа и так измерены нами.** Просить чужой сервис сходить за версией,
      которую сборка уже знает, значит завести второй источник того же числа —
      два места, где оно может разойтись;
    * **проверить их из окна нельзя.** Прокси окна не пускает этот хост, и
      живой бейдж от опечатки в ссылке отсюда неотличим. Утверждение, которое
      нельзя проверить, витрина на себя не берёт;
    * **чужой хост — это чужая доступность.** Картинка, которая однажды не
      отрисуется, выглядит как сломанная страница, а не как чужой сбой.

    Тон значения — не украшение: он говорит то, чего не говорит само значение.
    Красный «CI failing» читается с расстояния, зелёный «passing» — тоже.

    НАХОДКИ О СОСЕДЯХ СКЛАДЫВАЮТСЯ В ``findings``, А НЕ РОНЯЮТ СБОРКУ. Ответ
    витрины о чужом репозитории устаревает от чужой правки, и цена отказа здесь
    несоразмерна: неверная плашка одного проекта не делает неверными остальные
    тридцать чисел и не мешает их пересчитать. Красным они становятся на
    проверке изменения (``--check``), где чинит их окно.
    """
    if findings is None:
        findings = []
    badges: list[tuple[str, str, str]] = []
    facts, facts_finding = neighbour_facts(repo)
    if facts_finding:
        findings.append(facts_finding)
    for kind in BADGE_KINDS:
        answer = answers.get(kind, {})
        if "none" in answer:
            # ОТВЕТ «ПРЕДМЕТА НЕТ» БОЛЬШЕ НЕ ВЕРЯТ НА СЛОВО — И НЕ РОНЯЮТ ИМ
            # СБОРКУ. Живой источник сильнее записанного ответа: если сосед
            # начал публиковать показатель, витрина покажет ЕГО, а устаревшая
            # причина станет находкой для проверки изменения.
            #
            # Прежде порядок был обратный: ответ считался истиной, расхождение
            # — отказом сборки. Три дня простоя 5–7 сентября это и есть цена
            # такого порядка: глоссарий вернул значок покрытия на место, наш
            # ответ «значка нет» устарел, и встали пересчёт всех тридцати
            # чисел, публикация картинок и сторож свежести — из-за правки,
            # которая на той стороне была верной.
            found = live_value(repo, kind, answer, facts, findings)
            if found is None:
                # Значка нет — но «предмета нет» могло устареть и по другому
                # признаку: у выпусков это релиз площадки, у CI — заведшийся
                # прогон, и значением они не отдаются. Плашка остаётся «none»,
                # находка едет к проверке изменения.
                stale = verify_absence(repo, kind, answer["none"])
                if stale:
                    findings.append(stale)
                # Плашка остаётся и говорит «none». Пропустить её значило бы
                # показать четыре показателя у одного проекта и один у другого
                # — читатель достроит недостающее сам, и достроит в сторону
                # «просто не показали». «Предмета нет» и «не дошли руки» так
                # снова склеиваются, а ради их различия ответ и заводился.
                # Причина остаётся в projects.json: она по-русски и служебная,
                # а витрину читает англоязычный посетитель.
                badges.append((BADGE_LABELS[kind], "none", "muted"))
                continue
            findings.append(
                f"{repo}: ответ по показателю «{kind}» устарел — записано «предмета "
                f"нет», а источник отдаёт {found!r}. Витрина показывает источник; "
                f"уберите «none» из projects.json")
            badges.append((BADGE_LABELS[kind], found, "info"))
            continue
        if kind == "release":
            # ВЫПУСК И ПАКЕТ — ОДНА ПЛАШКА, И ЭТО НЕ ЭКОНОМИЯ МЕСТА. Раньше их
            # было две: «release v1.11.0» из выпусков площадки и «pypi 1.11.0»
            # из PyPI. Одно и то же число дважды, и витрина при этом УТВЕРЖДАЛА
            # их равенство самим соседством плашек — утверждение, которого она
            # проверить не может: разойдись они, читатель увидел бы противоречие
            # и не понял, какому верить.
            #
            # Теперь равенство утверждает проект, а не витрина: грейдер и каталог
            # публикуют собственный значок `release`, где их CI сводит выпуск и
            # пакет в одно значение. Витрина только показывает, что ей сказали
            # (правило 146: не утверждать того, чего не проверяешь).
            #
            # Три источника, потому что проекты в разной зрелости, и требовать
            # от всех значок значило бы требовать невозможного (051):
            #   {"endpoint"|"badge": имя} — собственный значок проекта;
            #   {"release": true}         — выпуски площадки, пока значка нет;
            #   {"pypi": имя}             — версия пакета, пока нет выпусков.
            if "endpoint" in answer or "badge" in answer:
                badges.append((BADGE_LABELS["release"], badge_value(repo, answer), "info"))
            elif "pypi" in answer:
                badges.append((BADGE_LABELS["release"], pypi_version(repo, answer["pypi"]), "info"))
            else:
                badges.append((BADGE_LABELS["release"], latest_tag(repo) or "—",
                               "info" if latest_tag(repo) else "muted"))
        elif kind == "ci":
            runs = _api(
                f"/repos/{repo}/actions/workflows/{answer['workflow']}"
                "/runs?branch=main&status=completed&per_page=1"
            ).get("workflow_runs", [])
            state = runs[0]["conclusion"] if runs else "unknown"
            badges.append((BADGE_LABELS["ci"], state, "ok" if state == "success" else "warn"))
        elif kind == "coverage":
            # Объявленный значок мог исчезнуть — сосед вправе переложить его или
            # сменить предмет файла, и это его дело. Витрина отступает к фактам,
            # потом к «none» с находкой, но НЕ падает: чужая перекладка не
            # обязана останавливать пересчёт остальных чисел (039).
            value = live_value(repo, kind, answer, facts, findings)
            if value is None:
                findings.append(
                    f"{repo}: объявленный значок «{kind}» не читается, и в facts.json "
                    f"поля {FACTS_FIELD.get(kind)!r} нет. Витрина показывает «none» — "
                    f"поправьте ответ в projects.json либо спросите соседа")
                badges.append((BADGE_LABELS[kind], "none", "muted"))
            else:
                badges.append((BADGE_LABELS["coverage"], value, "ok"))
        else:
            # Версия — не то же, что выпуск: у грейдера выпуск «1.11», а версия
            # «1.11.60». Первое — серия, которую видит пользователь пакета,
            # второе — конкретная сборка. Показывать одно вместо другого значило
            # бы терять то, что проект о себе говорит.
            badges.append((BADGE_LABELS["version"], badge_value(repo, answer), "info"))
    return badges


def pill(x: int, y: int, label: str, value: str, tone: str, dark: bool) -> tuple[str, int]:
    """Один показатель: подпись и значение в скруглённой плашке.

    Ширина считается по числу знаков, а не измеряется: шрифта у нас нет, и
    измерить его нечем. Коэффициент подобран так, чтобы текст не упирался в
    край при самом широком значении, — запас лучше обрезки.
    """
    if dark:
        back, edge, muted = "#161B22", "#30363D", "#8B949E"
        tones = {"ok": "#3FB950", "warn": "#F85149", "info": "#58A6FF", "muted": "#8B949E"}
    else:
        back, edge, muted = "#F6F8FA", "#D0D7DE", "#636C76"
        tones = {"ok": "#1A7F37", "warn": "#CF222E", "info": "#0969DA", "muted": "#636C76"}

    label_w = len(label) * 6.4
    value_w = len(value) * 6.9
    width = int(13 + label_w + 7 + value_w + 13)
    svg = (
        f'<g><rect x="{x}" y="{y}" width="{width}" height="24" rx="12" '
        f'fill="{back}" stroke="{edge}"/>'
        f'<text x="{x + 13}" y="{y + 16}" fill="{muted}" font-family="{FONT}" '
        f'font-size="12" font-weight="600">{escape(label)}'
        f'<tspan fill="{tones[tone]}" font-weight="700" dx="7">{escape(value)}</tspan>'
        f"</text></g>"
    )
    return svg, width


def check_badges(config: dict) -> None:
    """Ответ по каждому обязательному показателю есть у каждого проекта.

    Обязателен не бейдж, а ОТВЕТ. Требовать бейдж значило бы требовать
    невозможного: у текстового репозитория нет покрытия, у неопубликованного —
    версии на PyPI, и красное на этом было бы ложным отказом (правило 051).
    Требовать нечего — но молчать нельзя: «у нас этого нет по такой-то причине»
    и «мы не дошли» выглядят одинаково ровно до тех пор, пока их не развели.

    Пустая причина считается отсутствием ответа: строка-заглушка удобна тем,
    что закрывает гейт, ничего не сказав.
    """
    required = config.get("required_badges", list(BADGE_KINDS))
    unknown = set(required) - set(BADGE_KINDS)
    if unknown:
        raise SystemExit(
            f"projects.json: обязательными объявлены показатели, которых сборка не умеет: "
            f"{', '.join(sorted(unknown))}. Умеет: {', '.join(BADGE_KINDS)}"
        )

    complaints = []
    for project in config["projects"]:
        answers = project.get("badges", {})
        for kind in required:
            answer = answers.get(kind)
            if not isinstance(answer, dict) or not answer:
                complaints.append(f"{project['title']}: нет ответа по показателю «{kind}»")
                continue
            if "none" in answer and not str(answer["none"]).strip():
                complaints.append(f"{project['title']}: «{kind}» отклонён без причины")
        for kind in set(answers) - set(BADGE_KINDS):
            complaints.append(f"{project['title']}: показатель «{kind}» сборке неизвестен")

    if complaints:
        raise SystemExit(
            "обязательные показатели проектов не отвечены:\n"
            + "\n".join(f"  • {line}" for line in complaints)
            + "\n\n  У каждого проекта по каждому показателю обязан быть ответ: бейдж или"
            "\n  причина, почему предмета нет. Пустого ответа не бывает — «у нас этого нет»"
            "\n  и «мы не дошли» это разные вещи."
        )


def slug(repo: str) -> str:
    """Имя файла плитки. Только строчные и дефис — по этому виду их находят
    и подпись, и отпечаток содержимого.

    Подчёркивание приводится к дефису, а не оставляется как есть: 2 сентября
    сосед переименовался в `Claude-Code_Usage-Token`, и плитка получила бы имя
    `tile-claude-code_usage-token-dark.svg` — вперемешку. Утверждение в этой
    докстроке было бы неправдой, а неправда о своём же коде дороже лишней
    строки.
    """
    return repo.split("/")[1].lower().replace("_", "-")


def render_tile(project: dict, dark: bool) -> str:
    """Плитка проекта — кнопка, а не витрина показателей.

    Зачем отдельная картинка на проект: у одной картинки может быть только одна
    ссылка, а баннер крутится по четырём. Клик по кадру с одним проектом,
    ведущий на другой, — враньё, поэтому баннер ведёт «во все репозитории», а
    переход в конкретный проект даёт эта плитка.

    Внутри самой плитки ссылки нет и быть не может: ``<a>`` внутри картинки,
    вставленной через ``<img>``, не кликается. Кликается ОБЁРТКА — ссылка вокруг
    картинки в разметке страницы. Отсюда правило: одна плитка — один адрес.

    Ни показателей, ни стека здесь нет намеренно: они в баннере. Повторять их
    значило бы завести второе место, где одно и то же может разойтись, — и
    первая редакция это подтвердила сразу: стек грейдера в плитку не влез и
    обрезался краем. Плитка — кнопка, а кнопке подпись не нужна.
    """
    width, height = 246, 68
    if dark:
        card, stroke, name_c, mark = "#0D1117", "#30363D", "#F0F6FC", "#58A6FF"
    else:
        card, stroke, name_c, mark = "#FFFFFF", "#D0D7DE", "#1F2328", "#0969DA"

    title = project["title"]
    # Кегль подбирается под длину: имена проектов различаются вдвое, и единый
    # кегль либо мельчит короткие, либо упирает длинные в стрелку.
    size = 16 if len(title) <= 20 else 14
    # Подпись описывает ДЕЙСТВИЕ, а не картинку: плитка — кнопка, и читателю
    # экрана важно, куда она ведёт, а не как выглядит.
    label = f"Open {title} on GitHub"
    return "\n".join([
        svg_open(width, height, label),
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" '
        f'fill="{card}" stroke="{stroke}"/>',
        f'<rect x="18" y="20" width="26" height="3" rx="1.5" fill="{mark}"/>',
        f'<text x="18" y="49" fill="{name_c}" font-family="{FONT}" font-size="{size}" '
        f'font-weight="800" letter-spacing="-0.3">{escape(title)}</text>',
        f'<text x="{width - 18}" y="49" fill="{mark}" font-family="{FONT}" font-size="16" '
        f'font-weight="800" text-anchor="end">&#8594;</text>',
        "</svg>",
    ]) + "\n"


#: Карточки профиля рядами: имя картинки и её доля ширины. Ряд рисуется целиком
#: или не рисуется вовсе — вместе со своим разделителем.
#:
#: ПОРЯДОК И ШИРИНА ЖИВУТ ЗДЕСЬ, а не в разметке README. До 8 сентября они жили
#: в двух местах: `width="48%"` руками на странице и `width=492` в коде, который
#: рисует саму картинку. Разъезжались они молча — 7 сентября карточка шириной
#: 1000 точек оказалась сжата до 48%, и шесть чисел встали тремя колонками
#: вместо двух.
PROFILE_ROWS = ((("engineering", "48%"), ("stack", "48%")),
                (("activity", "92%"),))


def render_profile_cards(drawn: dict[str, str]) -> str:
    """Блок карточек профиля — из тех картинок, что сборка НАРИСОВАЛА.

    ЗАЧЕМ СБОРКОЙ, А НЕ РУКОЙ. Ссылку добавлял человек, а картинку рисует
    прогон, и между этими двумя моментами страница показывает сломанное. 7
    сентября так вышло дважды за смену, в одном файле, одним автором: README
    получил ссылки на четыре картинки, которых в ветке ещё не было, а следом
    пятую. Оба раза чинилось запуском прогона руками — а у окна на это 403.

    ПОЧЕМУ ИМЕННО «НАРИСОВАННЫЕ», А НЕ «ОБЪЯВЛЕННЫЕ». Публикация ЗАМЕНЯЕТ ветку
    ``assets`` целиком: `ghaction-github-pages` выкладывает каталог как есть, и
    картинки, которую сборка в этот раз не нарисовала, в ветке не остаётся. Это
    проверяется глазами — в ветке ровно шестнадцать файлов, и следов удалённой
    плитки в ней нет. Значит ссылка на ненарисованное — это ссылка в пустоту, и
    единственный способ не показать битую картинку — не написать ссылку.

    Отсюда и обратное свойство, ради которого задача заводилась: новая карточка
    появляется на странице САМА, а исчезнувшая исчезает вместе со своим рядом, а
    не остаётся битой ссылкой.

    ГРАНИЦА. Рукодельные картинки — шапка, печатающаяся строка, разделитель —
    сюда не попадают: их пишет человек, и сборка их не рисует. Подпись под
    блоком тоже остаётся прозой: она объясняет, а не перечисляет.

    ``alt`` и отпечаток против кэша проставляются позже, общим проходом
    (``sync_alt`` и ``stamp_assets``), — здесь их писать нельзя, иначе у
    подписи появилось бы второе место.
    """
    block: list[str] = []
    for row in PROFILE_ROWS:
        # КАРТОЧКА ПОКАЗЫВАЕТСЯ, ТОЛЬКО ЕСЛИ НАРИСОВАНЫ ОБЕ ТЕМЫ. Половина —
        # это `<picture>` с живой тёмной и битой светлой (или наоборот), то есть
        # ровно тот сломанный показ, ради которого блок и собирается сборкой.
        # Сегодня цикл рисует темы парой, и условие проверяет намерение, а не
        # сегодняшнюю реализацию.
        shown = [(name, width) for name, width in row
                 if f"{name}-dark" in drawn and f"{name}-light" in drawn]
        if not shown:
            continue
        if block:
            block += ["", "<br><br>", ""]
        for name, width in shown:
            block += [
                "<picture>",
                f'  <source media="(prefers-color-scheme: dark)" '
                f'srcset="./assets/{name}-dark.svg">',
                f'  <source media="(prefers-color-scheme: light)" '
                f'srcset="./assets/{name}-light.svg">',
                f'  <img src="./assets/{name}-dark.svg" alt="" width="{width}">',
                "</picture>",
            ]
    if not block:
        # НИ ОДНОЙ КАРТОЧКИ НЕ НАРИСОВАНО — это исход, а не пустая строка.
        # Молчаливо пустой блок неотличим от блока, который забыли собрать.
        return "\n\n<sub>Profile cards are not available: every source declined.</sub>\n\n"
    return "\n\n" + "\n".join(block) + "\n\n"


def render_projects(config: dict) -> str:
    """Ряд кликабельных плиток: по плитке на проект, каждая — ссылка.

    Текстового списка здесь больше нет. Он существовал ровно затем, что ссылка
    внутри картинки не работает; плитки решают это иначе — ссылкой ВОКРУГ
    картинки, по одной на проект. Тогда клик ведёт туда, что видишь, а не туда,
    что выпало на общий адрес.

    Глубоких ссылок под плитками нет: PyPI и быстрый старт дублировали блок
    установки, который стоит абзацем ниже и даёт ровно то, за чем посетитель
    туда шёл, — команду. История же в одном клике от репозитория, куда ведёт
    сама плитка. Поле ``links`` в данных убрано вместе со строкой: данные,
    которые никто не читает, устаревают молча, как и всё прочее.

    Показываются первые ``featured_limit``. Остаток не пропадает молча — под
    плитками сказано, сколько проектов не показано и где они лежат.
    """
    limit = config["featured_limit"]
    projects = config["projects"]
    activity = {project["repo"]: repo_activity(project["repo"]) for project in projects}

    ordered = sorted(projects, key=lambda project: activity[project["repo"]], reverse=True)
    ordered.sort(key=lambda project: not project.get("pin", False))  # сортировка стабильна
    featured, hidden = ordered[:limit], ordered[limit:]

    rows = ['<div align="center">', ""]
    for project in featured:
        name = slug(project["repo"])
        rows += [
            f'<a href="https://github.com/{project["repo"]}">'
            f'<picture>'
            f'<source media="(prefers-color-scheme: dark)" srcset="./assets/tile-{name}-dark.svg">'
            f'<source media="(prefers-color-scheme: light)" srcset="./assets/tile-{name}-light.svg">'
            f'<img src="./assets/tile-{name}-dark.svg" alt="" width="23%">'
            f'</picture></a>',
        ]

    # ОТМЕТКА СВЕЖЕСТИ. Витрина показывает живые числа, и до 28 августа
    # умалчивала, НАСКОЛЬКО живые. Суточная сборка пропустила день — площадка не
    # гарантирует запуск по расписанию, — и страница сутки показывала вчерашнее,
    # ничем этого не выдавая. Заметил владелец, а не механизм.
    #
    # ЧТО ИМЕННО ОБЕЩАЕТ ЭТА ДАТА. День, когда числа последний раз ИЗМЕНИЛИСЬ,
    # а не когда сборка бежала: строка пишется вместе с данными и вместе с ними
    # доезжает изменением. Замри сборка — замрёт и дата, и застрявшая страница
    # видна без всякого прогона. Вопрос «бежала ли сборка» — другой, и на него
    # отвечает .github/workflows/staleness.yml, а не эта строка (правило 056:
    # сигнал говорит, чего он НЕ значит).
    tail = [f"data as of {dt.date.today().isoformat()}"]
    if hidden:
        tail.append(f"{limit} shown, most recently active first · {len(hidden)} more on the "
                    "[repositories tab](https://github.com/ArtVsMark?tab=repositories)")
    rows += ["", f"<sub>{' · '.join(tail)}</sub>"]
    rows += ["", "</div>"]
    return "\n" + "\n".join(rows) + "\n"


def check_focus_limit(text: str) -> None:
    """Потолок «Current focus»: строк не больше FOCUS_LIMIT.

    Единственный блок витрины, который ведётся руками, — планы измерить нечем.
    Значит у него должен быть хотя бы предел, выраженный числом и проверяемый
    машиной: «стало многовато» не проверяет ничего.
    """
    block = re.search(r"<!--focus-->(.*?)<!--/focus-->", text, re.S)
    if not block:
        raise SystemExit("в README нет блока <!--focus--> — потолок не к чему применить")
    rows = [line for line in block.group(1).splitlines() if line.startswith("| **")]
    if len(rows) > FOCUS_LIMIT:
        raise SystemExit(f"в «Current focus» {len(rows)} строк при потолке {FOCUS_LIMIT}")


def grader_facts() -> dict:
    """Факты грейдера — из файла, который он публикует о себе сам.

    ПОЧЕМУ НЕ СЧИТАЕМ САМИ. Три числа из четырёх требовали знания чужого
    устройства: где лежат тесты, как назван каталог, как устроена матрица в
    ci.yml. Четвёртое — проверок на PR — вычислялось медианой по семи последним
    PR, потому что снаружи точный ответ не виден; внутри он есть, тем же
    набором, каким грейдер держит собственный мерж-гейт. Приём тот же, что у
    каталога правил: издатель считает, потребитель читает (правило 090 — второй
    копии чужого определения не заводят).

    ЧИТАЕТСЯ ЧЕРЕЗ contents-API, а не через ``raw.githubusercontent.com``: raw
    отвечает 404 на запрос с заголовком ``Authorization`` — токен для него
    чужой. Тот же подвох уже разобран у значков, и труба здесь та же самая.

    Несовместимый мажор — отказ, а не «прочитаем что получится»: формат,
    сменивший смысл полей, хуже нечитаемого. Ровно так витрина уже поступает с
    контрактом каталога.
    """
    try:
        payload = _api(f"/repos/{REPO}/contents/{FACTS_PATH}?ref=badges")
        facts = json.loads(base64.b64decode(payload["content"]))
    except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
        raise SystemExit(
            f"факты грейдера не прочитаны ({REPO}:badges/{FACTS_PATH}): {error}.\n"
            f"  Это отказ ИСТОЧНИКА, а не находка о витрине: числа не подставляются "
            f"прошлыми — тихий откат к вчерашнему и есть то молчание, против которого "
            f"сборка написана."
        ) from error

    schema = str(facts.get("schema", ""))
    if schema.split(".")[0] != FACTS_SCHEMA:
        raise SystemExit(f"схема фактов грейдера {schema!r}, а сборка умеет мажор {FACTS_SCHEMA}.x")
    return facts


def project_facts(repo: str, silent: list[str] | None = None) -> dict:
    """Факты проекта — из файла, который он публикует о себе сам. Нет — пусто.

    ОТЛИЧИЕ ОТ ``grader_facts``: там молчание источника роняет сборку, потому
    что без тех чисел витрине нечего показать вовсе. Здесь молчание — законный
    ответ «этот проект о себе пока не рассказывает», и он ОТЛИЧИМ от нуля:
    пустой словарь означает «файла нет», а не «измерено ноль».

    Соседи публикуют разное, и это нормально: контракт называет обязательными
    три поля, остальные разделы — по мере того, как проект их измеряет.

    ТРЕТИЙ ИСХОД ОТДАЁТСЯ ОТДЕЛЬНО (правило 039). Пустой словарь у этой функции
    означает «читать нечего», а ПОЧЕМУ — два разных ответа: ``404`` это «файла
    нет», а сорванная связь, чужой код ошибки или несовместимая схема — «источник
    промолчал». Для картинки разницы нет, а для утверждения о соседе есть:
    молчание источника нельзя записывать в «не публикует». Кто промолчал,
    складывается в ``silent``, если список передан.
    """
    try:
        payload = _api(f"/repos/{repo}/contents/{FACTS_PATH}?ref=badges")
        facts = json.loads(base64.b64decode(payload["content"]))
    except urllib.error.HTTPError as refusal:
        if refusal.code != 404 and silent is not None:
            silent.append(repo)
        return {}
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        if silent is not None:
            silent.append(repo)
        return {}
    if not isinstance(facts, dict):
        if silent is not None:
            silent.append(repo)
        return {}
    schema = str(facts.get("schema", ""))
    if schema and schema.split(".")[0] != FACTS_SCHEMA:
        # Несовместимый мажор читать нельзя, но и ронять сборку из-за соседа,
        # ушедшего вперёд, — значит останавливать витрину чужой правкой.
        if silent is not None:
            silent.append(repo)
        return {}
    return facts

#: Колонки таблицы «Кто это уже делает» в .rules/facts-contract.md: подпись в
#: шапке и раздел фактов, о котором она говорит. Порядок — порядок колонок.
CONTRACT_COLUMNS = (("файл", None), ("tests", "tests"), ("checks", "checks_per_pr"),
                    ("coverage", "coverage_percent"), ("rules", "rules"))

#: Строка таблицы: имя проекта ссылкой, дальше клетки. Ключом берётся АДРЕС, а
#: не подпись: подпись правят, адрес — нет.
CONTRACT_ROW = re.compile(r"^\|\s*\[[^\]]+\]\(https://github\.com/(?P<repo>[\w.-]+/[\w.-]+)\)"
                          r"\s*\|(?P<cells>.+)\|\s*$", re.M)

#: Что в клетке считается «да» и что «нет». Всё остальное — не разобрано, и
#: молчать об этом нельзя: непонятая клетка не значит «нет».
CONTRACT_YES = ("есть", "✅", "да")
CONTRACT_NO = ("нет", "—", "-", "–")


def contract_findings(document: str, facts: dict[str, dict],
                      silent: list[str]) -> list[str]:
    """Таблица «кто это уже делает» сверяется с тем, что соседи публикуют сейчас.

    ЗАЧЕМ. Документ сам называет свою болезнь: «Эта таблица устаревала молча, и
    дважды». К 8 сентября это случилось ТРЕТИЙ раз и за один час: строка про
    каталог говорила «файла нет» — и была верна утром, а к полудню каталог
    закрыл свою задачу и начал публиковать все четыре раздела. Ответ о соседе,
    написанный однажды, врёт тем же способом, что число, вписанное руками.

    ПОЧЕМУ ЭТО НЕ ГЕЙТ ДЕРЕВА, А НАХОДКА О СОСЕДЕ. Предмет живёт на чужой
    стороне и меняется без нашего участия. Поэтому находка едет тем же каналом,
    что и остальные о соседях: красная на проверке изменения (чинится правкой
    документа здесь и сейчас), предупреждением — в суточной сборке, где чужая
    правка не вправе останавливать наши числа.

    МОЛЧАНИЕ ИСТОЧНИКА НЕ СУДИТСЯ (правило 039). Сосед, чьи факты не прочитаны
    вовсе — сорванная связь, чужой код ошибки, несовместимая схема, — из сверки
    выпадает: «не ответил» и «не публикует» это разные вещи, и записывать первое
    во второе значило бы врать в документе о том, чего не знаешь.
    """
    found: list[str] = []
    for row in CONTRACT_ROW.finditer(document):
        repo = row.group("repo")
        if repo in silent or repo not in facts:
            continue
        cells = [cell.strip().strip("*").strip() for cell in row.group("cells").split("|")]
        known = facts[repo]
        for (name, section), cell in zip(CONTRACT_COLUMNS, cells):
            said = (True if cell.lower() in CONTRACT_YES
                    else False if cell.lower() in CONTRACT_NO else None)
            truth = bool(known) if section is None else bool(known.get(section))
            if said is None:
                found.append(f".rules/facts-contract.md: клетка «{name}» у {repo} записана "
                             f"как «{cell}» — сверить не с чем, а непонятая клетка не "
                             f"значит «нет»")
            elif said != truth:
                found.append(f".rules/facts-contract.md: у {repo} в таблице «{name}» = "
                             f"«{cell}», а сосед сейчас {'публикует' if truth else 'не публикует'} "
                             f"это. Таблица устаревает молча — поправьте строку, "
                             f"а не проверку")
    return found



def catalogue_where() -> dict[str, dict]:
    """Ответ каталога о каждом потребителе: доли механизмов, разобрано, следы.

    Читается у ИЗДАТЕЛЯ, а не собирается из чужих `bindings.json`: определение
    того, что считается механизмом, принадлежит каталогу, и вторая копия этого
    определения разошлась бы с первой молча (правило 090).

    Словарь долей берётся КАК ЕСТЬ. За две недели он вырос с четырёх значений
    до пяти — добавился ``code``, — и свой список отстал бы, а первым это
    увидел бы читатель картинки.
    """
    try:
        payload = json.loads(_get(checks.CATALOGUE_WHERE, authenticated=False))
    except (urllib.error.URLError, OSError, ValueError) as error:
        print(checks.annotate("warning", f"ответ каталога о потребителях не прочитан "
                              f"({checks.CATALOGUE_WHERE}): {error}"),
              file=sys.stdout)
        return {}
    consumers = payload.get("consumers")
    if not isinstance(consumers, list):
        return {}
    return {str(item.get("repo", "")): item for item in consumers if isinstance(item, dict)}


def facts_staleness(generated_at: str, now: dt.datetime, limit: int = FACTS_STALE_DAYS) -> str:
    """Насколько факты отстали от жизни. Пусто — не отстали.

    ЗАЧЕМ ОТДЕЛЬНАЯ ПРОВЕРКА. Файл соседа не пропадает, когда его прогон
    перестаёт работать: он просто остаётся вчерашним. Витрина показывала бы
    старые числа сколько угодно долго, и снаружи это неотличимо от «числа не
    менялись» — то самое молчание, ради которого вся сборка и заведена. Раньше
    предмета не было: числа считались здесь и устареть не могли.

    ОТСУТСТВИЕ ОТМЕТКИ — НАХОДКА, А НЕ МОЛЧАНИЕ. Пустое поле означает «когда
    измеряли, неизвестно», и читать его как «свежо» значило бы решать за
    издателя. Первая редакция так и делала.
    """
    if not str(generated_at).strip():
        return ("факты грейдера без отметки времени — когда их измеряли, неизвестно, "
                "и свежесть проверить нечем")
    try:
        stamp = dt.datetime.fromisoformat(str(generated_at))
    except ValueError:
        return f"отметка времени фактов {generated_at!r} не разобрана — свежесть проверить нечем"
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    days = (now - stamp).days
    if days <= limit:
        return ""
    return (f"факты грейдера собраны {days} дней назад (порог {limit}) — либо остановился "
            f"его прогон, либо проект; витрина всё это время показывала бы прежние числа "
            f"как свежие")


def facts_gaps(facts: dict) -> list[str]:
    """Чего в фактах нет из того, что витрина показывает. Пусто — всё на месте.

    «КЛЮЧА НЕТ — ЗНАЧИТ НЕ ИЗМЕРЯЛИ» — это контракт издателя, и он честнее нуля:
    ноль читался бы как «проверок не создаётся». Но витрине от честного
    отсутствия не легче: показать число она всё равно не может, а показать
    прошлое — нельзя.

    Поэтому пробел назван поимённо и разведён со своей поломкой: сборка
    отказывает, называя СТОРОНУ. «Издатель не измерил» и «мы не собрали» чинятся
    в разных репозиториях, и путать их дороже, чем разбирать (правило 039).
    """
    needed = {
        "python.experimental": facts.get("python", {}).get("experimental"),
    }
    return sorted(key for key, value in needed.items() if value in (None, "", [], {}))


def protection_facts() -> tuple[int, int, int]:
    """Обязательные проверки на ``main``: сколько их, сколько ОС и версий Python.

    Источник — правила ветки, а не объект ruleset: ``/rules/branches/main``
    отдаёт имена обязательных контекстов любому, кто видит репозиторий, тогда
    как ``/rulesets/{id}`` без прав admin молчит про ``bypass_actors``.

    Имена матричных джобов входят в ruleset дословно
    (``test (ubuntu-latest, 3.12, false)``), поэтому размерность матрицы
    вынимается из них же: это ровно те комбинации, без которых мерж не
    состоится.
    """
    contexts = []
    for rule in _api(f"/repos/{REPO}/rules/branches/main"):
        if rule.get("type") == "required_status_checks":
            contexts = [c["context"] for c in rule["parameters"]["required_status_checks"]]
    matrix = [re.match(r"test \(([^,]+), ([^,)]+)", context) for context in contexts]
    systems = {m.group(1) for m in matrix if m}
    versions = {m.group(2) for m in matrix if m}
    return len(contexts), len(systems), len(versions)


def release_count() -> int:
    return len(_api(f"/repos/{REPO}/releases?per_page=100"))


#: За сколько дней считается подпись работы. Скользящее окно, а не вся история:
#: соглашение появилось не в первый день жизни витрины, и доля по всей истории
#: говорила бы о прошлом, а не о том, как здесь работают сейчас.
SIGNED_WINDOW_DAYS = 30

#: Заголовок суточной пересборки. Её составляет прогон, а не человек: решения он
#: не принимает и трейлера исполнителя нести не обязан (правило 051).
MACHINE_SUBJECT = "chore(profile): пересобранные метрики"


def signed_commits(days: int = SIGNED_WINDOW_DAYS) -> tuple[int, int]:
    """Сколько рабочих коммитов общей ветки несут исполнителя и след сессии.

    ЗАЧЕМ ЭТО ЧИСЛО НА ВИТРИНЕ. Страница утверждает, что работу ведут агентские
    окна и что это видно в истории. Утверждение проверяемо — открой историю и
    посмотри, — но пока его никто не измеряет, оно ничем не отличается от
    обещания. Здесь оно измеряется тем же способом, что и остальные числа.

    МАШИННЫЕ КОММИТЫ НЕ СЧИТАЮТСЯ НИ В ЧИСЛИТЕЛЕ, НИ В ЗНАМЕНАТЕЛЕ. Суточную
    пересборку составляет прогон: решения он не принимает, исполнителя у него
    нет, и требовать от него трейлер значило бы требовать невозможного. Считать
    его в знаменателе — занижать долю за то, чего не бывает.

    Молчание источника ловится сторожем пустых метрик: ноль рабочих коммитов за
    месяц — это не «никто не подписывает», а «список не прочитан».
    """
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    commits = _api(f"/repos/{SHOWCASE}/commits?sha=main&since={since}&per_page=100")
    signed = total = 0
    for item in commits if isinstance(commits, list) else []:
        commit = item.get("commit") or {}
        message = str(commit.get("message", ""))
        author = ((commit.get("author") or {}).get("name") or "")
        if MACHINE_SUBJECT in message or checks.machine_made(author):
            continue
        total += 1
        if "co-authored-by:" in message.lower():
            signed += 1
    return signed, total


def rules_export() -> dict:
    """Экспорт каталога правил — источник и числа правил, и списка их номеров.

    Что считать правилом, решает каталог: пара файлов в двух деревьях, номер,
    область, разбираемый след — и всё это держат его гейты. ``count`` в экспорте
    посчитан тем же скриптом, что собирает указатель каталога, и закреплён тем
    же гейтом. Считать здесь самому означало бы держать копию чужого
    определения: она совпадает ровно до первого изменения на той стороне, а
    расходится молча — оба числа правдоподобны.

    Отказ загрузки роняет сборку и НЕ подставляет прошлое число. Тихий откат к
    старому значению — та самая половина правила про «молча»: страница осталась
    бы прежней, а конвейер отчитался бы «числа не изменились».

    Несовместимый мажор схемы — тоже отказ: читать «что получится» из формата,
    который сменил смысл полей, хуже, чем не читать вовсе.
    """
    try:
        export = json.loads(_get(RULES_EXPORT, authenticated=False))
    except (urllib.error.URLError, ValueError) as error:
        raise SystemExit(f"экспорт каталога не прочитан ({RULES_EXPORT}): {error}") from error

    schema = str(export.get("schema", ""))
    if schema.split(".")[0] != RULES_SCHEMA:
        raise SystemExit(f"схема экспорта {schema!r}, а сборка умеет мажор {RULES_SCHEMA}.x")
    return export


#: Имя репозитория в дереве витрины. Ищется всюду, кроме журнала: там ссылки на
#: старые имена стоят НАМЕРЕННО — редирект держится, а прошлое не переписывают.
REPO_MENTION = re.compile(r"ArtVsMark/[A-Za-z][A-Za-z0-9_.-]*")
CENSUS_SKIP = ("HISTORY.md",)


def mentioned_repos(root: pathlib.Path) -> dict[str, list[str]]:
    """Перепись: какое имя репозитория где записано.

    ЗАЧЕМ ПЕРЕПИСЬ, А НЕ ГЕЙТ НА ОТКАЗ. Переименование репозитория держит
    ПЛОЩАДКА: редирект работает, и отключить его нельзя. Значит сигнала о
    незавершённой миграции не будет вовсе — ни красного прогона, ни битой
    ссылки. Заменить его может только перечисление мест, сверяемое с живым
    источником (правило 172).

    Цена уже заплачена: 28 августа владелец переименовал двух соседей за день,
    и старые имена нашлись в двадцати местах — значки, ссылки, адреса выгрузки.
    Чинилось это чтением дерева глазами (#111).
    """
    census: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*")):
        if (not path.is_file() or ".git/" in str(path) or path.name in CENSUS_SKIP
                or path.suffix not in (".py", ".json", ".yml", ".yaml", ".md")):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for name in REPO_MENTION.findall(text):
            # `.git` на конце — часть адреса клона, а не имени репозитория:
            # площадка такого имени не знает, и запрос о нём был бы отказом.
            name = name.removesuffix(".git")
            if name.count("/") == 1 and not name.endswith("/"):
                census.setdefault(name, []).append(str(path.relative_to(root)))
    return census


def renaming_finding(name: str, live: str, places: list[str]) -> str:
    """Находка о переименовании, отдельно от похода в сеть — ради набора.

    Пустая строка означает «имя живое». Пустой ответ площадки — тоже: у окна
    может не быть доступа к репозиторию, и это говорит о правах, а не о
    миграции (039).
    """
    if not live or live == name:
        return ""
    seen = sorted(set(places))
    return (f"{name} переименован в {live}, а имя записано в {len(seen)} местах: "
            f"{checks.tail(seen, 4)} (172)")


def renamed_repos(census: dict[str, list[str]]) -> list[str]:
    """Имена из переписи, которые площадка знает уже под другим именем.

    ЖИВОЙ ИСТОЧНИК, А НЕ КОНСТАНТА: при переименовании площадка продолжает
    отвечать по старому адресу, но в ``full_name`` возвращает НОВОЕ имя. Это
    единственный доступный признак незавершённой миграции — сам по себе старый
    адрес работает и выглядеть сломанным не будет никогда.

    Отказ по конкретному имени пропускается молча: у окна может не быть доступа
    к репозиторию, и это говорит о правах, а не о миграции (039).
    """
    found = []
    for name, places in sorted(census.items()):
        try:
            live = str(_api(f"/repos/{name}").get("full_name", ""))
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            continue
        finding = renaming_finding(name, live, places)
        if finding:
            found.append(finding)
    return found


def protection_names(repo: str = "ArtVsMark/ArtVsMark") -> list[str]:
    """Имена обязательных проверок в защите ветки — как их видит площадка."""
    contexts: list[str] = []
    for rule in _api(f"/repos/{repo}/rules/branches/main"):
        if rule.get("type") == "required_status_checks":
            contexts = [c["context"] for c in rule["parameters"]["required_status_checks"]]
    return contexts


def job_names(root: pathlib.Path) -> set[str]:
    """Имена работ, объявленные прогонами В ДЕРЕВЕ ЭТОГО ИЗМЕНЕНИЯ.

    Состав читается из дерева, а не из прогонов на общей ветке: эталон с общей
    ветки приходит из прошлого и делает неразрешимым ровно тот класс изменений,
    который сам состав и меняет — переименование работы не уехало бы никогда
    (правило 171).
    """
    names = set()
    for flow in sorted((root / ".github/workflows").glob("*.yml")):
        for match in re.finditer(r"^\s{4}name:\s*(.+?)\s*$", flow.read_text(encoding="utf-8"),
                                 re.M):
            names.add(match.group(1))
    return names


def unmet_contexts(required: list[str], declared: set[str]) -> list[str]:
    """Обязательные проверки, которых никто не создаёт. Пусто — все создаются.

    ЗАЧЕМ. Защита ветки требует проверок ПО ИМЕНИ, и имя попадает в настройку
    дословно — вне репозитория и вне ревью. Имя, которого никто не создаёт,
    переводит изменение в ВЕЧНОЕ ожидание: снаружи всё зелено, слияния нет, и
    единственный след — отказ автомержа в логе.

    Цена уже заплачена: 22 августа работа звалась `check`, а обязательным
    контекстом стал `PR check`. Несливаемым стал КАЖДЫЙ PR, включая тот,
    которым это чинили. Совпадение с тех пор держалось ничем.

    СВЕРКА ИДЁТ ОТ НАСТРОЙКИ К ДЕРЕВУ, а не наоборот: работ в дереве больше,
    чем обязательных проверок, и это законно — лишняя работа никого не
    блокирует, а недостающая блокирует всё (правила 168 и 171).

    ОТКАЗ НАЗЫВАЕТ ОБЕ СТОРОНЫ РАСХОЖДЕНИЯ, а не только недостающее имя. Это
    половина правила 178, которая следует из данных целиком: судить, «меряют ли
    источники разное», машина не может, но положить оба списка рядом — может, и
    без этого читатель достраивает вторую сторону по памяти. Инцидент 22 августа
    был ровно таким: имя `check` против `PR check` — расхождение в одном слове,
    и глазами оно не читается, пока списки не окажутся в одной строке.
    """
    return [f"обязательная проверка {name!r} не создаётся ни одной работой — "
            f"изменение встанет навсегда, и снаружи это выглядит как «ещё бежит» "
            f"(168). Работы в дереве: {', '.join(sorted(declared)) or '—'}"
            for name in sorted(set(required) - declared)]


def answer_contract_version() -> str:
    """Версия формата ОТВЕТА потребителя — у издателя, из его же заготовки.

    ЗАЧЕМ ОТДЕЛЬНЫЙ ИСТОЧНИК, А НЕ `schema` ВЫГРУЗКИ. Это разные предметы с
    одним именем ключа, и витрина на этом уже обожглась: в её ответе стояло
    1.2 — номер формата ВЫГРУЗКИ в поле формата ОТВЕТА, где контракт требует
    1.1. Файл оставался валидным, гейт зелёным, а сторож отставания сравнивал
    чужую выгрузку со своим ответом и молчал ровно потому, что номер был
    подогнан под чужой (правило 164).

    Каталог версию формата ответа машиночитаемо не публикует — в `export/`
    её нет. Живой источник у него один: собственная заготовка ответа, по
    которой подключают потребителей. Она и спрашивается — артефакт издателя,
    а не константа здесь (049).

    Отказ источника не роняет сборку: без версии сверять отставание не с чем,
    и это третий исход, а не находка о витрине. Пустая строка так и читается
    вызывающим (039).
    """
    try:
        template = json.loads(_get(ANSWER_CONTRACT, authenticated=False))
    except (urllib.error.URLError, ValueError, OSError):
        return ""
    return str(template.get("schema", ""))


def contract_drift(published: str, answered: str) -> str:
    """Насколько ответ витрины отстал от контракта каталога. Пусто — не отстал.

    Правило 157. Мажор роняет сборку выше: читать «что получится» из формата,
    сменившего смысл полей, хуже, чем не читать. МИНОР так не ломается — и
    именно поэтому опасен: записи остаются формально валидными, означая уже
    другое. У соседа на подъёме 1.0 → 1.1 слово ``process-step`` раскололось, и
    52 ответа из 153 стали значить «мы не ответили», оставаясь зелёными.

    Сравнение идёт с версией НАШЕГО ответа, а не с собственной константой: обе
    стороны такой константы обновляются одной рукой, и подъём у издателя она не
    заметит никогда. Здесь одна сторона — чужой контракт, вторая — наш файл.

    Живой предмет, ради которого функция заведена: 2 сентября контракт стоял на
    1.2, ответ витрины — на 1.0, и не падало ничего. Перечитывание нашло запись,
    где ``where`` был прозой без разрешимого адреса, — требование появилось
    вместе с 1.1.
    """
    def parts(version: str) -> tuple[int, int]:
        major, _, minor = str(version).partition(".")
        return (int(major or 0), int(minor.split(".")[0] or 0))

    # Пустая версия — не «равные нули», а отсутствие ответа на вопрос. Молчать
    # здесь значило бы читать её как совпадение: первая редакция так и делала,
    # и набор поймал это случаем «версии нет вовсе».
    if not str(published).strip() or not str(answered).strip():
        return (f"версия контракта {published!r} или ответа {answered!r} не названа — "
                f"сверять отставание не с чем")
    try:
        theirs, ours = parts(published), parts(answered)
    except ValueError:
        return (f"версия контракта {published!r} или ответа {answered!r} не разобрана — "
                f"сверить отставание нечем")
    if theirs <= ours:
        return ""
    return (f"контракт каталога {published}, ответ витрины {answered} — "
            f"перечитать записи .rules/bindings.json и поднять schema: подъём минора "
            f"меняет значение полей, а не только формат (правило 157)")


def sync_bindings(export: dict, write: bool = True) -> str:
    """Дописывает в ответ потребителя правила, которых в нём ещё нет.

    Гейта здесь нет намеренно: витрина собирается, а не проверяется, и падать
    из-за того, что в чужом каталоге появилось правило, она не должна. Но и
    молчать нельзя — иначе «никто не знал» снова становится возможным
    состоянием. Поэтому новое правило само приезжает сюда со статусом
    ``unreviewed``: решение по нему принимает человек, а вот появление в списке
    от человека не зависит.

    СВЕРКА ИДЁТ В ОБЕ СТОРОНЫ, и вторая половина появилась дорого. Здесь стояло:
    «номера правил не переиспользуются, поэтому исчезнувшие записи не удаляются:
    пропасть правило может только вместе с каталогом». Неверно. Каталог удаляет
    записи — правило 143 удалили как переоткрывающее уже сказанное, — и ответ на
    него остался у витрины висеть: 148 ответов при 147 правилах. Гейт полноты
    такого не ловит: он спрашивает, есть ли ОТВЕТ, а не есть ли у ответа предмет.

    Поэтому появление и исчезновение обрабатываются ПО-РАЗНОМУ, и асимметрия
    намеренная. Появление решается само: новое правило приезжает со статусом
    ``unreviewed``, и падать из-за чужого пополнения витрина не должна.
    Исчезновение решения не имеет — ответ мог быть верным, а мог держаться
    удалённым правилом, — поэтому оно называется находкой и требует человека.
    """
    answer = json.loads(BINDINGS.read_text(encoding="utf-8"))
    rules = answer["rules"]
    added = [rule["id"] for rule in export["rules"] if rule["id"] not in rules]
    for rule_id in added:
        rules[rule_id] = {"status": "unreviewed"}
    # ВЫГРУЗКА, ПО КОТОРОЙ ПОСТРОЕНЫ ОТВЕТЫ, — поле контракта 1.2, и берётся
    # оно ИЗ САМОЙ ВЫГРУЗКИ, а не переписывается по памяти. Номер, вписанный
    # рукой, стареет молча и врёт ровно там, где должен предупреждать:
    # каталог сверяет его со своим и печатает отставание (157, 164).
    answered_to = str(export.get("contracts", {}).get("export", ""))
    stale = bool(answered_to) and answer.get("answers_to") != answered_to
    pending = any(binding["status"] == "unreviewed" for binding in rules.values())
    raise_to = answered_version(str(answer.get("answers_to", "")), answered_to, pending)
    if (added or raise_to) and write:
        if raise_to:
            answer["answers_to"] = raise_to
        answer["rules"] = {key: rules[key] for key in sorted(rules)}
        BINDINGS.write_text(json.dumps(answer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    unreviewed = sum(1 for binding in rules.values() if binding["status"] == "unreviewed")
    # Правил каталога, на которые ответа нет вовсе. Это число знает только
    # сборка — check_bindings живёт без сети и печатать его не вправе. До
    # записи файла оно ненулевое, после — сходится к нулю: дописанное
    # становится «не рассмотрено», то есть долг переезжает, а не исчезает (177).
    unanswered = len(added) if not write else 0
    unheld = sum(1 for binding in rules.values()
                 if binding["status"] == "active" and binding.get("mechanism") == "none")
    left = orphaned(export, rules)
    tail = f", ответ без правила: {', '.join(left)}" if left else ""
    # Долг называется ПЕРВЫМ, до числа записей: незакрытая работа по правилам
    # идёт впереди новой, и увидеть её надо раньше, чем список нового (177).
    # Отставание поля «по какой выгрузке отвечено» называется вслух и на
    # сухом прогоне: сборка его чинит записью, а проверка — только видит.
    behind = (f", выгрузка ответа {answer.get('answers_to', '—')} против {answered_to}"
              f"{' — сначала разбор, потом номер' if pending else ''}"
              if stale else "")
    return (f"долг по правилам: без ответа {unanswered} · не рассмотрено {unreviewed} · "
            f"держится ничем {unheld}\n"
            f"ответ каталогу: записей {len(rules)}, дописано {len(added)}{tail}{behind}")


def answered_version(current: str, published: str, pending: bool) -> str:
    """Номер выгрузки, который вправе встать в ответ. Пусто — не вправе никакой.

    ПОЛЕ ``answers_to`` — УТВЕРЖДЕНИЕ, А НЕ ОТМЕТКА О СИНХРОНИЗАЦИИ. Оно
    говорит: ответы ниже построены по выгрузке такой-то. Пока в файле лежит
    хоть один ``unreviewed``, это ложно — правило приехало, а ответа на него
    нет.

    ЧЕМ ПЛАТИТ МАШИНА, СТАВЯЩАЯ НОМЕР САМА. Каталог сверяет его со своим и
    печатает отставание; номер, поднятый сборкой в тот же заход, что приехали
    новые правила, глушит ровно этот сигнал — и глушит зелёным (146). Долг
    остаётся виден локально («не рассмотрено N»), а издатель видит потребителя,
    который якобы всё разобрал.

    Отсюда асимметрия: номер поднимает ПЕРЕЧИТЫВАНИЕ, сборка лишь записывает
    его тогда, когда перечитывать нечего. Пустая версия у издателя — третий
    исход: выгрузка не назвала свой контракт, и выдумывать номер неоткуда (039).
    """
    if not published or pending or current == published:
        return ""
    return published


def our_trails(export: dict, repo: str = SHOWCASE) -> list[str]:
    """Следы каталога, ведущие в НАШИ документы, — разрешаются ли они (185).

    СЛЕД — ЭТО АДРЕС В ЧУЖОМ ДЕРЕВЕ, и правит его владелец дерева: сторона,
    которая переименовала файл или раздел, узнаёт о правке в тот же миг, а
    сторона, которая на него сослалась, не узнает никогда — пока кто-нибудь не
    пойдёт по следу. Отсюда обязанность лежит здесь, а не на каталоге.

    ЦЕНА ИЗМЕРЕНА У СОСЕДА: в английском дереве каталога 68 следов из 71 не
    разрешались — название раздела переводили вместе с текстом записи. У
    русского было два, и оба медленные: раздел переименовали, след остался.

    НАХОДКА, А НЕ ОТКАЗ, и причина не в мягкости. Починка живёт в ЧУЖОМ
    репозитории: файл правила лежит у каталога, и отсюда его не поправить.
    Красное, которое нечем закрыть в этом дереве, останавливает витрину за
    чужую правку — а правило требует пойти и поправить, а не встать (051).

    Проверяется только след-документ: у следа-задачи предмет в трекере, и
    спрашивать о нём здесь значило бы звать площадку ради каждой записи.
    Раздел после ``§`` ищется в тексте как есть, буква в букву: перевод и
    пересказ адреса — ровно та поломка, ради которой правило заведено.
    """
    found = []
    for rule in export.get("rules", []):
        for trail in rule.get("trails", []):
            if trail.get("repo") != repo or not trail.get("doc"):
                continue
            path, _, section = str(trail["doc"]).partition("§")
            file = ROOT / path.strip()
            if not file.is_file():
                found.append(f"след правила {rule['id']} ведёт в наш документ "
                             f"{path.strip()!r}, которого нет. Поправить след обязана "
                             f"сторона, чей документ, — то есть мы (185)")
            elif section.strip() and section.strip() not in file.read_text(encoding="utf-8"):
                found.append(f"след правила {rule['id']} называет раздел "
                             f"{section.strip()!r} в {path.strip()}, а такого раздела "
                             f"там нет: заголовок переименовали, след остался (185)")
    return found


def orphaned(export: dict, rules: dict) -> list[str]:
    """Ответы, у которых в каталоге больше нет правила.

    Отдельной функцией, потому что это утверждение о согласованности двух
    источников, и его надо уметь прогнать (правило 140), а не только выполнить
    по дороге.
    """
    live = {rule["id"] for rule in export["rules"]}
    return sorted(set(rules) - live)



#: Что показывает карточка профиля и в каком порядке. Список — вход
#: рисовальщика: подпись картинки собирается из него же, и разойтись им негде.
ENGINEERING_TILES = (
    ("repos", "public repos"),
    ("stars", "stars earned"),
    ("followers", "followers"),
    ("contributions", "contributions · 365d"),
    ("streak", "day streak"),
    ("longest", "longest streak"),
)


def render_engineering(stats: dict[str, object], dark: bool) -> str:
    """Карточка инженерного профиля: шесть чисел одной строкой в две полосы.

    ПОЧЕМУ НЕ ЯРКАЯ КАРТОЧКА СО СТОРОННЕГО СЕРВИСА, ради которой заводилась
    задача #139. Внешняя карточка — это чужая доступность и чужой отказ,
    выглядящий как сломанная страница; проверить её из окна нельзя, потому что
    прокси не пускает хост. Числа витрина и так измеряет сама, и рисует их той
    же кистью, что остальные плитки.

    ФОРМА ПОВТОРЯЕТ ``render``, А НЕ ИЗОБРЕТАЕТ СВОЮ: те же карточные цвета, тот
    же шрифт, тот же радиус. Две полосы по три плитки — потому что шесть в ряд
    на ширине профиля дают числа мельче подписи, а витрину читают с телефона.
    """
    # ПОЛОВИНА ШИРИНЫ, А НЕ ВСЯ: карточка встаёт в ряд со следом технологий,
    # как это сделано у профилей, где два блока стоят по 49%. Шесть чисел в
    # две колонки по три строки — при трёх в ряд на узкой карточке число
    # становится мельче подписи, а витрину читают с телефона.
    width, gap, per_row = 492, 14, 2
    rows = len(ENGINEERING_TILES) // per_row
    tile_w = (width - gap * (per_row - 1)) // per_row
    tile_h, head = 84, 28
    height = head + tile_h * rows + gap * (rows - 1)
    if dark:
        card, stroke, num, lab = "#0D1117", "#30363D", "#F0F6FC", "#7D8590"
    else:
        card, stroke, num, lab = "#FFFFFF", "#D0D7DE", "#1F2328", "#636C76"

    def shown(key: str) -> str:
        """Число — с разделителем разрядов, всё остальное — как есть.

        Разряды разделяются, иначе «1287» читается как год. Нечисловое значение
        форматированию не поддаётся вовсе (`:,` на строке — отказ), и первая
        редакция роняла на этом рисование целиком: набор подсунул `<&>`, и
        сборка вышла третьим исходом вместо картинки. Источник чужой, приехать
        оттуда может что угодно, и падать на этом рисовальщику незачем.
        """
        value = stats.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return str(value)
        return f"{value:,}".replace(",", " ")

    values = [(shown(key), name) for key, name in ENGINEERING_TILES]
    label = "GitHub engineering stats: " + ", ".join(f"{v} {n}" for v, n in values)
    out = [
        svg_open(width, height, label),
        '<defs><linearGradient id="e" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%" stop-color="#58A6FF"/><stop offset="100%" stop-color="#7EE787"/>'
        "</linearGradient></defs>",
        f'<text x="{width / 2:.0f}" y="17" fill="{lab}" font-family="{FONT}" '
        f'font-size="13" font-weight="700" text-anchor="middle" letter-spacing="0.4">'
        f"GitHub engineering stats</text>",
    ]
    for index, (value, name) in enumerate(values):
        row, column = divmod(index, per_row)
        x = column * (tile_w + gap)
        y = head + row * (tile_h + gap)
        size = 32 if len(value) <= 4 else 26
        out.append(
            f"  <g>\n"
            f'    <rect x="{x + 0.5}" y="{y + 0.5}" width="{tile_w - 1}" '
            f'height="{tile_h - 1}" rx="14" fill="{card}" stroke="{stroke}"/>\n'
            f'    <rect x="{x + 18}" y="{y + 16}" width="36" height="4" rx="2" fill="url(#e)"/>\n'
            f'    <text x="{x + tile_w / 2:.0f}" y="{y + 54}" fill="{num}" '
            f'font-family="{FONT}" font-size="{size}" font-weight="800" '
            f'text-anchor="middle" letter-spacing="-1">{escape(value)}</text>\n'
            f'    <text x="{x + tile_w / 2:.0f}" y="{y + 73}" fill="{lab}" '
            f'font-family="{FONT}" font-size="12.5" font-weight="600" '
            f'text-anchor="middle">{escape(name)}</text>\n'
            f"  </g>"
        )
    return "\n".join(out) + "\n</svg>\n"


def render_stack(reach: list[tuple[str, int]], roles: list[str], total: int,
                 dark: bool, height: int = 308) -> str:
    """След технологий: языки по охвату проектов и роли, которые они играют.

    ЗАМЕНЯЕТ «TOP LANGUAGES», А НЕ ПОВТОРЯЕТ ЕГО. Типовая карточка считает доли
    по объёму кода; у нас это 96% одним сектором и ноль сведений. Здесь два
    ответа на вопрос «из чего сделаны проекты»: язык — по числу репозиториев,
    где он встречается, и роли — строкой `stack` из projects.json, то есть
    словами автора о предмете, а не выводом из размера файлов.

    Высота равна карточке чисел: они стоят в одном ряду, и разъехавшийся низ
    читается как недоделанная вёрстка.
    """
    width, pad = 492, 22
    if dark:
        card, stroke, num, lab, bar = "#0D1117", "#30363D", "#F0F6FC", "#7D8590", "#21262D"
    else:
        card, stroke, num, lab, bar = "#FFFFFF", "#D0D7DE", "#1F2328", "#636C76", "#EAEEF2"

    shown = reach[:5]
    label = ("Technology footprint: "
             + ", ".join(f"{name} in {count} of {total} repos" for name, count in shown)
             + (f"; roles: {', '.join(roles)}" if roles else ""))
    out = [
        svg_open(width, height, label),
        '<defs><linearGradient id="s" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%" stop-color="#58A6FF"/><stop offset="100%" stop-color="#7EE787"/>'
        "</linearGradient></defs>",
        f'<text x="{width / 2:.0f}" y="17" fill="{lab}" font-family="{FONT}" '
        f'font-size="13" font-weight="700" text-anchor="middle" letter-spacing="0.4">'
        f"Technology footprint</text>",
        f'<rect x="0.5" y="28.5" width="{width - 1}" height="{height - 29}" rx="14" '
        f'fill="{card}" stroke="{stroke}"/>',
    ]
    y = 62
    for name, count in shown:
        # Полоса — доля ПРОЕКТОВ, а не байтов: длина читается как «в скольких из
        # пяти», и подпись рядом говорит это словами.
        full = width - pad * 2
        filled = max(int(full * count / max(total, 1)), 6)
        out += [
            f'<text x="{pad}" y="{y}" fill="{num}" font-family="{FONT}" font-size="13.5" '
            f'font-weight="700">{escape(name)}</text>',
            f'<text x="{width - pad}" y="{y}" fill="{lab}" font-family="{FONT}" '
            f'font-size="12.5" font-weight="600" text-anchor="end">{count} / {total}</text>',
            f'<rect x="{pad}" y="{y + 8}" width="{full}" height="6" rx="3" fill="{bar}"/>',
            f'<rect x="{pad}" y="{y + 8}" width="{filled}" height="6" rx="3" fill="url(#s)"/>',
        ]
        y += 34

    if roles:
        y += 4
        out.append(f'<text x="{pad}" y="{y}" fill="{lab}" font-family="{FONT}" '
                   f'font-size="12" font-weight="700" letter-spacing="0.4">WHAT THEY DO</text>')
        y += 20
        # Роли переносятся по ширине карточки: строка `stack` длиннее её у
        # флагмана, и обрезать её значило бы молча потерять половину предмета.
        line = ""
        for role in roles:
            candidate = f"{line} · {role}" if line else role
            if len(candidate) * 6.4 > width - pad * 2:
                out.append(f'<text x="{pad}" y="{y}" fill="{num}" font-family="{FONT}" '
                           f'font-size="12.5" font-weight="600">{escape(line)}</text>')
                y += 18
                line = role
            else:
                line = candidate
        if line:
            out.append(f'<text x="{pad}" y="{y}" fill="{num}" font-family="{FONT}" '
                       f'font-size="12.5" font-weight="600">{escape(line)}</text>')
    return "\n".join(out) + "\n</svg>\n"


#: Ветка, куда змейку кладёт её собственный прогон. Она чужая по авторству
#: (Platane/snk), но своя по данным: рисуется по нашему календарю вкладов.
SNAKE_BRANCH = "output"

#: Клетка календаря у змейки помечена классом ``c``, а её размер задан СТИЛЕМ, а
#: не атрибутом: `Platane/snk` рисует ``<rect class="c" x=… y=…>`` без ширины и
#: высоты и красит их правилом ``.c{…;stroke-width:1px;…;width:12px;height:12px}``.
#: Читать размер приходится оттуда же, откуда его читает браузер.
#:
#: Взгляд назад обязателен: без него ``width:`` находится внутри
#: ``stroke-width:1px``, стоящего в том же правиле РАНЬШЕ, и клетка выходит
#: шириной в единицу. Сетка и тренд при этом сходятся друг с другом и оба
#: съезжают на полклетки — расхождение, которое набор не заметит, если считать
#: их одной величиной.
SNAKE_CELL_RULE = re.compile(r"\.c\{[^}]*?(?<![-\w])width:\s*([\d.]+)px")

#: Клетка помечена классом-СЛОВОМ ``c``, а не классом, НАЧИНАЮЩИМСЯ на «c», и
#: слово это может стоять в списке не первым. Признак ``class="c[^"]*"`` был
#: неверен в обе стороны сразу: он взял бы будущий ``class="caption"`` за столбец
#: сетки и не взял бы ``class="cell c"``. Сегодня у `Platane/snk` соседей нет —
#: классы там ровно ``c``, ``c c1a``, ``u u0``, ``s s0``, — и потому ошибка
#: молчала бы ровно до чужой правки (правило 195: починка называет соседей).
SNAKE_CELL_TAG = re.compile(r'<rect\b[^>]*\bclass="(?P<classes>[^"]*)"[^>]*>')
SNAKE_CELL_X = re.compile(r'\bx="([-\d.]+)"')


def snake_grid(body: str) -> tuple[list[float], float]:
    """Колонки календаря змейки и размер клетки — в её собственных координатах.

    ЗАЧЕМ ЭТО ЧИТАТЬ. Змейка нарисована С ПОЛЯМИ: её ``viewBox`` шире сетки на
    те 16–18 единиц, где змея входит в кадр и выходит из него. Тренд под сеткой
    отвечает на тот же вопрос теми же данными, и растянуть его на всю ширину
    картинки значит поставить неделю не под её столбцом. Расхождение вышло
    ровно таким: сетка занимала ``x ∈ [18, 862]``, линия шла от 5 до 875.

    ПОЛЯ У ЧУЖОЙ КАРТИНКИ НЕ УГАДЫВАЮТСЯ. Их задаёт чужой рисовальщик и вправе
    менять; вычесть «примерно 16» значило бы завести второе определение сетки,
    которое разойдётся с первым молча. Здесь спрашивается сама картинка.

    Пустой ответ — сетку прочесть не удалось. Это третий исход, а не поломка
    (правило 039): решает по нему тот, кто рисует.
    """
    xs = sorted({float(found.group(1))
                 for cell in SNAKE_CELL_TAG.finditer(body)
                 if "c" in cell.group("classes").split()
                 and (found := SNAKE_CELL_X.search(cell.group(0)))})
    size = SNAKE_CELL_RULE.search(body)
    return (xs, float(size.group(1))) if xs and size else ([], 0.0)


def snake_layer(theme: str) -> dict | None:
    """Змейка из ветки ``output``: тело, габарит и сетка. Нет — ``None``.

    ПОЧЕМУ ИНЛАЙНОМ, А НЕ ВЛОЖЕННОЙ КАРТИНКОЙ. Змейка анимирована классами и
    ``@keyframes``; вложенная через ``<image>``, она встала бы неподвижным
    кадром — площадка не проигрывает анимацию внутри картинки в картинке.
    Инлайн переносит её стили в наш документ, где они и работают.

    МОЛЧАНИЕ ИСТОЧНИКА — ТРЕТИЙ ИСХОД, А НЕ ПОЛОМКА. Прогон змейки идёт своим
    расписанием, и его ветки может не быть вовсе. Тогда полотно рисует
    собственный календарь: показать пустоту там, где обычно движение, значило
    бы соврать о том, что работы не было.
    """
    try:
        payload = _api(f"/repos/{SHOWCASE}/contents/snake-{theme}.svg?ref={SNAKE_BRANCH}")
        svg = base64.b64decode(payload["content"]).decode("utf-8")
    except (urllib.error.URLError, OSError, ValueError, KeyError, UnicodeDecodeError):
        return None
    head = re.match(r"<svg[^>]*>", svg)
    box = re.search(r'viewBox="\s*([-\d.]+)\s+([-\d.]+)\s+([\d.]+)\s+([\d.]+)"', svg)
    if not head or not box:
        return None
    left, top, width, height = (float(v) for v in box.groups())
    body = svg[head.end():].rsplit("</svg>", 1)[0]
    if "<style" not in body:
        return None
    columns, cell = snake_grid(body)
    return {"body": body, "left": left, "top": top, "width": width, "height": height,
            "columns": columns, "cell": cell}


def render_activity(days: list[tuple[str, int]], dark: bool,
                    snake: dict | None = None) -> str:
    """Календарь вкладов за год: 53 недели квадратиками, как у площадки.

    ПОЧЕМУ ОН ЗДЕСЬ, А НЕ ССЫЛКОЙ НА ЧУЖУЮ КАРТИНКУ. Календарь на странице
    профиля площадка рисует сама, но в README его нет: там он был бы внешним
    изображением, то есть чужой доступностью. Свой рисуется из тех же данных,
    которыми считаются серии, — второго определения активности не заводится.

    Уровни те же пять, что у площадки, и порог берётся от МАКСИМУМА периода, а
    не от абсолютного числа: у профиля с тремя вкладами в день и у профиля с
    тридцатью картинка иначе была бы либо пустой, либо сплошной.
    """
    cell, gap, head = 11, 3, 26
    # Под календарём — линия недельных сумм. Она отвечает на другой вопрос:
    # квадратики показывают ДНИ, линия — куда идёт год. У профилей, где такой
    # график берут с внешнего сервиса, он стоит отдельной картинкой; здесь это
    # тот же файл и те же данные — второго определения активности не заводится.
    # Хвост под трендом — под подпись «weekly · peak»: без него она выходит за
    # нижний край полотна и обрезается ровно там, где объясняет, что за линия.
    trend_h, trend_gap, trend_tail = 64, 14, 20
    weeks = (len(days) + 6) // 7
    width = max(weeks * (cell + gap) - gap, 1)
    grid_h = 7 * (cell + gap) - gap
    height = head + grid_h + (trend_gap + trend_h + trend_tail if len(days) > 7 else 0)
    if dark:
        empty, tones, lab = "#161B22", ("#0E4429", "#006D32", "#26A641", "#39D353"), "#7D8590"
        line, area, axis = "#58A6FF", "#58A6FF22", "#21262D"
    else:
        empty, tones, lab = "#EBEDF0", ("#9BE9A8", "#40C463", "#30A14E", "#216E39"), "#636C76"
        line, area, axis = "#0969DA", "#0969DA1A", "#EAEEF2"

    peak = max((count for _, count in days), default=0)

    # ЦЕНТР ПОЛОТНА — ОДИН СЛОЙ, А НЕ ДВА. Календарь вкладов рисуется либо
    # змейкой, либо своими квадратиками, но никогда обоими: одна и та же сетка,
    # показанная дважды, — это два места, где она может разойтись.
    if snake:
        width = int(snake["width"])
        grid_h = int(snake["height"])
    height = head + grid_h + (trend_gap + trend_h + trend_tail if len(days) > 7 else 0)

    # ГДЕ У ПОЛОТНА СЕТКА. Своя начинается в нуле и кончается на краю картинки;
    # у змейки поля вокруг сетки принадлежат ЗМЕЕ, а не календарю. Столбцы
    # считаются один раз и здесь — по ним равняются и квадратики, и тренд, и
    # обе подписи: разойтись им негде, потому что источник один.
    if not snake:
        columns, grid_cell = [index * (cell + gap) for index in range(weeks)], cell
    else:
        columns = [x - snake["left"] for x in snake["columns"]]
        grid_cell = snake["cell"] or cell
    # Сетку у змейки прочесть не удалось — равняемся по всей ширине картинки,
    # как до этой правки. Хуже, но честно: третий исход, а не поломка.
    edge = (columns[0], columns[-1] + grid_cell) if columns else (0.0, float(width))

    # ПОДПИСЬ НЕ ПОВТОРЯЕТ СОСЕДА. Сумма вкладов за год стоит строкой выше — в
    # карточке профиля, и второй раз она здесь не добавляет ничего, зато заводит
    # второе место, где то же число может устареть (правило 090). Полотно
    # отвечает на свой вопрос: слева вверху дневной максимум, слева внизу
    # недельный, и вместе они читаются как легенда к двум видам одних данных.
    caption = f"daily · peak {peak}"
    label = (f"A year of contributions day by day, peak {peak} in a day, "
             f"weekly trend below")
    if snake:
        label += "; a snake crossing the contribution grid"
    out = [
        svg_open(width, height, label),
    ]
    if snake:
        # Движение отключаемо. Погашенная анимация оставляет клетки в их
        # собственных цветах и змейку на месте — кадр остаётся читаемым, а не
        # пустым (правило доступности здесь важнее эффекта).
        out.append("<style>@media (prefers-reduced-motion: reduce) "
                   "{ * { animation: none !important } }</style>")
    out.append(
        f'<text x="{edge[0]:.1f}" y="14" fill="{lab}" font-family="{FONT}" '
        f'font-size="12" font-weight="600">{escape(caption)}</text>'
    )

    if snake:
        # Змейка нарисована в своих координатах с полями: сдвигаем её под нашу
        # подпись, а не подгоняем полотно под чужой viewBox.
        out.append(f'<g transform="translate({-snake["left"]:.0f} '
                   f'{head - snake["top"]:.0f})">{snake["body"]}</g>')
    else:
        for index, (date, count) in enumerate(days):
            column, row = divmod(index, 7)
            # Ноль — не уровень: пустой день красят фоном, иначе самый слабый
            # тон означал бы «работа была», когда её не было.
            fill = empty if not count else tones[min(int(count * len(tones) / max(peak, 1)),
                                                     len(tones) - 1)]
            out.append(
                f'<rect x="{columns[column]:.0f}" y="{head + row * (cell + gap)}" '
                f'width="{cell}" height="{cell}" rx="2" fill="{fill}"><title>{escape(date)}: '
                f"{count}</title></rect>"
            )

    if len(days) > 7:
        # Недельные суммы, а не сглаживание по дням: неделя — естественный
        # период работы, и линия по ней читается без объяснений, чем окно
        # усреднения. Точек ровно столько же, сколько столбцов календаря, и
        # они стоят под своими столбцами — иначе два вида одних данных
        # разъезжались бы по горизонтали.
        sums = [sum(count for _, count in days[i:i + 7]) for i in range(0, len(days), 7)]
        top = max(sums) or 1
        base = head + grid_h + trend_gap + trend_h
        # ТОЧКА НЕДЕЛИ СТОИТ ПО ЦЕНТРУ СВОЕГО СТОЛБЦА, а не по доле ширины.
        # Столбцы известны поимённо — свои по построению, чужие прочитаны у
        # змейки. Если их оказалось не столько, сколько недель, точки
        # раскладываются ровно по ширине сетки: разойтись на одну неделю лучше,
        # чем на поля всей картинки.
        if len(columns) == len(sums):
            xs = [x + grid_cell / 2 for x in columns]
        else:
            span = edge[1] - edge[0] - grid_cell
            xs = [edge[0] + grid_cell / 2 + index * span / max(len(sums) - 1, 1)
                  for index in range(len(sums))]
        points = [(x, base - value / top * (trend_h - 10))
                  for x, value in zip(xs, sums)]
        path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}"
                        for i, (x, y) in enumerate(points))
        out += [
            f'<line x1="{edge[0]:.1f}" y1="{base}" x2="{edge[1]:.1f}" y2="{base}" '
            f'stroke="{axis}" stroke-width="1"/>',
            f'<path d="{path} L{points[-1][0]:.1f},{base} L{points[0][0]:.1f},{base} Z" '
            f'fill="{area}"/>',
            f'<path d="{path}" fill="none" stroke="{line}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>',
            f'<text x="{edge[0]:.1f}" y="{base + 15}" fill="{lab}" '
            f'font-family="{FONT}" font-size="11" font-weight="600">'
            f'weekly · peak {top}</text>',
        ]
    return "\n".join(out) + "\n</svg>\n"


def aria_of(svg: str) -> str:
    """Подпись картинки, как её объявляет сама картинка — по её тексту.

    У разделителей ``aria-label`` нет намеренно — это декорация, и alt у неё
    пустой.
    """
    match = re.search(r'aria-label="([^"]*)"', svg)
    return match.group(1) if match else ""


def aria_label(svg: pathlib.Path) -> str:
    """То же, но для картинки, лежащей в дереве.

    Остаётся ради рукодельных: шапки, печатающейся строки и разделителя. Для
    них файл и есть источник — сборка их не рисует и перерисовать не может.
    """
    return aria_of(svg.read_text(encoding="utf-8"))


def asset_version(name: str, drawn: dict[str, str] | None = None) -> str:
    """Отпечаток содержимого картинки — восемь знаков хеша.

    Нужен не для красоты адреса, а против кэша. Картинки на странице профиля
    отдаёт прокси площадки, и ключом кэша служит АДРЕС. Сборка переписывает
    файлы, не меняя имён, — значит адрес прежний, и читателю сколько-то времени
    показывают вчерашнюю картинку. Проверено на живом примере: страница
    показывала баннер без плашек и с числом коммитов на два меньше, когда в
    репозитории уже лежал новый.

    Это ровно то, от чего витрина защищается сборкой: число, устаревшее молча.
    Гейт на маркеры тут не помогает — в репозитории всё верно, врёт показ.

    СЧИТАЕТСЯ ОТ ТОГО, ЧТО ОПУБЛИКУЕТСЯ, А НЕ ОТ ТОГО, ЧТО ЛЕЖИТ В ДЕРЕВЕ.
    Производных картинок в дереве больше нет (правило 160), и читать их оттуда
    стало не только нечем, но и неверно: отпечаток обязан описывать ту картинку,
    которую увидит читатель. Нарисованное берётся из ``drawn``, с диска читаются
    только рукодельные — шапка, печатающаяся строка, разделитель: для них файл и
    есть источник. Тот же довод, что у ``sync_alt``: свой вывод не перечитывают.
    """
    if drawn and name in drawn:
        return hashlib.sha256(drawn[name].encode("utf-8")).hexdigest()[:8]
    handmade = ROOT / "assets" / f"{name}.svg"
    if not handmade.exists():
        # НИ НАРИСОВАНО, НИ ЛЕЖИТ В ДЕРЕВЕ — отпечатка не существует, и это не
        # поломка. Так бывает у картинки, чей источник в этот раз промолчал:
        # профильные числа приходят из `/users/*` и GraphQL, окну они закрыты, и
        # карточка не перерисовывается вовсе (задача #139). Ссылка остаётся без
        # `?v=`, то есть ровно в том виде, в каком её написал человек: версия
        # нужна против кэша, а кэшировать нечего, пока картинки нет.
        return ""
    return hashlib.sha256(handmade.read_bytes()).hexdigest()[:8]


def stamp_assets(text: str, drawn: dict[str, str] | None = None) -> tuple[str, int]:
    """Проставляет отпечаток каждой ссылке на картинку витрины.

    Меняет и ``src``, и ``srcset``: тёмную с светлой кэшируют по отдельности, и
    забытый ``srcset`` означал бы, что половина читателей по-прежнему видит
    старое.

    ЗАОДНО РЕШАЕТ, КУДА ССЫЛКА ВЕДЁТ. Производное живёт в ветке ``assets`` и
    адресуется по ней; рукодельное лежит в дереве и адресуется относительно.
    Признак — не имя файла, а ФАКТ: нарисовала ли эту картинку текущая сборка
    (правило 147 — переключатель по имени отменяет операцию молча, стоит
    префиксу разойтись). Появится новая плитка — она поедет в ветку сама, без
    правки списка; перестанет рисоваться — вернётся в дерево тем же порядком.

    Возвращает число заменённых ссылок: ноль означает, что разметка изменилась
    и картинки перестали находиться, — а это отказ, а не «нечего делать».
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        version = asset_version(name, drawn)
        if drawn and name in drawn:
            return f"{ASSETS_BRANCH}/{name}.svg?v={version}"
        if not version:
            # Отпечатка нет: картинку эта сборка не рисовала и в дереве её нет.
            # Ссылка остаётся там, куда её написали, — в ветке `assets`, если
            # она уже была туда написана. Перевести её в дерево значило бы
            # указать на файл, которого там не будет никогда (правило 160).
            return match.group(0)
        return f"./assets/{name}.svg?v={version}"

    return re.subn(ASSET_LINK, replace, text)


def sync_alt(text: str, fresh: dict[str, str] | None = None) -> tuple[str, int]:
    """Приводит alt каждой картинки витрины к её же ``aria-label``.

    Alt правится вместе с картинкой не для порядка: он невидим глазу, но именно
    его читают скринридеры и текстовые выгрузки страницы. Разошедшись с
    картинкой, он врёт тише всех — «32 checks per PR» прожили в alt на мерж
    дольше, чем на самом изображении. Поэтому подпись у картинки одна, и
    хранится она внутри SVG.
    """
    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        # Подпись только что нарисованной картинки берётся из памяти. Читать её
        # с диска значило бы читать собственный вывод: генератор питается
        # источниками и ничем из того, что сам записал. С диска берутся только
        # рукодельные SVG — шапка, печатающаяся строка, разделитель: для них
        # файл и есть источник.
        if fresh and name in fresh:
            label = fresh[name]
        else:
            handmade = ROOT / "assets" / f"{name}.svg"
            if not handmade.exists():
                # Картинку эта сборка не рисовала, и в дереве её нет: подпись
                # взять неоткуда. Оставляем ту, что написал человек, — она
                # относится к картинке, лежащей в ветке `assets` от прошлого
                # прогона. Затереть её пустой значило бы отнять у скринридера
                # единственное, что он читает (задача #139).
                return match.group(0)
            label = aria_label(handmade)
        return f"{match.group('head')}{label.replace(chr(34), chr(39))}{match.group('tail')}"

    return re.subn(
        rf'(?P<head><img src="(?:\./assets/|{re.escape(ASSETS_BRANCH)}/)'
        rf'(?P<name>[a-z0-9-]+)\.svg(?:\?v=[0-9a-f]+)?" alt=")[^"]*(?P<tail>")',
        replace,
        text,
    )


def hollow_regions(text: str, values: dict[str, object]) -> list[str]:
    """Области, которые сборка заполняет, а в файле они пусты.

    ПРЕДМЕТ ОПЛАЧЕН В ТОТ ЖЕ ДЕНЬ. Изменение #184 перевело рукодельный блок
    карточек на сборку и оставило маркеры пустыми: заполнить их некому до
    следующего суточного прогона, а запустить его из окна нельзя. Витрина
    осталась без блока статистики целиком, и **все гейты были зелёными** —
    ``--check`` смотрел на генератор, а страницу в этот момент определял коммит.
    Чинилось это #185, руками.

    ЭТО ФИКСТУРА, А НЕ ВТОРОЙ ГЕЙТ (правило 072). Гейты витрины проверяют
    НАМЕРЕНИЕ до прогона: маркеры на месте, источники живы, alt проставлен.
    Здесь проверяется ФАКТ — что лежит в файле, который уедет в общую ветку.
    Причину ловит гейт, факт ловит фикстура, и слепы они в разных местах.

    ПРЕДИКАТ НЕСИММЕТРИЧЕН НАМЕРЕННО. Судится только случай «сборка даёт
    содержимое, а в файле пусто»: обратный — «сборка не даёт ничего» — законен и
    означает, что промолчал источник; за ним следит ``unanswered``. Пустое к
    пустому тоже законно: так выглядит область, которую ещё не наполняли.
    """
    hollow = []
    for key, value in values.items():
        if not str(value).strip():
            continue
        found = re.search(rf"<!--m:{key}-->(.*?)<!--/m:{key}-->", text, flags=re.S)
        if found and not found.group(1).strip():
            hollow.append(key)
    return hollow


def patch_readme(values: dict[str, object], fresh: dict[str, str],
                 drawn: dict[str, str] | None = None, write: bool = True) -> None:
    """Обновляет числа между маркерами ``<!--m:key-->`` … ``<!--/m:key-->``.

    Если маркер не нашёлся, скрипт падает, а не проходит молча: ``re.sub`` без
    совпадения ничего не делает и возвращает тот же текст — витрина замерла бы,
    workflow отчитался бы «числа не изменились», и отказ выглядел бы как
    отсутствие изменений. Ровно от этого молчания скрипт и написан.
    """
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")

    missing = []
    for key, value in values.items():
        text, count = re.subn(
            rf"(<!--m:{key}-->).*?(<!--/m:{key}-->)",
            lambda m, v=value: f"{m.group(1)}{v}{m.group(2)}",
            text,
            flags=re.S,
        )
        if not count:
            missing.append(key)
    if missing:
        raise SystemExit(f"в README нет маркеров: {', '.join(missing)}")

    # ФАКТ, А НЕ НАМЕРЕНИЕ: проверяется файл ДО подстановки. Область, которую
    # сборка наполняет, не уезжает в общую ветку пустой — иначе страница стоит
    # без неё до следующего прогона, а прогон идёт по расписанию.
    hollow = hollow_regions(readme.read_text(encoding="utf-8"), values)
    if hollow:
        raise SystemExit(
            f"области пусты в файле, хотя сборка их наполняет: {', '.join(hollow)}.\n"
            f"  Между слиянием и следующим прогоном страница будет без них — а прогон\n"
            f"  идёт по расписанию, и запустить его из окна нельзя.\n"
            f"  Положите в маркеры то, что сборка туда напишет: она перепишет это\n"
            f"  тем же содержимым, а пустая разметка живёт до самого прогона."
        )

    # Сначала считаем картинки грубым выражением («любой <img> на assets/»),
    # потом строгим проставляем alt — и сверяем счётчики. Иначе защита
    # проверяет саму себя: строгое выражение не видит поехавшую разметку, не
    # находит её — и молча докладывает, что всё проставлено.
    expected = len(re.findall(r"<img[^>]*assets/[a-z0-9-]+\.svg", text))
    check_focus_limit(text)
    text, patched = sync_alt(text, fresh)
    if patched != expected:
        raise SystemExit(f"alt проставлен у {patched} картинок из {expected} — разметка изменилась")

    # Отпечаток содержимого в адресе: прокси площадки кэширует картинки ПО
    # АДРЕСУ, а сборка переписывает их, не меняя имён. Без отпечатка читатель
    # какое-то время видит вчерашнюю картинку при верном репозитории — то есть
    # число, устаревшее молча, ровно то, от чего эта сборка и заведена.
    text, stamped = stamp_assets(text, drawn)
    if not stamped:
        raise SystemExit(
            "ни одной ссылки на картинки витрины не нашлось — разметка изменилась.\n"
            "  Отпечаток содержимого проставить некуда, а без него страница показывает кэш."
        )

    if write:
        readme.write_text(text, encoding="utf-8")


# Ноль у метрики означает, что источник не ответил, и переписывать витрину по
# нему нельзя. Исключений сейчас нет: единственное — пустой пул задач новичка —
# ушло вместе с блоком, который его показывал. Множество оставлено пустым, а не
# удалено: разница между «ноль — состояние» и «ноль — молчание» существует и
# вернётся вместе с первой же метрикой, у которой ноль законен.
ZERO_IS_A_STATE: set[str] = set()


def unanswered(measured: dict[str, object]) -> list[str]:
    """Метрики, по которым источник не ответил.

    Проверяются СЫРЫЕ значения — до того, как число превратится в строку для
    показа. Сторож, стоявший после форматирования, пропускал «0000+ tests»:
    ноль тестов давал именно такую плитку, а сравнение шло с ``"0"``.

    Ноль ищется по цифрам, а не по равенству строке: измеренное значение
    приходит с единицей измерения (``"0%"`` от бейджа покрытия), и сравнение
    с ``"0"`` там не срабатывает так же, как не срабатывало на ``"0000+"``.
    Пусто — это отсутствие ответа, а не маленькое число: ``0.5%`` и ``3.14``
    сторож пропускает, потому что среди цифр есть ненулевая.
    """
    empty = []
    for key, value in measured.items():
        text = str(value).strip()
        if not text:
            # Пустая строка — не ответ ни для одной метрики: «ноль» и
            # «источник промолчал» это разные вещи.
            empty.append(key)
            continue
        digits = [character for character in text if character.isdigit()]
        if digits and set(digits) == {"0"} and key not in ZERO_IS_A_STATE:
            empty.append(key)
    return empty



def selftest() -> int:
    """Прогоняет через сторож то, что он обязан отвергнуть и пропустить.

    Правило 140: пока такого прогона нет, «сторож не пропустит пустую метрику» —
    обещание. Зелёная сборка на живых источниках подтверждает лишь, что скрипт
    ходит в сеть: сторож, всегда возвращающий пустой список, проходит её
    идеально — ровно это и происходило, пока он стоял после форматирования.

    Обе стороны, а не одна. Набор из одних «обязан отвергнуть» не видит ложного
    отказа, а он здесь дороже: сборка, падающая на честном маленьком числе,
    останавливает витрину без причины.

    ВЕРДИКТ ОДИН И СТОИТ В КОНЦЕ, и наверх его поднимать нельзя. Он там уже
    стоял — сразу после баннера, — и три последние группы случаев дописывали в
    ``broken`` уже ЗА ``return``: вызов без клона грейдера, сверка ответа с
    каталогом и отказ с адресом печатались, но не судили. Проверено подставным
    провалом в последней группе: самопроверка отвечала «пройдена» и кодом 0.
    """
    live = {
        "projects": "|таблица|", "modules": 218, "required": 11, "os": 3, "py": 2,
        "exp": "3.14", "releases": 12, "rules": 140,
        "signed": 80, "signed-total": 81,
        "tests": 4321, "coverage": "92.4%", "checks per PR": 17,
    }
    cases = [
        ("живые источники", live, []),
        ("ноль тестов — тот самый «0000+»", {**live, "tests": 0}, ["tests"]),
        ("999 тестов: источник ответил", {**live, "tests": 999}, []),
        ("покрытие «0%» — ноль с единицей измерения", {**live, "coverage": "0%"}, ["coverage"]),
        ("покрытие «0.0%»", {**live, "coverage": "0.0%"}, ["coverage"]),
        ("покрытие «0.5%»: маленькое, но не пустое", {**live, "coverage": "0.5%"}, []),
        ("экспериментальные версии не прочитаны", {**live, "exp": ""}, ["exp"]),
    ]

    broken = []
    for name, measured, expected in cases:
        got = unanswered(measured)
        if got != expected:
            broken.append(f"{name}: ожидалось {expected or 'пропуск'}, вышло {got or 'пропуск'}")
        print(f"  {'отвергнут' if got else 'пропущен '} — {name}")

    # ── ранжирование акцентов ──────────────────────────────────────────────
    lead = {"stars": 9, "commits": 900, "issues": 90, "releases": 9, "prs": 90}
    mid = {"stars": 5, "commits": 500, "issues": 50, "releases": 5, "prs": 50}
    tail = {"stars": 0, "commits": 1, "issues": 0, "releases": 0, "prs": 0}
    rank_cases = [
        ("впереди по всем категориям — первый",
         {"a": lead, "b": mid, "c": tail}, ["a", "b", "c"]),
        ("порядок не зависит от порядка в словаре",
         {"c": tail, "a": lead, "b": mid}, ["a", "b", "c"]),
        ("равные значения делят место, ничья решается именем",
         {"b": dict(mid), "a": dict(mid)}, ["a", "b"]),
        ("звёзды не перевешивают четыре остальные категории",
         {"a": {**mid, "stars": 0}, "b": {**tail, "stars": 99}}, ["a", "b"]),
    ]
    for name, stats, expected in rank_cases:
        got = rank_featured(stats)
        if got != expected:
            broken.append(f"ранжирование, {name}: ожидалось {expected}, вышло {got}")
        print(f"  порядок {got} — {name}")

    # ── баннер: то, что обязано быть в картинке ────────────────────────────
    accents = [
        {"title": "Alpha", "tagline": "первый по всему", "stack": "CLI · web",
         "badges": [("release", "v1.2.3", "info"), ("CI", "success", "ok")], "stats": lead},
        {"title": "Beta", "tagline": "середина", "stack": "docs",
         "badges": [("CI", "failure", "warn")], "stats": mid},
        {"title": "Gamma", "tagline": "хвост", "stack": "content", "badges": [], "stats": tail},
    ]
    svg = render_featured(accents, dark=True)
    label = svg.split('aria-label="')[1].split('">')[0]
    checks = [
        ("подпись перечисляет все акценты, а не первый",
         all(a["title"] in label for a in accents)),
        ("подпись несёт описание, а не только числа",
         all(a["tagline"] in label for a in accents)),
        ("подпись несёт показатели", "release v1.2.3" in label and "CI failure" in label),
        ("подпись несёт стек", all(a["stack"] in label for a in accents)),
        ("плашка есть у каждого показателя, включая отсутствующий",
         svg.count('rx="12"') == sum(len(a["badges"]) for a in accents)),
        ("подпись не двоит точку на стыке описания и показателей",
         ".." not in label),
        ("показатель подписан одинаково и с предметом, и без него",
         set(BADGE_LABELS) == set(BADGE_KINDS)),
        ("подпись несёт измеренные числа", "1664" not in svg and "900 commits" in svg),
        ("просьба уменьшить движение уважается", "prefers-reduced-motion" in svg),
        ("первый акцент виден без стиля", 'class="accent" opacity="1"' in svg),
        ("остальные без стиля скрыты", svg.count('class="accent" opacity="0"') == len(accents) - 1),
        ("у каждого акцента своя задержка",
         all(f"animation-delay: {i * ACCENT_SECONDS}s" in svg for i in range(len(accents)))),
    ]
    for name, ok in checks:
        if not ok:
            broken.append(f"баннер: {name} — нет")
        print(f"  {'да ' if ok else 'НЕТ'} — баннер: {name}")

    # ── обязательные показатели проекта ────────────────────────────────────
    full = {"release": {"endpoint": "release"}, "ci": {"workflow": "ci.yml"},
            "coverage": {"endpoint": "cov"}, "version": {"endpoint": "version"}}

    def config_of(badges: dict) -> dict:
        return {"required_badges": list(BADGE_KINDS),
                "projects": [{"title": "X", "repo": "o/r", "badges": badges}]}

    badge_cases = [
        ("ответ есть по всем четырём", config_of(full), False),
        ("показатель пропущен целиком", config_of({k: v for k, v in full.items() if k != "version"}), True),
        ("ответ пустым словарём", config_of({**full, "coverage": {}}), True),
        ("отказ без причины", config_of({**full, "coverage": {"none": ""}}), True),
        ("отказ с причиной — законный ответ",
         config_of({**full, "coverage": {"none": "тестов нет: репозиторий текстовый"}}), False),
        ("показатель, которого сборка не умеет", config_of({**full, "stars": {"none": "x"}}), True),
        # Значок в ветке по умолчанию — такой же законный ответ, как значок на
        # ветке `badges`. Случай заведён потому, что вторая форма появилась
        # позже первой: договор, знающий одну форму, отверг бы каталог правил.
        ("покрытие значком в ветке по умолчанию",
         config_of({**full, "coverage": {"badge": "coverage"}}), False),
        # У «release» три законных источника, потому что проекты в разной
        # зрелости: собственный значок, выпуски площадки, версия пакета.
        # Договор, знающий один, отверг бы проект, у которого другой.
        ("выпуск от площадки — законный ответ",
         config_of({**full, "release": {"release": True}}), False),
        ("выпуск версией пакета — законный ответ",
         config_of({**full, "release": {"pypi": "имя-пакета"}}), False),
        ("версия отказом с причиной — законный ответ",
         config_of({**full, "version": {"none": "версия не публикуется значком"}}), False),
    ]
    for name, cfg, must_reject in badge_cases:
        try:
            check_badges(cfg)
            rejected = False
        except SystemExit:
            rejected = True
        if rejected is not must_reject:
            broken.append(f"показатели, {name}: ожидалось {'отказ' if must_reject else 'пропуск'}")
        print(f"  {'отвергнут' if rejected else 'пропущен '} — показатели: {name}")

    # ── пакет обязан вести обратно на репозиторий ─────────────────────────
    # Совпадения имени мало: чужой пакет с похожим названием даёт
    # правдоподобное число, и месяц давал (release/pypi 2.0.0 у соседа, чей
    # собственный выпуск — v0.2.0).
    ownership_cases = [
        ("репозиторий объявлен в Repository", "o/r",
         {"project_urls": {"Repository": "https://github.com/o/r"}}, True),
        ("репозиторий объявлен в Homepage", "o/r",
         {"project_urls": {"Homepage": "https://github.com/o/r/"}}, True),
        ("старое поле home_page тоже считается", "o/r",
         {"home_page": "https://github.com/o/r"}, True),
        ("регистр владельца не важен", "ArtVsMark/Repo",
         {"project_urls": {"Repository": "https://github.com/artvsmark/repo"}}, True),
        ("чужой пакет с похожим именем", "ArtVsMark/Claude-Code_Usage-Token",
         {"project_urls": {"Repository": "https://github.com/Maex-z9/CC_Usage"}}, False),
        ("ссылок нет вовсе", "o/r", {}, False),
        ("ссылки пустые", "o/r", {"home_page": None, "project_urls": None}, False),
        # Чужой репозиторий, имя которого НАЧИНАЕТСЯ с нашего. Первая редакция
        # проверки искала подстроку и признавала его своим — случай заведён
        # подделкой и сразу нашёл дефект.
        ("чужой репозиторий с нашим именем в начале", "o/r",
         {"project_urls": {"Repository": "https://github.com/o/r-fork-by-someone"}}, False),
        ("страница задач своего репозитория — своя", "o/r",
         {"project_urls": {"Issues": "https://github.com/o/r/issues"}}, True),
        ("адрес для клона тоже свой", "o/r",
         {"project_urls": {"Repository": "https://github.com/o/r.git"}}, True),
    ]
    for name, repo_name, info, must_own in ownership_cases:
        got = owns_package(repo_name, info)
        if got is not must_own:
            broken.append(f"принадлежность пакета, {name}: ожидалось {must_own}, вышло {got}")
        print(f"  {'свой  ' if got else 'чужой '} — пакет: {name}")

    # ── отказ по показателю сверяется со значком, а не с веткой ───────────
    # Ветка `badges` общая на все показатели: сосед заводит её ради покрытия, а
    # краснеет ответ и по версии, которой там нет. Набор ЗОВЁТ проверку на
    # подставном дереве и смотрит на её ответ, а не повторяет условие
    # (правило 150).
    # Файл называется значком по СОДЕРЖИМОМУ, а не по имени: у соседа
    # `coverage.json` четыре часа был shields-значком, а потом стал отчётом о
    # покрытии официального Python карточками — другой предмет под тем же
    # именем. Подделка отдаёт и список, и тела файлов.
    BADGE = {"schemaVersion": 1, "message": "99%"}
    REPORT = {"schema": 1, "totals": {"ratio": 0.79}}
    absence_cases = [
        ("покрытие есть, версии нет — краснеет только покрытие",
         {"coverage.json": BADGE, "facts.json": REPORT}, {"coverage": True, "version": False}),
        ("грейдерская форма имени тоже находится",
         {"coverage-combined.json": BADGE}, {"coverage": True, "version": False}),
        ("значков нет вовсе — оба отказа законны", {}, {"coverage": False, "version": False}),
        ("обе публикации — краснеют оба",
         {"coverage.json": BADGE, "version.json": BADGE}, {"coverage": True, "version": True}),
        ("имя значка при чужом предмете внутри — не значок",
         {"coverage.json": REPORT}, {"coverage": False, "version": False}),
    ]
    saved_api = globals()["_api"]

    def _fake(files):
        """Ветка `badges` с этими файлами; ветки по умолчанию нет вовсе."""
        def call(path):
            where, _, query = path.partition("?")
            if "ref=badges" not in query:
                return []
            if where.endswith("/badges"):
                return [{"type": "file", "name": n} for n in files]
            return {"content": base64.b64encode(
                json.dumps(files[where.rsplit("/", 1)[-1]]).encode("utf-8")).decode()}
        return call

    try:
        for name, files, expected in absence_cases:
            globals()["_api"] = _fake(files)
            for kind, must_reject in expected.items():
                # ВОЗВРАЩАЕТ НАХОДКУ, А НЕ ПАДАЕТ: расхождение с чужим
                # репозиторием красит проверку изменения, но не роняет
                # пересчёт остальных чисел (039).
                said = verify_absence("o/r", kind, "предмета нет")
                if bool(said) is not must_reject:
                    broken.append(f"отказ по «{kind}», {name}: "
                                  f"ожидалось {'находка' if must_reject else 'молчание'}, "
                                  f"вышло {said!r}")
                print(f"  {'находка ' if said else 'молчание'} — отказ «{kind}»: {name}")
        # Отказ обязан НАЗЫВАТЬ найденное: «показатель публикуется» без имени
        # файла — это отказ, по которому нечего чинить (правило 158).
        globals()["_api"] = _fake({"coverage-combined.json": BADGE})
        said = verify_absence("o/r", "coverage", "тестов нет")
        if not said:
            broken.append("находки по покрытию нет при живом значке")
        elif "coverage-combined.json" not in said:
            broken.append("находка по покрытию не называет найденный значок")
    finally:
        globals()["_api"] = saved_api

    # ── серии дней с вкладами (задача #139) ───────────────────────────────
    # Считается по календарю площадки, и цена ошибки — неверное число на
    # витрине, которое выглядит измеренным. Случаи взяты по границам, а не по
    # «типичному профилю»: обрыв, ноль сегодня, дыра посередине, пустой год.
    def day(offset: int, count: int, base: str = "2026-09-07") -> tuple[str, int]:
        return ((dt.date.fromisoformat(base) - dt.timedelta(days=offset)).isoformat(), count)

    streak_cases = [
        ("пустой календарь", [], (0, 0)),
        ("вкладов нет вовсе", [day(i, 0) for i in range(5)], (0, 0)),
        ("три дня подряд до сегодня", [day(2, 1), day(1, 2), day(0, 3)], (3, 3)),
        # Календарь площадки заполняется с задержкой: ноль сегодня серию не
        # рвёт, иначе витрина показывала бы ноль в полдень рабочего дня.
        ("ноль сегодня — серия по вчера", [day(3, 1), day(2, 1), day(1, 1), day(0, 0)], (3, 3)),
        ("два нуля подряд рвут серию", [day(4, 1), day(3, 1), day(2, 0), day(1, 0), day(0, 1)], (1, 2)),
        ("дыра посередине", [day(5, 1), day(4, 1), day(3, 1), day(2, 0), day(1, 1), day(0, 1)], (2, 3)),
        ("самая длинная в прошлом, текущей нет",
         [day(9, 1), day(8, 1), day(7, 1), day(6, 1), day(5, 0), day(4, 0), day(3, 0),
          day(2, 0), day(1, 0), day(0, 0)], (0, 4)),
        ("один день", [day(0, 7)], (1, 1)),
    ]
    for name, days, expected in streak_cases:
        got = streaks(days, "2026-09-07")
        if got != expected:
            broken.append(f"серии, {name}: ожидалось {expected}, вышло {got}")
        print(f"  {str(got):<8} — серии: {name}")

    # Хвост недели площадка отдаёт целиком, включая ненаступившие дни. Считать
    # их нулями значило бы обрывать серию будущим.
    future = [day(1, 1), day(0, 2), day(-1, 0), day(-2, 0)]
    if streaks(future, "2026-09-07") != (2, 2):
        broken.append(f"серии: будущие дни оборвали текущую — {streaks(future, '2026-09-07')}")
    print(f"  {str(streaks(future, '2026-09-07')):<8} — серии: ненаступившие дни не рвут серию")

    # ── след технологий: охват, а не байты ────────────────────────────────
    # Замер, из-за которого карточка считает иначе типовой: по нашим пяти
    # репозиториям Python даёт 96% объёма, и круговая диаграмма из этого
    # сообщает только язык. Охват отвечает на другой вопрос — в скольких
    # проектах язык встречается вообще.
    reach_sample = [("Python", 5), ("HTML", 3), ("JavaScript", 1), ("CSS", 1), ("Shell", 1)]
    roles_sample = ["CLI", "web UI", "GUI", "pytest plugin", "OS sandbox", "docs", "RU/EN"]
    for dark in (True, False):
        stack = render_stack(reach_sample, roles_sample, 5, dark)
        theme = "тёмная" if dark else "светлая"
        stack_checks = [
            ("полос столько же, сколько языков", stack.count("url(#s)") == len(reach_sample)),
            ("подпись несёт охват", "Python in 5 of 5 repos" in aria_of(stack)),
            ("подпись несёт роли", "roles:" in aria_of(stack)),
            ("роли попали в картинку", "pytest plugin" in stack),
            ("высота равна карточке чисел", 'height="308"' in stack),
        ]
        for name, ok in stack_checks:
            if not ok:
                broken.append(f"след технологий ({theme}): {name} — нет")
            print(f"  {'да ' if ok else 'НЕТ'} — след технологий ({theme}): {name}")

    # Пустой ответ источника не роняет рисование: у нового профиля языков может
    # не быть вовсе, и это состояние, а не сбой.
    try:
        render_stack([], [], 0, True)
    except Exception as e:
        broken.append(f"след технологий: пустой охват уронил рисование — {e!r}")
    print("  да  — след технологий: пустой охват рисуется")

    # Длинный список ролей ПЕРЕНОСИТСЯ, а не обрезается: у флагмана строка
    # длиннее карточки, и молча потерять половину предмета нельзя.
    many = render_stack(reach_sample, ["роль-" + str(i) for i in range(20)], 5, True)
    if many.count("font-size=\"12.5\"") < 3:
        broken.append("след технологий: длинный список ролей не перенесён по строкам")
    print("  да  — след технологий: длинные роли переносятся")

    # ── карточка профиля рисуется и называет себя ─────────────────────────
    eng_stats = {"repos": 12, "stars": 6, "followers": 4,
                 "contributions": 1287, "streak": 12, "longest": 41}
    for dark in (True, False):
        card = render_engineering(eng_stats, dark)
        theme = "тёмная" if dark else "светлая"
        checks_card = [
            ("плиток ровно шесть", card.count('rx="14"') == len(ENGINEERING_TILES)),
            ("подпись несёт числа", "1 287" in card and "41" in card),
            ("подпись картинки не пуста", len(aria_of(card)) > 30),
            ("тема разная", ("#0D1117" in card) is dark),
        ]
        for name, ok in checks_card:
            if not ok:
                broken.append(f"карточка профиля ({theme}): {name} — нет")
            print(f"  {'да ' if ok else 'НЕТ'} — карточка профиля ({theme}): {name}")

    # Разряды разделяются, иначе «1287» читается как год. Пробел неразрывный не
    # нужен: это текст SVG, переносов в нём нет.
    if "1 287" not in render_engineering(eng_stats, True):
        broken.append("карточка профиля: тысячи не разделены — число читается хуже")

    # Текст в подписи ЭКРАНИРУЕТСЯ: имя подписи приходит из данных, и амперсанд
    # в нём порвал бы XML молча.
    tricky = render_engineering({**eng_stats, "repos": "<&>"}, True)
    if "<&>" in tricky or "&lt;&amp;&gt;" not in tricky:
        broken.append("карточка профиля: значение не экранировано — XML порвётся молча")
    print("  да  — карточка профиля: значение экранируется")

    # ── блок карточек профиля ────────────────────────────────────────────
    # Ссылку добавлял человек, картинку рисует прогон, и между этими моментами
    # страница показывала сломанное. Соседи признака «что показывать» перебраны
    # поимённо: ряд целиком · ряд наполовину · только верхний ряд · только
    # нижний · половина карточки · чужое имя в нарисованном.
    both = {f"{name}-{theme}": "<svg/>"
            for name in ("engineering", "stack", "activity")
            for theme in ("dark", "light")}

    def only(*names: str) -> dict[str, str]:
        return {k: v for k, v in both.items() if k.rsplit("-", 1)[0] in names}

    card_cases = [
        ("все три карточки", both, 3, True),
        ("верхний ряд без нижнего", only("engineering", "stack"), 2, False),
        ("только нижний ряд", only("activity"), 1, False),
        ("половина верхнего ряда", only("stack"), 1, False),
        ("половина карточки — не карточка", {"stack-dark": "<svg/>"}, 0, False),
        ("чужое имя в нарисованном не протекает",
         {**only("stack"), "tile-x-dark": "<svg/>", "tile-x-light": "<svg/>"}, 1, False),
    ]
    for name, drawn_now, pictures, separated in card_cases:
        made = render_profile_cards(drawn_now)
        got, gap = made.count("<picture>"), "<br><br>" in made
        if got != pictures or gap != separated:
            broken.append(f"карточки, {name}: ожидалось картинок {pictures} и "
                          f"разделитель {separated}, вышло {got} и {gap}")
        print(f"  {got} картинок — карточки: {name}")

    # НИ ОДНОЙ КАРТОЧКИ — исход, названный словами. Пустая строка между
    # маркерами неотличима от блока, который забыли собрать.
    nothing = render_profile_cards({})
    if "<picture>" in nothing or "not available" not in nothing:
        broken.append(f"карточки: пустой исход не назван — {nothing!r}")
    print("  назван    — карточки: ни одной не нарисовано")

    # Ширина и порядок живут ЗДЕСЬ, а не в разметке: до 8 сентября они жили в
    # двух местах и разъехались молча — карточка шириной 1000 точек оказалась
    # сжата до 48%, и шесть чисел встали тремя колонками вместо двух.
    if 'width="92%"' not in render_profile_cards(both):
        broken.append("карточки: ширина полотна активности потеряна")
    print("  да  — карточки: ширина и порядок берутся из одного места")

    # ── шов открывающего тега картинки ───────────────────────────────────
    # Вынесен по третьему случаю, а их было пять (правило 093). Соседи признака
    # «что открывает картинку» перебраны: экранирование подписи, пустая подпись
    # и подпись из одних пробелов, и — главное — что ВСЕ пятеро действительно
    # зовут шов, а не осталась шестая копия строки.
    opened = svg_open(10, 20, "подпись & <тест>")
    seam_checks = [
        ("размер попадает в тег", 'width="10" height="20" viewBox="0 0 10 20"' in opened),
        ("роль объявлена", 'role="img"' in opened),
        ("подпись экранируется", "&amp;" in opened and "&lt;тест&gt;" in opened),
    ]
    for name, ok in seam_checks:
        if not ok:
            broken.append(f"шов: {name} — нет")
        print(f"  {'да ' if ok else 'НЕТ'} — шов: {name}")

    for name, label in (("пустая подпись", ""), ("одни пробелы", "  \t ")):
        try:
            svg_open(10, 20, label)
        except ValueError:
            print(f"  отвергнут — шов: {name}")
        else:
            broken.append(f"шов: {name} принята — alt на странице стал бы пустым молча")

    # КОПИЙ БОЛЬШЕ НЕТ, и это проверяется по самому файлу: обобщение, из-под
    # которого уцелела шестая копия строки, не обобщение, а ещё одно место.
    #
    # СЧИТАЕТСЯ ТОЛЬКО РИСУЮЩАЯ ЧАСТЬ, до этой самой функции: первая редакция
    # проверки нашла ДВЕ копии и была права — второй оказался её собственный
    # образец. Тот же случай, что у гейта обращений к площадке, который поймал
    # сам себя: искать текстом можно только там, где текст и есть предмет.
    source = pathlib.Path(__file__).read_text(encoding="utf-8").split("def selftest")[0]
    copies = source.count('xmlns="http://www.w3.org/2000/svg"')
    if copies != 1:
        broken.append(f"шов: открывающий тег написан {copies} раз, а должен один")
    print(f"  {copies} раз     — шов: открывающий тег написан в одном месте")

    # ── фикстура: область не уезжает пустой ──────────────────────────────
    # Гейты витрины проверяют НАМЕРЕНИЕ, эта проверка — ФАКТ (правило 072).
    # Соседи предиката перебраны поимённо: обе стороны несимметричного условия,
    # пробельная пустота, число вместо блока, ноль как содержимое, отсутствие
    # маркера.
    filled = "<!--m:profile-cards-->\n<picture/>\n<!--/m:profile-cards-->"
    void = "<!--m:profile-cards-->\n<!--/m:profile-cards-->"
    spaces = "<!--m:profile-cards-->   \n\t\n<!--/m:profile-cards-->"
    number = "<!--m:rules-->194<!--/m:rules-->"
    zero = "<!--m:rules-->0<!--/m:rules-->"
    hollow_cases = [
        ("область пуста, сборка наполняет", void, {"profile-cards": "<picture/>"},
         ["profile-cards"]),
        ("область полна, сборка наполняет", filled, {"profile-cards": "<picture/>"}, []),
        ("область пуста, сборка молчит", void, {"profile-cards": ""}, []),
        ("пробелы и переносы — та же пустота", spaces, {"profile-cards": "<picture/>"},
         ["profile-cards"]),
        ("число вместо блока судится так же", number, {"rules": 200}, []),
        ("ноль — содержимое, а не пустота", zero, {"rules": 200}, []),
        ("маркера нет вовсе — не наш предмет", "текст без маркеров",
         {"profile-cards": "<picture/>"}, []),
    ]
    for name, text, made, expected in hollow_cases:
        got = hollow_regions(text, made)
        if got != expected:
            broken.append(f"пустая область, {name}: ожидалось {expected}, вышло {got}")
        print(f"  {'найдена  ' if got else 'пропущена'} — пустая область: {name}")

    # ── календарь активности ──────────────────────────────────────────────
    year = [day(i, i % 5) for i in range(364, -1, -1)]
    grid = render_activity(year, True)
    grid_checks = [
        ("квадрат на каждый день", grid.count("<rect") == len(year)),
        # Сумма вкладов за год стоит в СОСЕДНЕЙ карточке, и здесь её быть не
        # должно: одно число в двух местах расходится молча (правило 090).
        ("подпись не повторяет сумму соседа", str(sum(c for _, c in year)) not in grid),
        ("подпись несёт дневной максимум",
         f"daily · peak {max(c for _, c in year)}" in grid),
        ("у каждого дня своя подсказка", grid.count("<title>") == len(year)),
        ("пустой день не красится тоном", grid.count("#161B22") > 0),
    ]
    for name, ok in grid_checks:
        if not ok:
            broken.append(f"календарь: {name} — нет")
        print(f"  {'да ' if ok else 'НЕТ'} — календарь: {name}")

    # Линия недельного тренда — второй взгляд на те же данные, и она обязана
    # стоять ПОД своими столбцами: два вида одних данных, разъехавшиеся по
    # горизонтали, читаются как два разных периода.
    trend = render_activity(year, True)
    if "stroke-linejoin" not in trend or "weekly · peak" not in trend:
        broken.append("календарь: линия недельного тренда не нарисована")
    print("  да  — календарь: линия недельного тренда на месте")
    short = render_activity(year[:5], True)
    if "stroke-linejoin" in short:
        broken.append("календарь: линия рисуется там, где недели ещё нет")
    print("  да  — календарь: на неполной неделе линии нет")

    # ЗМЕЙКА НАРИСОВАНА С ПОЛЯМИ, И ТРЕНД РАВНЯЕТСЯ ПО СЕТКЕ, А НЕ ПО КАРТИНКЕ.
    # Подставная змейка повторяет геометрию живой: `viewBox` шире сетки слева на
    # 16 единиц, столбцы идут с шагом 16, клетка — 12. Первая точка обязана
    # встать в центр первого столбца (2 + 16 + 6 = 24), последняя — в центр
    # последнего (834 + 16 + 6 = 856). До этой правки они стояли на 5.5 и 874.5:
    # расхождение видел глаз, а набор — нет.
    fake = {"body": '<style>.c{width:12px;height:12px}</style>',
            "left": -16.0, "top": -32.0, "width": 880.0, "height": 192.0,
            "columns": [2.0 + 16 * i for i in range(53)], "cell": 12.0}
    crawled = render_activity(year, True, fake)
    drawn_path = re.search(r'<path d="M([\d.]+),[\d.]+((?: L[\d.]+,[\d.]+)+)"', crawled)
    ends = (drawn_path.group(1),
            drawn_path.group(2).rsplit(" L", 1)[1].split(",")[0]) if drawn_path else ()
    if ends != ("24.0", "856.0"):
        broken.append(f"календарь: тренд не встал под столбцами змейки — концы {ends}")
    print("  да  — календарь: тренд равняется по сетке змейки, а не по её полям")

    # Сетка читается у самой картинки, а поля не угадываются числом.
    # СОСЕДИ ОБОИХ ПРИЗНАКОВ ПЕРЕБРАНЫ ПОИМЁННО (правило 195). Признаков два:
    # чем берётся размер клетки из стиля и что считается клеткой в разметке.
    # Каждый решает больше одного случая, и чинились они по одному.
    style = ('<style>.c{shape-rendering:geometricPrecision;stroke-width:1px;'
             'width:12px;height:12px}</style>')
    grid_cases = [
        # `stroke-width:1px` стоит в том же правиле РАНЬШЕ `width:12px` — ровно
        # так его пишет живая змейка, и ровно на нём клетка вышла шириной в 1.
        ("stroke-width раньше width", style + '<rect class="c" x="2"/>', ([2.0], 12.0)),
        # Тот же класс свойств: их в правиле сегодня нет, но признак решает и их.
        ("min-width и max-width в том же правиле",
         '<style>.c{min-width:4px;max-width:9px;width:12px}</style>'
         '<rect class="c" x="2"/>', ([2.0], 12.0)),
        # Клетка помечена словом `c`, а не классом, начинающимся на «c».
        ("класс-слово c, а не префикс", style
         + '<rect class="c c1a" x="2"/><rect class="caption" x="99"/>', ([2.0], 12.0)),
        # Два соседа одного признака, и они несимметричны: `cell c` прежний
        # образец ловил ПО СЛУЧАЙНОСТИ — значение начинается на «c» от «cell», —
        # а `grid c` не поймал бы вовсе. Оба стоят в наборе, иначе случайное
        # совпадение сошло бы за работающий разбор.
        ("слово c не первым в списке", style
         + '<rect class="cell c" x="2"/>', ([2.0], 12.0)),
        ("слово c не первым и без общей буквы", style
         + '<rect class="grid c" x="2"/>', ([2.0], 12.0)),
        # Змея и её тень помечены своими словами и столбцами быть не должны.
        ("тело змеи и тень не клетки", style
         + '<rect class="u u0" x="7"/><rect class="s s0" x="9"/>'
         + '<rect class="c" x="2"/>', ([2.0], 12.0)),
        # `x` берётся атрибутом x, а не rx/cx: `\b` это уже держал, случай стоит
        # ради соседа, который НЕ ломался, — правило требует ответить и о нём.
        ("rx и cx за координату не принимаются", style
         + '<rect class="c" rx="9" cx="9" x="2"/>', ([2.0], 12.0)),
        # Третий исход: размера клетки в стиле нет вовсе.
        ("клетки есть, размера нет", '<rect class="c" x="2"/>', ([], 0.0)),
        # И обратный: правило есть, клеток нет.
        ("размер есть, клеток нет", style, ([], 0.0)),
    ]
    for name, body, expected in grid_cases:
        got = snake_grid(body)
        if got != expected:
            broken.append(f"змейка, {name}: ожидалось {expected}, вышло {got}")
        print(f"  {'да ' if got == expected else 'НЕТ'} — змейка: {name}")

    # Пустой календарь не роняет рисование: у нового профиля вкладов нет, и это
    # состояние, а не сбой.
    try:
        render_activity([], True)
    except Exception as e:
        broken.append(f"календарь: пустой год уронил рисование — {e!r}")
    print("  да  — календарь: пустой год рисуется")

    # ── витрина спрашивает источники, а не помнит их форму ────────────────
    # Ради этого набора и переписана вся ветка: чужая правка не должна ронять
    # пересчёт, а устаревший ответ витрины не должен показываться читателю.
    # Каждый случай ЗОВЁТ live_value на подставном дереве (правило 150).
    BADGE_BODY = {"schemaVersion": 1, "message": "96.8%"}
    live_cases = [
        ("значок под названным именем",
         {"endpoint": "coverage"}, {"coverage.json": BADGE_BODY}, {}, "96.8%", False),
        # Имя умерло, показатель жив: значение находится само, а мёртвое имя
        # называется находкой — иначе оно переживёт этот прогон и все следующие.
        ("названное имя умерло, значок нашёлся сам",
         {"endpoint": "coverage-old"}, {"coverage.json": BADGE_BODY}, {}, "96.8%", True),
        # Ответа про имя нет вовсе — сосед завёл значок сам, витрина его видит.
        ("значка витрина не объявляла, сосед его завёл",
         {"none": "тестов нет"}, {"coverage.json": BADGE_BODY}, {}, "96.8%", False),
        # Значка нет, но контракт фактов ровно для этого и писался.
        ("значка нет, число есть в фактах",
         {"none": "тестов нет"}, {}, {"coverage_percent": 91.2}, "91.2%", False),
        ("ни значка, ни фактов — источники молчат",
         {"none": "тестов нет"}, {}, {}, None, False),
        # Строку из фактов не переделывают: единицу дописывают только числу.
        ("строка из фактов остаётся строкой",
         {"none": "тестов нет"}, {}, {"coverage_percent": "n/a"}, "n/a", False),
    ]
    saved_api = globals()["_api"]
    try:
        for name, answer, files, facts_body, expected, must_find in live_cases:
            globals()["_api"] = _fake(files)
            said: list[str] = []
            got = live_value("o/r", "coverage", answer, facts_body, said)
            if got != expected:
                broken.append(f"живое значение, {name}: ожидалось {expected!r}, вышло {got!r}")
            if bool(said) is not must_find:
                broken.append(f"живое значение, {name}: находок {said}, ожидалось "
                              f"{'хотя бы одна' if must_find else 'ни одной'}")
            print(f"  {str(got):<8} — живое значение: {name}")
    finally:
        globals()["_api"] = saved_api

    # Обязательный список, объявленный в данных, тоже проверяется: показатель,
    # которого сборка не умеет, — это опечатка, тихо снимающая требование.
    try:
        check_badges({"required_badges": ["выдумка"], "projects": []})
        broken.append("показатели: выдуманный обязательный показатель пропущен")
        print("  пропущен  — показатели: выдуманный обязательный показатель")
    except SystemExit:
        print("  отвергнут — показатели: выдуманный обязательный показатель")

    # ── описание не влезает в баннер ───────────────────────────────────────
    try:
        render_featured([{"title": "X", "tagline": "д" * (TAGLINE_LIMIT + 1),
                          "stack": "s", "badges": [], "stats": lead}], dark=True)
        broken.append("баннер: слишком длинное описание пропущено")
        print("  пропущен  — баннер: описание длиннее потолка")
    except SystemExit:
        print("  отвергнут — баннер: описание длиннее потолка")

    # ── свежесть чужих фактов ─────────────────────────────────────────────
    # Обе стороны, и обе ошибки названы. Молчание здесь опаснее ложной находки:
    # витрина показывала бы вчерашние числа как сегодняшние, а снаружи это
    # неотличимо от «числа не менялись».
    now = dt.datetime(2026, 9, 2, tzinfo=dt.timezone.utc)
    stale_cases = [
        ("сегодняшние", "2026-09-02T10:00:00+00:00", False),
        ("вчерашние", "2026-09-01T10:00:00+00:00", False),
        ("ровно на пороге", "2026-08-19T10:00:00+00:00", False),
        ("старше порога", "2026-08-01T10:00:00+00:00", True),
        ("без часового пояса — читаются как UTC", "2026-09-02T10:00:00", False),
        ("отметки нет вовсе", "", True),
        ("отметка не разобрана", "позавчера", True),
    ]
    for name, stamp, must_find in stale_cases:
        found = bool(facts_staleness(stamp, now))
        if found != must_find:
            broken.append(f"свежесть фактов, {name}: ожидалось "
                          f"{'находка' if must_find else 'молчание'}, вышло {found}")
        print(f"  {'найдено  ' if found else 'молчание '} — свежесть фактов: {name}")

    # ── пробел у издателя ─────────────────────────────────────────────────
    # «Ключа нет — значит не измеряли» это контракт грейдера, и витрине от такой
    # честности не легче: показать число всё равно нечем. Проверяется, что
    # пробел НАЙДЕН и НАЗВАН — «что-то не так с фактами» отправило бы читающего
    # искать предмет самому.
    whole = {"python": {"experimental": ["3.14"]}}
    if facts_gaps(whole):
        broken.append("полные факты объявлены неполными")
    if facts_gaps({"python": {}}) != ["python.experimental"]:
        broken.append("пробел в фактах не назван поимённо")
    if facts_gaps({}) != ["python.experimental"]:
        broken.append("пустые факты не дают всех пробелов")
    # Спрашивается ровно то, что витрина показывает. Тесты и проверки на
    # изменение ушли отсюда вместе с плиткой флагмана: падать из-за чужого
    # пробела в числе, которого на странице нет, значит требовать невозможного.
    if facts_gaps({**whole, "tests": {}, "checks_per_pr": {}}):
        broken.append("спрашивается больше, чем показывается")
    print("  отвергнут — факты: пробел назван поимённо, ноль пробелом не считается")

    # Сверка ответа с каталогом идёт в обе стороны, и вторая половина
    # появилась после живого дефекта: 148 ответов при 147 правилах.
    export = {"rules": [{"id": "001"}, {"id": "002"}]}
    for name, rules, expected in (
        ("ответ без правила", {"001": {}, "002": {}, "143": {}}, ["143"]),
        ("все ответы при своих правилах", {"001": {}, "002": {}}, []),
        ("правило без ответа — не сюда", {"001": {}}, []),
        ("ответов нет вовсе", {}, []),
    ):
        got = orphaned(export, rules)
        if got != expected:
            broken.append(f"{name}: ожидалось {expected}, вышло {got}")
        print(f"  {str(got) if got else 'сходится':<12} — {name}")

    # ── отставание ответа от контракта каталога ────────────────────────────
    # Обе ошибки названы: пропустить подъём минора значит везти ответ, который
    # значит уже другое; объявить отставание там, где его нет, — остановить
    # изменение на ровном месте.
    drift_cases = [
        ("ответ на той же версии", "1.2", "1.2", False),
        ("издатель поднял минор", "1.2", "1.0", True),
        ("издатель поднял мажор", "2.0", "1.2", True),
        ("ответ впереди — не отставание", "1.2", "1.3", False),
        ("минор с хвостом версии", "1.2.1", "1.2", False),
        ("версия не разобрана — сказать, а не молчать", "неизвестно", "1.0", True),
        ("версии нет вовсе", "", "", True),
    ]
    for name, published, answered, expected in drift_cases:
        got = bool(contract_drift(published, answered))
        if got is not expected:
            broken.append(f"отставание от контракта, {name}: ожидалось "
                          f"{'находка' if expected else 'пропуск'}, вышло наоборот")
        print(f"  {'найдено ' if got else 'пропущен'} — отставание: {name}")

    # Отказ обязан назвать ОБЕ версии: без них чинящий идёт смотреть их сам.
    said = contract_drift("1.2", "1.0")
    if not ("1.2" in said and "1.0" in said and "bindings.json" in said):
        broken.append("отставание от контракта: отказ не называет обе версии и файл")

    # ── обязательная проверка кем-то создаётся ────────────────────────────
    # Сверка идёт ОТ НАСТРОЙКИ К ДЕРЕВУ: лишняя работа никого не блокирует, а
    # недостающая блокирует всё. Набор проверяет обе стороны именно поэтому.
    context_cases = [
        ("имена совпадают", ["PR check"], {"PR check", "automerge"}, False),
        ("работу переименовали", ["PR check"], {"check", "automerge"}, True),
        ("лишняя работа в дереве", ["PR check"], {"PR check", "прочее"}, False),
        ("обязательных нет вовсе", [], {"PR check"}, False),
        ("две обязательных, одной нет", ["PR check", "e2e"], {"PR check"}, True),
    ]
    for name, required, declared, expected in context_cases:
        got = bool(unmet_contexts(required, declared))
        if got is not expected:
            broken.append(f"обязательные проверки, {name}: ожидалось "
                          f"{'находка' if expected else 'пропуск'}, вышло наоборот")
        print(f"  {'найдено ' if got else 'пропущен'} — обязательные проверки: {name}")

    # Отказ обязан назвать ИМЯ несозданной проверки: «что-то не так с защитой»
    # отправляет читающего в настройки искать предмет самому.
    unmet = unmet_contexts(["PR check"], {"check"})
    if not (unmet and "'PR check'" in unmet[0]):
        broken.append("обязательные проверки: отказ не называет имя несозданной проверки")
    # ...и ВТОРУЮ сторону расхождения тоже (правило 178): без списка работ в
    # дереве читатель достраивает его по памяти, а расхождение здесь бывает в
    # одно слово — `check` против `PR check`.
    if not (unmet and "check" in unmet[0].split("Работы в дереве:")[-1]):
        broken.append("обязательные проверки: отказ не называет вторую сторону расхождения")
    empty = unmet_contexts(["PR check"], set())
    if not (empty and "—" in empty[0]):
        broken.append("обязательные проверки: пустая сторона не названа состоянием")

    # ── перепись имён репозиториев ────────────────────────────────────────
    # Переименование держит площадка, отключить редирект нельзя, и сигнала о
    # незавершённой миграции не будет вовсе. Проверяется решение, а не поход в
    # сеть: сеть приносит `full_name`, набор проверяет, что с ним делают.
    rename_cases = [
        ("имя живое", "ArtVsMark/Showcase", "ArtVsMark/Showcase", False),
        ("имя переименовано", "ArtVsMark/old-name", "ArtVsMark/New-Name", True),
        ("площадка промолчала — прав нет, а не миграция", "ArtVsMark/x", "", False),
    ]
    for name, mentioned, live, expected in rename_cases:
        got = bool(renaming_finding(mentioned, live, ["a.py", "b.md"]))
        if got is not expected:
            broken.append(f"перепись имён, {name}: ожидалось "
                          f"{'находка' if expected else 'пропуск'}, вышло наоборот")
        print(f"  {'найдено ' if got else 'пропущен'} — перепись имён: {name}")

    # Находка обязана назвать ОБА имени и число мест: чинящий идёт править их,
    # и «что-то переименовали» отправило бы его искать самому.
    said = renaming_finding("ArtVsMark/old", "ArtVsMark/new", ["a.py", "b.md", "c.yml"])
    if not ("ArtVsMark/old" in said and "ArtVsMark/new" in said and "3 местах" in said):
        broken.append("перепись имён: находка не называет оба имени и число мест")

    # ── третий исход называет предмет, а не только причину ─────────────────
    # Сети набор не требует: отказ подставной, а спрашивается механизм —
    # доедет ли адрес до печати (правило 150).
    probe_url = f"{API}/repos/o/r"
    refusal_cases = [
        ("площадка отказала в правах",
         urllib.error.HTTPError(probe_url, 403, "Forbidden", {}, None)),
        ("источник не ответил вовсе", urllib.error.URLError("timed out")),
        ("ответ не разобран", ValueError("Expecting value: line 1 column 1")),
        ("в ответе нет ожидаемого ключа", KeyError("tag_name")),
    ]
    for name, refusal in refusal_cases:
        try:
            with naming(probe_url):
                raise refusal
        except (urllib.error.URLError, OSError, ValueError, KeyError) as refused:
            named = getattr(refused, SOURCE_URL, None) == probe_url
            same = type(refused) is type(refusal)
        if not (named and same):
            broken.append(f"третий исход, {name}: "
                          + ("адрес не прикреплён" if not named else "класс отказа подменён"))
        print(f"  {'адрес назван' if named else 'БЕЗ АДРЕСА  '} — третий исход: {name}")

    # Штатное отсутствие значка ловится по классу — `except HTTPError`. Обёртка,
    # подменившая класс, роняет сборку на проекте, у которого значков нет по
    # замыслу: ровно это и случилось с первой редакцией.
    try:
        with naming(probe_url):
            raise urllib.error.HTTPError(probe_url, 404, "Not Found", {}, None)
    except urllib.error.HTTPError as absent:
        caught = absent.code == 404
    except OSError:
        caught = False
    if not caught:
        broken.append("третий исход: обёртка подменила класс — штатное «значка нет» "
                      "перестало ловиться по HTTPError")
    print(f"  {'ловится' if caught else 'ПОТЕРЯН'} — третий исход: 404 остаётся HTTPError")

    # Внутренний адрес точнее внешнего: обращение лежит внутри обёртки разбора,
    # и вложенность здесь обычное дело.
    try:
        with naming(f"{API}/внешний"):
            with naming(probe_url):
                raise urllib.error.HTTPError(probe_url, 404, "Not Found", {}, None)
    except OSError as refused:
        inner = getattr(refused, SOURCE_URL, None) == probe_url
    if not inner:
        broken.append("третий исход: вложенная обёртка подменила адрес внешним")
    print(f"  {'адрес внутренний' if inner else 'ПОДМЕНЁН'} — третий исход: вложенная обёртка")

    # Сквозная проверка: адрес доходит до ПЕЧАТИ, а не только до обработчика.
    # Проверяется guarded целиком — вместе с кодом возврата.
    printed = io.StringIO()
    real_main = globals()["main"]

    def refusing_main() -> int:
        refusal = urllib.error.HTTPError(probe_url, 403, "Forbidden", {}, None)
        with naming(probe_url):
            raise refusal

    globals()["main"] = refusing_main
    try:
        with contextlib.redirect_stderr(printed):
            code = guarded()
    finally:
        globals()["main"] = real_main
    said = printed.getvalue()
    for name, ok in (("код третьего исхода", code == 2),
                     ("адрес в напечатанном", probe_url in said),
                     ("причина в напечатанном", "403" in said)):
        if not ok:
            broken.append(f"третий исход печатью, {name}: нет")
        print(f"  {'да ' if ok else 'НЕТ'} — третий исход печатью: {name}")

    # Отказ без обёртки печатается как раньше: адреса нет, но исход тот же —
    # молчания на месте причины быть не должно.
    printed = io.StringIO()
    globals()["main"] = lambda: (_ for _ in ()).throw(ValueError("ответ не разобран"))
    try:
        with contextlib.redirect_stderr(printed):
            bare = guarded()
    finally:
        globals()["main"] = real_main
    bare_said = printed.getvalue()
    for name, ok in (("код третьего исхода", bare == 2),
                     ("причина названа", "ответ не разобран" in bare_said),
                     ("пустого адреса не печатается", " —  — " not in bare_said)):
        if not ok:
            broken.append(f"третий исход без адреса, {name}: нет")
        print(f"  {'да ' if ok else 'НЕТ'} — третий исход без адреса: {name}")

    # ── номер выгрузки, по которой отвечено (контракт 1.2, правило 157) ─
    # Обе стороны, и вторая здесь дороже: сборка, поднявшая номер сама, гасит
    # у издателя сигнал отставания — зелёным и молча (146).
    version_cases = [
        ("издатель ушёл вперёд, разбирать нечего", ("1.4", "1.5", False), "1.5"),
        ("издатель ушёл вперёд, но есть неразобранные", ("1.4", "1.5", True), ""),
        ("номера совпали — двигать нечего", ("1.5", "1.5", False), ""),
        ("издатель не назвал свой контракт — третий исход", ("1.4", "", False), ""),
        ("своего номера нет вовсе — ставится издательский", ("", "1.5", False), "1.5"),
    ]
    for name, args, expected in version_cases:
        got = answered_version(*args)
        if got != expected:
            broken.append(f"выгрузка ответа, {name}: ожидалось {expected!r}, вышло {got!r}")
        print(f"  {'поднят  ' if got else 'оставлен'} — выгрузка ответа: {name}")

    # ── следы каталога в наши документы (правило 185) ─────────────────
    # Оба исхода, а не один: ложный отказ здесь отправляет чинить живой след
    # в чужом репозитории — то есть просить владельца каталога о правке,
    # которой не нужно.
    trail_cases = [
        ("документ на месте", "CLAUDE.md", False),
        ("документа нет", "scripts/нет-такого.py", True),
        ("раздел на месте", "CLAUDE.md § Ветки", False),
        ("раздел переименован", "CLAUDE.md § Такого раздела нет", True),
    ]
    for name, doc, must_find in trail_cases:
        export = {"rules": [{"id": "185", "trails": [{"repo": SHOWCASE, "doc": doc}]}]}
        got = bool(our_trails(export))
        if got is not must_find:
            broken.append(f"следы, {name}: ожидалось "
                          f"{'находка' if must_find else 'пропуск'}, вышло {got}")
        print(f"  {'найден  ' if got else 'пропущен'} — след: {name}")
    # След в ЧУЖОЕ дерево — не наш предмет: там владелец другой, и правит его он.
    foreign = {"rules": [{"id": "185", "trails": [
        {"repo": "ArtVsMark/Stepik-Python-Grader", "doc": "нет-такого.md"}]}]}
    if our_trails(foreign):
        broken.append("следы: чужой документ принят за свой — владелец дерева другой")
    print(f"  {'НЕТ' if our_trails(foreign) else 'да '} — след: чужое дерево не наш предмет")

    # ТРИ БЛОКА КАДРА: «не рассказывает» и «намерил ноль» — разные состояния, и
    # набор проверяет именно их различие, а не наличие полей.
    made_cases = [
        ("раздела нет — строки не будет", {}, 0),
        ("тесты есть, проверок нет", {"tests": {"functions": 12, "modules": 3}}, 2),
        ("ноль тестов — это ответ, а не молчание",
         {"tests": {"functions": 0, "modules": 0}}, 2),
        ("чужой мусор вместо числа", {"tests": {"functions": "много"}}, 0),
    ]
    for name, facts, expected in made_cases:
        got = len(project_made(facts))
        if got != expected:
            broken.append(f"кадр, {name}: ожидалось {expected} чисел, вышло {got}")
        print(f"  {got} чисел  — кадр: {name}")

    rules_cases = [
        ("проект не подключён", None, False),
        ("подключён, но долей нет", {"answered": 5, "by_mechanism": {}}, False),
        ("доли есть", {"answered": 181, "trails": 7,
                       "by_mechanism": {"gate": 76, "document": 65}}, True),
    ]
    for name, answer, expected in rules_cases:
        got = project_rules(answer) is not None
        if got is not expected:
            broken.append(f"правила, {name}: ожидалось {'есть' if expected else 'нет'}")
        print(f"  {'есть' if got else 'нет '}      — правила: {name}")

    # Незнакомый механизм НЕ ТЕРЯЕТСЯ: словарь чужой и растёт, а доля, выпавшая
    # из полосы, читается как «такого у нас нет» (правило 022).
    grown = ordered_mechanisms({"gate": 3, "quantum": 1, "none": 2})
    if [name for name, _ in grown] != ["gate", "none", "quantum"]:
        broken.append(f"доли: незнакомый механизм потерялся или встал не туда: {grown}")
    print(f"  {[n for n, _ in grown]} — доли: незнакомый механизм показан")

    # Неподключённый проект НАЗЫВАЕТСЯ словами, а не пустой полосой: пустота
    # читалась бы как «правил ноль» (правило 046).
    silent = rules_strip({"rules": None}, 1000, True, "#8B949E")
    # Ищется во ВСЁМ блоке, а не в первой строке: над полосой стоит заголовок,
    # и привязка к позиции ломала бы набор при каждой правке раскладки.
    named = any("not connected" in line for line in silent)
    if not named:
        broken.append("правила: неподключённый проект показан пустотой, а не словами")
    # Заголовок блока обязателен и там: полоса без подписи не объясняет предмет.
    if not any("HOW ITS RULES ARE HELD" in line for line in silent):
        broken.append("правила: блок без заголовка — читателю не сказано, что за доли")
    print(f"  {'назван' if named else 'НЕТ'}   — правила: неподключённый назван")

    # ── таблица контракта сверяется с соседями ─────────────────────────────
    # Набор двусторонний (140). Ложный отказ здесь дороже пропуска: находки о
    # соседях красные на проверке изменения, и ругаться на верную строку значит
    # красить чужой правкой то, что в порядке.
    TABLE = ("| проект | файл | tests | checks | coverage | rules |\n"
             "|---|:---:|:---:|:---:|:---:|:---:|\n"
             "| [Сосед](https://github.com/Owner/Neighbour) | есть | ✅ | ✅ | — | — |\n")
    HAS = {"Owner/Neighbour": {"schema": "1.0", "tests": {"functions": 5},
                               "checks_per_pr": {"count": 3}}}
    contract_cases = [
        ("строка сходится с тем, что сосед публикует", TABLE, HAS, [], False),
        ("сосед начал публиковать раздел, а в таблице прочерк", TABLE,
         {"Owner/Neighbour": {**HAS["Owner/Neighbour"], "rules": {"gate": 1}}}, [], True),
        ("сосед перестал публиковать раздел, а в таблице галочка", TABLE,
         {"Owner/Neighbour": {"schema": "1.0", "checks_per_pr": {"count": 3}}}, [], True),
        ("файла не стало вовсе, а таблица говорит «есть»", TABLE,
         {"Owner/Neighbour": {}}, [], True),
        ("файл появился, а таблица говорит «нет»",
         TABLE.replace("| есть |", "| **нет** |"), HAS, [], True),
        # Молчание источника не судится: «не ответил» и «не публикует» — разное.
        ("сосед промолчал — строка не сверяется", TABLE, {"Owner/Neighbour": {}},
         ["Owner/Neighbour"], False),
        ("фактов этого соседа не читали вовсе", TABLE, {}, [], False),
        # Непонятая клетка не значит «нет»: гадать здесь дороже, чем спросить.
        ("клетка записана словом, которого разбор не знает",
         TABLE.replace("| ✅ | ✅ |", "| частично | ✅ |"), HAS, [], True),
        ("строки таблицы нет — сверять нечего", "текст без таблицы\n", HAS, [], False),
    ]
    for name, table, known, quiet, must_reject in contract_cases:
        found = contract_findings(table, known, quiet)
        if bool(found) is not must_reject:
            broken.append(f"контракт соседей, {name}: ожидалось "
                          f"{'отказ' if must_reject else 'пропуск'}, вышло {found}")
        print(f"  {'отвергнут' if found else 'пропущен '} — контракт соседей: {name}")

    # Отказ обязан назвать и проект, и колонку: находка без предмета отправляет
    # читающего искать его самому (158).
    named = contract_findings(TABLE, {"Owner/Neighbour": {"schema": "1.0"}}, [])
    if not (named and "Owner/Neighbour" in named[0] and "tests" in " ".join(named)):
        broken.append(f"контракт соседей: отказ не называет проект или колонку: {named}")

    # ── читаемость текста на картинках ─────────────────────────────────────
    # Набор двусторонний (правило 140), и живая половина здесь дороже: гейт,
    # ругающийся на исправную палитру, останавливает СБОРКУ, а не правку, —
    # витрина при этом стоит с прежними числами и не говорит почему.
    #
    # Проверяются и рукодельные картинки с диска: они на странице стоят рядом с
    # собранными, а меняет их человек — то есть ровно тот, кто ошибётся.
    strip = {"mechanisms": {"gate": 5, "pipeline": 3, "code": 2, "document": 4,
                            "none": 1, "квантовый": 2}, "answered": 20, "trails": 3}
    drawings = dict(handmade())
    for theme, dark in (("dark", True), ("light", False)):
        drawings[f"featured-{theme}"] = render_featured(
            [{**accents[0], "rules": strip}] + accents[1:], dark)
        drawings[f"engineering-{theme}"] = render_engineering(eng_stats, dark)
        drawings[f"stack-{theme}"] = render_stack(reach_sample, roles_sample, 5, dark)
        drawings[f"activity-{theme}"] = render_activity(year, dark)
        drawings[f"tile-x-{theme}"] = render_tile(
            {"repo": "ArtVsMark/X", "title": "X", "tagline": "плитка", "stack": "CLI"}, dark)

    for name, body in sorted(drawings.items()):
        found = unreadable(name, body)
        if found:
            broken += [f"читаемость: {line}" for line in found]
        print(f"  {'НЕ ПРОШЛА' if found else 'читаема  '} — картинка {name}")

    dark_card, light_card = drawings["featured-dark"], drawings["featured-light"]
    faked = [
        # Подпись потускнела на один тон палитры площадки — это и есть тот
        # случай, ради которого механизм заведён: глазами он не отличим.
        ("тёмная подпись потускнела", dark_card.replace("#7D8590", "#6E7681"), "#6E7681"),
        ("светлая подпись потускнела", light_card.replace("#636C76", "#8C959F"), "#8C959F"),
        # Новый цвет обязан получить роль при появлении: непонятая заливка —
        # это подложка, читаемость на которой не проверяет никто.
        ("заливка без роли", dark_card.replace('fill="#0D1117"', 'fill="#123456"', 1), "#123456"),
        # Цвет из градиента отсюда не виден, и такой текст отвергается, а не
        # пропускается: невидимая проверка хуже отсутствующей.
        ("цвет текста градиентом",
         dark_card.replace('fill="#F0F6FC"', 'fill="url(#e)"', 1), "url(#e)"),
    ]
    for name, body, subject in faked:
        found = unreadable("featured-dark" if "светлая" not in name else "featured-light", body)
        if not any(subject in line for line in found):
            broken.append(f"читаемость: подделка «{name}» прошла или не названа: {found}")
        print(f"  {'отвергнута' if found else 'ПРОШЛА   '} — подделка: {name}")

    # Тему картинка называет именем файла, и другого источника у неё нет:
    # безымянная тема — это подложка наугад, а не «наверное, тёмная».
    if not unreadable("featured", dark_card):
        broken.append("читаемость: картинка без темы в имени прошла молча")

    # Четыре числа, которыми критерий держался до 8 сентября, обязаны сходиться
    # с арифметикой — иначе документ и код разошлись бы обратно (правило 175).
    measured = [contrast("#7D8590", "#0D1117"), contrast("#636C76", "#FFFFFF"),
                contrast("#F0F6FC", "#0D1117"), contrast("#1F2328", "#FFFFFF")]
    if [round(v, 1) for v in measured] != [5.1, 5.3, 17.4, 15.8]:
        broken.append(f"читаемость: числа .rules/roles.md разошлись с расчётом: {measured}")
    print(f"  {[round(v, 2) for v in measured]} — числа свода сходятся с расчётом")

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: сторож, ранжирование и баннер держат объявленное")
    return 0


def main() -> int:
    """``--check`` прогоняет всё то же самое, но ничего не пишет.

    Витрине нечему зеленеть на PR: тестов у неё нет, а проверять есть что —
    жив ли каждый источник, на месте ли маркеры, проставился ли alt у всех
    картинок, не перерос ли «Current focus» свой потолок. Это и есть проверка,
    которую ждёт автомерж: без неё «слить по зелёному» означает «слить сразу».
    """
    # Самопроверка ни в какую сеть не ходит и клона не требует: она про сторож,
    # а не про источники. Поэтому стоит до всего остального.
    if "--selftest" in sys.argv[1:]:
        return selftest()

    check = "--check" in sys.argv

    # КЛОНА ГРЕЙДЕРА ЗДЕСЬ БОЛЬШЕ НЕТ. Путь в аргументах принимается и молча
    # игнорируется: прогоны соседних репозиториев и чужие вызовы передают его по
    # привычке, и падать на лишнем слове значило бы ломать то, что работает.
    # Отказ ради чистоты дороже совместимости (правило 051).
    facts = grader_facts()

    stale = facts_staleness(facts.get("generated_at", ""), dt.datetime.now(dt.timezone.utc))
    if stale:
        # Находка, а не отказ: числа в файле есть и они настоящие — вопрос лишь
        # в том, когда их считали. Ронять суточную сборку из-за молчания соседа
        # значило бы заморозить и остальную страницу.
        print(checks.annotate("warning", stale), file=sys.stderr)

    gaps = facts_gaps(facts)
    if gaps:
        print(checks.annotate("error", f"грейдер не измерил: {', '.join(gaps)} — "
                              f"витрине эти числа брать неоткуда, и прошлые не подставляются"),
              file=sys.stderr)
        return 1

    required, systems, versions = protection_facts()
    experimental = " · ".join(facts["python"]["experimental"])
    releases = release_count()
    signed, signed_total = signed_commits()
    export = rules_export()
    rules = int(export["count"])
    bindings = sync_bindings(export, write=not check)
    # Ответ без правила — находка, а не фон. Красным она становится ровно на
    # изменении: там на неё смотрит человек, и починка стоит одну строку.
    # Суточная сборка при этом продолжает работать: витрина не должна перестать
    # обновляться из-за того, что в чужом каталоге что-то удалили.
    # Подъём минора у издателя: на изменении — находка, в суточной сборке —
    # предупреждение. Числа не должны замирать из-за чужой правки контракта, но
    # и уехать в общую ветку с ответом, который значит уже другое, нельзя.
    #
    # СРАВНИВАЮТСЯ ВЕРСИИ ОДНОГО ПРЕДМЕТА. Здесь стояла `schema` ВЫГРУЗКИ против
    # `schema` ОТВЕТА — два разных формата с одним именем ключа, — и молчало это
    # ровно потому, что в ответе витрины лежал чужой номер 1.2 вместо своего 1.1
    # (правило 164). Теперь обе стороны про формат ответа: наша — из своего
    # файла, издательская — из его заготовки.
    answer = json.loads(BINDINGS.read_text(encoding="utf-8"))
    drift = contract_drift(answer_contract_version(), str(answer.get("schema", "")))
    if drift and check:
        print(checks.annotate("error", f"ответ витрины отстал от контракта: {drift}"),
              file=sys.stderr)
        print("  Перечитываются ЗАПИСИ, а не только их формат: вместе с минором меняется"
              "\n  значение полей, и валидность это переживает. Поднимите schema после"
              "\n  перечитывания, а не вместо него.", file=sys.stderr)
        return 1
    if drift:
        print(checks.annotate("warning", f"ответ витрины отстал от контракта: {drift}"))

    # Обязательная проверка обязана кем-то создаваться. Отказ площадки здесь —
    # третий исход, а не находка: настройка защиты живёт вне репозитория, и её
    # недоступность говорит о доступе, а не о витрине (039).
    try:
        unmet = unmet_contexts(protection_names(), job_names(ROOT))
    except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
        print(checks.annotate("warning", f"защита ветки витрины не прочитана: {error}. "
                              f"Совпадение имён проверить нечем"), file=sys.stderr)
        unmet = []
    # Перепись имён соседей — против миграции, о незавершённости которой никто
    # не сообщит: редирект площадки отключить нельзя (172). Находка, а не отказ:
    # старый адрес работает, страница не ломается, чинится это спокойно.
    for line in renamed_repos(mentioned_repos(ROOT)):
        print(checks.annotate("warning", line), file=sys.stderr)

    # Следы каталога, ведущие в наши документы: адрес правит владелец дерева,
    # и узнать о разрыве может только он (185). Находка, а не отказ — починка
    # живёт в чужом репозитории, и краснеть здесь значило бы вставать за неё.
    for line in our_trails(export):
        print(checks.annotate("warning", line), file=sys.stderr)

    if unmet:
        for line in unmet:
            print(checks.annotate("error", line), file=sys.stderr)
        print("  Имя работы и обязательный контекст — два имени в разных системах "
              "координат.\n  Совпадали они до сих пор ничем не подкреплённо: 22 августа "
              "расхождение\n  сделало несливаемым каждый PR, включая тот, которым чинили.",
              file=sys.stderr)
        return 1

    left = orphaned(export, answer["rules"])
    if check and left:
        print(bindings)
        print(checks.annotate("error", "ответ витрины отвечает по правилам, которых "
                              f"в каталоге больше нет: {', '.join(left)}"), file=sys.stderr)
        print("  Правило могли удалить как переоткрывающее уже сказанное — так ушло 143."
              "\n  Решения у этого нет механического: ответ мог быть верным сам по себе, а мог"
              "\n  держаться удалённым правилом. Уберите запись или перенесите её смысл в"
              "\n  ответ по тому правилу, которое её заменило.", file=sys.stderr)
        return 1

    config = json.loads(PROJECTS.read_text(encoding="utf-8"))
    # Раньше сети: ответ по обязательным показателям не зависит от источников,
    # и узнать о его нехватке дешевле до двадцати запросов, а не после.
    check_badges(config)
    values = {
        "projects": render_projects(config),
        "required": required,
        "os": systems,
        "py": versions,
        "exp": experimental,
        "releases": releases,
        "rules": rules,
        "signed": signed,
        "signed-total": signed_total,
    }
    print(bindings)
    print(" · ".join(f"{key}: {value}" for key, value in values.items() if key != "projects"))

    # Сторож стоит ДО форматирования плитки, и это не порядок строк ради
    # красоты. Пока «4000+» собиралось раньше проверки, ноль тестов давал
    # «0000+» — строку, в которой сторож ноля не находит: он сравнивал с "0".
    # Метрика, попадающая в сторож уже строкой для показа, не проверена.
    empty = unanswered(values)
    if empty:
        print(checks.annotate("error", f"метрика не собралась ({', '.join(empty)}) "
                              "— ничего не переписываю"), file=sys.stderr)
        return 1

    # Числа с плитки в тексте README не повторяются: одно число — одно место.
    # Текстовому читателю они достаются через alt картинки, а его тоже
    # проставляет этот скрипт — см. sync_alt.
    #

    # Акценты баннера. Через сторож пустых метрик эти числа НЕ проходят, и это
    # решение, а не пропуск: ноль звёзд и ноль релизов — честное состояние
    # молодого проекта, а не молчание источника. Молчание здесь ловится иначе —
    # отказом самого запроса и сторожем курсорной разбивки в _count.
    stats = {project["repo"]: project_stats(project["repo"]) for project in config["projects"]}
    titles = {project["repo"]: project["title"] for project in config["projects"]}
    by_repo = {project["repo"]: project for project in config["projects"]}
    accents = []
    # Находки о соседях копятся, а не роняют пересчёт. Ронять его чужой правкой
    # витрина перестала после трёх суток простоя 5–7 сентября (039).
    neighbour_findings: list[str] = []
    # Два чужих ответа на кадр: проект о себе (facts.json) и каталог о нём
    # (where.json). Оба необязательны и оба ОТЛИЧИМЫ от нуля: «не рассказывает»
    # и «измерено ноль» — разные состояния, и кадр показывает их по-разному.
    where = catalogue_where()
    # Прочитанные факты держатся до конца сборки: по ним сверяется таблица
    # «кто это уже делает» в контракте. Второго похода в сеть для этого не
    # делается — читается то же, что уже прочитано для карточек.
    read: dict[str, dict] = {}
    silent: list[str] = []
    for repo in rank_featured(stats)[:FEATURED_ACCENTS]:
        project = by_repo[repo]
        facts = project_facts(repo, silent)
        read[repo] = facts
        accents.append({
            "title": project["title"],
            "tagline": project["tagline"],
            "stack": project["stack"],
            "badges": project_badges(repo, project["badges"], neighbour_findings),
            "stats": stats[repo],
            "made": project_made(facts),
            "rules": project_rules(where.get(repo)),
        })
    # Утверждение о соседе сверяется с соседом, а не перечитывается глазами.
    neighbour_findings += contract_findings(
        (ROOT / ".rules/facts-contract.md").read_text(encoding="utf-8"), read, silent)
    if silent:
        print(checks.annotate("warning", "факты не прочитаны у " + ", ".join(silent)
                              + " — строки контракта по ним не сверялись"))

    print("акценты: " + " · ".join(
        f"{a['title']} ({', '.join(str(a['stats'][f]) for f in FEATURED_FIELDS)}"
        + (f"; {', '.join(f'{n} {v}' for n, v, _ in a['badges'])}" if a["badges"] else "")
        + ")"
        for a in accents))

    # Чьи числа на плитке: закреплённый проект, а при его отсутствии — первый
    # по свежести. Берётся из данных, а не вписывается: витрина не называет
    # проект по памяти автора.
    flagship = next(
        (p["title"] for p in config["projects"] if p.get("pin")),
        config["projects"][0]["title"] if config["projects"] else "",
    )

    # РИСУЕТСЯ ВСЕГДА, ПИШЕТСЯ НА ДИСК — ТОЛЬКО В БОЕВОМ ПРОГОНЕ. Раньше при
    # проверке плитки не рисовались вовсе, и это сходило с рук ровно потому, что
    # производные лежали в дереве: подпись и отпечаток читались из файла. С
    # переездом в ветку `assets` (правило 160) читать стало нечего, и разница
    # между «проверить» и «собрать» перестала быть в том, ЧТО считается, —
    # осталась только в том, записывается ли результат.
    fresh: dict[str, str] = {}
    drawn: dict[str, str] = {}

    # ПРОФИЛЬНЫЕ ЧИСЛА — ОТДЕЛЬНЫЙ ИСТОЧНИК, И ЕГО ОТКАЗ НЕ РОНЯЕТ ВИТРИНУ
    # (задача #139, правило 039). Они приходят из `/users/*` и GraphQL, а те
    # закрыты окну прокси сессии: проверить запрос отсюда нельзя, его проверяет
    # первый живой прогон. Поэтому отказ здесь — третий исход: карточка не
    # рисуется, прежняя остаётся лежать в ветке `assets`, остальные тридцать
    # чисел досчитываются.
    #
    # Пустыми прежние картинки не перезаписываются — этого прямо требует
    # задача, и механизм тут простой: не нарисовали, значит не положили в
    # `drawn`, а публикуется только то, что в нём.
    try:
        profile = profile_stats()
    except (urllib.error.URLError, OSError, ValueError, KeyError, SystemExit) as refusal:
        profile = {}
        print(checks.annotate("warning", f"профильные числа не собраны ({refusal}) — "
                              f"карточка не перерисовывается, прежняя остаётся"))

    # След технологий читается по РЕПОЗИТОРНЫМ эндпоинтам, и потому доступен
    # даже там, где профильные закрыты: у него свой отказ и своя судьба.
    project_repos = [project["repo"] for project in config["projects"]] + [SHOWCASE]
    try:
        reach = language_reach(project_repos)
        roles = [role.strip() for project in config["projects"]
                 for role in project["stack"].split("·")]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as refusal:
        reach, roles = [], []
        print(checks.annotate("warning", f"след технологий не собран ({refusal}) — "
                              f"карточка не перерисовывается, прежняя остаётся"))

    for theme, dark in (("dark", True), ("light", False)):
        if profile:
            card = render_engineering(profile, dark)
            drawn[f"engineering-{theme}"] = card
            fresh[f"engineering-{theme}"] = aria_of(card)
            # МОЛЧАНИЕ ЗМЕЙКИ ГОВОРИТСЯ ВСЛУХ (правило 039). Полотно в этом
            # случае рисует собственный календарь, и картинка выходит
            # исправной — то есть пропажа не видна ничем. Сторож свежести
            # спрашивает про её прогон отдельно, но он ходит по расписанию, а
            # эта строка стоит в том самом прогоне, где змейку не прочитали.
            snake = snake_layer(theme)
            if snake is None:
                print(checks.annotate("warning", f"змейка ветки {SNAKE_BRANCH} не "
                                      f"прочитана ({theme}) — полотно рисует свой "
                                      f"календарь без неё"))
            grid = render_activity(profile.get("days", []), dark, snake)
            drawn[f"activity-{theme}"] = grid
            fresh[f"activity-{theme}"] = aria_of(grid)
        if reach:
            stack = render_stack(reach, roles, len(project_repos), dark)
            drawn[f"stack-{theme}"] = stack
            fresh[f"stack-{theme}"] = aria_of(stack)
        drawn[f"featured-{theme}"] = render_featured(accents, dark)
        fresh[f"featured-{theme}"] = accent_label(accents)
        for project in config["projects"]:
            tile = render_tile(project, dark)
            name = f"tile-{slug(project['repo'])}-{theme}"
            drawn[name] = tile
            # Подпись плитки берётся из только что нарисованного текста, а не из
            # файла: файла может не быть вовсе — в дереве его больше не хранят.
            fresh[name] = aria_of(tile)
        if not check:
            for name, body in drawn.items():
                (ROOT / f"assets/{name}.svg").write_text(body, encoding="utf-8")
    # ЧИТАЕМОСТЬ СУДИТСЯ ПО КАРТИНКЕ, А НЕ ПО ПАМЯТИ. Проверяются и только что
    # нарисованные, и рукодельные: на странице они стоят рядом, и читателю
    # безразлично, кто их автор. Отказ здесь красный, а не третий исход —
    # источник ни при чём, палитра наша.
    faults = [line for name, body in {**handmade(), **drawn}.items()
              for line in unreadable(name, body)]
    if faults:
        raise SystemExit(
            "текст витрины не проходит порог читаемости:\n"
            + "\n".join(f"  • {line}" for line in faults)
            + "\n\n  Порог — AA по WCAG 2.1 (4.5:1). Критерий объявлен в .rules/roles.md,"
            "\n  и до 8 сентября он держался четырьмя числами, вписанными руками."
        )

    # БЛОК КАРТОЧЕК СОБИРАЕТСЯ ПОСЛЕ РИСОВАНИЯ, и это не порядок строк ради
    # красоты: он перечисляет то, что сборка НАРИСОВАЛА, а до цикла этого ещё
    # никто не знает. Сторож пустых метрик его намеренно не судит — он заведён
    # против числа, у которого промолчал источник, а у блока свой исход:
    # карточек нет вовсе, и он говорит это словами, а не пустотой.
    values["profile-cards"] = render_profile_cards(drawn)

    patch_readme(values, fresh, drawn, write=not check)

    # НАХОДКИ О СОСЕДЯХ РАЗВЕДЕНЫ ПО МОМЕНТУ, А НЕ ПО ГРОМКОСТИ. На проверке
    # изменения они красные: их чинит окно, здесь и сейчас, правкой
    # projects.json. В суточной сборке они печатаются командой площадки и
    # пересчёт продолжается: чужая правка не вправе останавливать наши числа,
    # а молчать о ней нельзя — предупреждение видно в прогоне и в его сводке.
    if neighbour_findings:
        for line in neighbour_findings:
            print(checks.annotate("error" if check else "warning", line),
                  file=sys.stderr if check else sys.stdout)
        if check:
            print(f"\nответы витрины о соседях разошлись с источниками: "
                  f"{len(neighbour_findings)}. Витрина показывает источник, а не "
                  f"записанное; поправьте projects.json.", file=sys.stderr)
            return 1

    print("проверка прошла: источники живы, маркеры на месте" if check
          else "картинки витрины и README обновлены")
    return 0


def guarded() -> int:
    """Вход с разведёнными исходами: отказ источника — не наша поломка.

    Сборка ходит в чужие сервисы двадцать с лишним раз. До 28 августа отказ
    любого из них поднимался трассировкой и выходил кодом 1 — тем же, каким
    сборка сообщает о СВОЕЙ находке. Ровно это и случилось, когда каталог унёс
    значки на отдельную ветку: `HTTP 404` прочиталось как «метрика не
    собралась», хотя не собрался ответ соседа.

    Предмет отказа печатается вместе с причиной: «двадцать с лишним раз»
    означает, что без адреса третий исход называет сторону, но не место, — и
    первое, что делает читающий, это заново ищет, кто именно отказал
    (``naming``).
    """
    try:
        return main()
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        where = getattr(e, SOURCE_URL, None)
        print("сборка не отработала: источник не ответил или ответ не разобран — "
              f"{f'{where} — ' if where else ''}{e}", file=sys.stderr)
        print("  Это третий исход, а не разновидность второго: чужой отказ чинится\n"
              "  на той стороне, а наша находка — здесь (правило 039).", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(guarded())
