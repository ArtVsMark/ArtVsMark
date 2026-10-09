#!/usr/bin/env python3
"""Факты каждого проекта сверяются с одной схемой — а не витрина подстраивается под каждый.

РЕШЕНИЕ ВЛАДЕЛЬЦА 1 ОКТЯБРЯ: у каждого проекта один файл
``.github/badges/facts.json`` в ветке ``badges``, и в нём всё, что витрина о
проекте показывает. Требования одни на всех и записаны в одном месте —
``.rules/facts.schema.json``. Прежде витрина читала у пяти проектов четыре вида
источников и помнила в ``projects.json``, у кого какой; терпимость к чужой форме
стала узаконенным разнобоем: у глоссария нет даже ``repo`` из обязательного
минимума, а версии Python лежат под своим именем.

СХЕМА — ИСТОЧНИК, ПРОВЕРКА ЕЁ ЧИТАЕТ. Здесь нет второй записи требований:
разбирается подмножество JSON Schema, которым схема написана. Ключевое слово,
которого разбор не знает, — отказ, а не пропуск: иначе требование, дописанное в
схему, молча не проверялось бы (правило 045).

ИЗДАТЕЛЬ ПРОВЕРЯЕТ СЕБЯ ТОЙ ЖЕ СХЕМОЙ — у себя, до публикации. Эта проверка —
взгляд потребителя: кто из соседей сейчас договору не отвечает и чем именно.

ФАЙЛ САМОСТОЯТЕЛЕН — У ИЗДАТЕЛЯ ОН ЛЕЖИТ ОДИН (#309). Выпуск договора
``facts-vX.Y.Z`` прикладывает этот файл рядом со схемой, номером и образцом, и
издатель гоняет у себя ровно то, чем витрина судит его. Поэтому здесь только
стандартная библиотека: ``checks`` витрины — необязательный импорт, нужный лишь
режиму соседей. Без него схема и номер ищутся рядом со скриптом. Держит набор
пробой переноса: файл, скопированный в пустой каталог, обязан отработать.

МАНИФЕСТ СЕМЬИ (С 1.6, #316). Рядом с фактами издатель кладёт
``contracts.json`` — форму держит каталог (контракт ``family``), здесь читается
только её мажор. Нет манифеста или мажор не тот — совет ``⚠``; в 2.0 — отказ.

Запуск::

    python scripts/check_facts.py              # все проекты из projects.json
    python scripts/check_facts.py --file f.json --repo владелец/имя
    python scripts/check_facts.py --contract   # номер договора против заголовков
    python scripts/check_facts.py --selftest

У издателя, из выпуска — файлы лежат рядом::

    python check_facts.py --file .github/badges/facts.json --repo владелец/имя

Исходы: 0 — все файлы отвечают договору; 1 — есть расхождения, перечислены по
проектам; 2 — проверка не отработала: схема не прочитана, площадка не ответила
о чьём-то файле (правило 039: «не ответил» не записывается в «не отвечает»).
"""

import argparse
import base64
import json
import os
import pathlib
import re
import sys
import urllib.error

try:
    import checks
except ImportError:          # у издателя файл лежит один — выпуском договора
    checks = None

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent


def beside(path: pathlib.Path) -> pathlib.Path:
    """Путь в дереве витрины, а без него — тот же файл рядом со скриптом.

    В выпуске договора файлы лежат плоско: ``check_facts.py``,
    ``facts.schema.json``, ``facts.version`` и образец — в одном каталоге.
    """
    return path if path.exists() else HERE / path.name


SCHEMA_PATH = beside(ROOT / ".rules" / "facts.schema.json")
#: Номер договора — здесь и только здесь (035). Заголовки схемы и прозы
#: сверяет с ним ``contract_drift``; выпуск договора ставит тег ``facts-v<номер>``.
VERSION_PATH = beside(ROOT / ".rules" / "facts.version")
#: Образец файла по текущему договору — прикладывается к выпуску; набор держит,
#: что он отвечает схеме без единого совета.
EXAMPLE_PATH = beside(ROOT / ".rules" / "facts.example.json")
CONTRACT_PATH = beside(ROOT / ".rules" / "facts-contract.md")
PROJECTS_PATH = ROOT / "projects.json"

#: Адрес файла у издателя. Один на всех — в этом и решение.
FACTS_PATH = ".github/badges/facts.json"
FACTS_REF = "badges"
#: Манифест семьи — рядом с фактами, на той же ветке (договор 1.6, #316).
MANIFEST_PATH = ".github/badges/contracts.json"
#: Мажор формы ``family``, на который договор соглашается. Номер, а не форма:
#: форму целиком судит каталог (``family.изъян_формы``), копии здесь нет (090).
FAMILY_MAJOR = "1"

#: Ключевые слова, которые разбор понимает. Служебные — только подписи.
KEYWORDS = {"type", "required", "properties", "additionalProperties", "items",
            "pattern", "minLength", "minimum", "maximum", "minItems", "enum",
            "anyOf", "allOf", "propertyNames"}
ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description"}

TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


def annotate(level: str, text: str) -> str:
    """Строка находки командой площадки в прогоне — через ``checks`` витрины.

    КОПИЯ НАМЕРЕННАЯ И В ТРИ СТРОКИ (071): у издателя ``checks`` нет, а
    тащить его в выпуск значит выпускать всё хозяйство витрины ради одной
    приставки. Признак прогона тот же — ``GITHUB_ACTIONS`` площадки.
    """
    if checks is not None:
        return checks.annotate(level, text)
    return f"::{level}::{text}" if os.environ.get("GITHUB_ACTIONS") == "true" else text


def validate(value: object, schema: dict, path: str = "") -> list[str]:
    """Расхождения ``value`` со ``schema`` — по строке на каждое, с путём к месту.

    Незнакомое ключевое слово — ``ValueError``: схема просит того, чего проверка
    не умеет, и молча пропустить его значило бы объявить требование и не держать.
    """
    unknown = set(schema) - KEYWORDS - ANNOTATIONS
    if unknown:
        raise ValueError(f"схема у {path or 'корня'} просит незнакомого: "
                         f"{', '.join(sorted(unknown))}")
    where = path or "файл"
    kind = schema.get("type")
    if kind is not None and not TYPES[kind](value):
        return [f"{where}: ожидался {kind}, лежит {type(value).__name__}"]

    found: list[str] = []
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                found.append(f"{where}: нет обязательного поля «{name}»")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties")
        names = schema.get("propertyNames")
        for name, item in value.items():
            sub = f"{path}.{name}" if path else name
            if names is not None:
                found += [f"{sub}: имя не из допустимых — {msg.split(': ', 1)[1]}"
                          for msg in validate(name, names, sub)]
            if name in props:
                found += validate(item, props[name], sub)
            elif isinstance(extra, dict):
                found += validate(item, extra, sub)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            found.append(f"{where}: элементов {len(value)}, нужно не меньше "
                         f"{schema['minItems']}")
        if "items" in schema:
            for index, item in enumerate(value):
                found += validate(item, schema["items"], f"{where}[{index}]")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            found.append(f"{where}: пустая строка")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            found.append(f"{where}: «{value}» не той формы")
    if TYPES["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            found.append(f"{where}: {value} меньше {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            found.append(f"{where}: {value} больше {schema['maximum']}")
    if "enum" in schema and value not in schema["enum"]:
        found.append(f"{where}: «{value}» — допустимы {', '.join(map(str, schema['enum']))}")
    for part in schema.get("allOf", []):
        found += validate(value, part, path)
    if "anyOf" in schema and not any(not validate(value, option, path)
                                     for option in schema["anyOf"]):
        found.append(f"{where}: нет ни поля, ни причины — "
                     f"{schema.get('description', 'ни одна из форм не подошла')}")
    return found


def check(facts: object, repo: str, schema: dict) -> list[str]:
    """Расхождения файла с договором. Сверх схемы — две сверки, которых ей не выразить.

    * файл о том, у кого лежит: схема не знает, откуда файл прочитан;
    * версия — сборка выпуска: ``version`` начинается с ``release`` и точки.
      Выпуск — серия ``X.Y``, версия — ``X.Y.Z`` внутри неё (договор 1.3).
      Сверка двух полей между собой схеме подмножества не по силам, а
      расходятся они правдоподобно: забытый подъём выпуска или версия,
      убежавшая в серию, которой нет, выглядят как обычные числа.
    """
    found = validate(facts, schema)
    if not isinstance(facts, dict):
        return found
    if isinstance(facts.get("repo"), str) and facts["repo"] != repo:
        found.append(f"repo: «{facts['repo']}», а файл лежит у {repo}")
    # Сверяются только поля правильной формы: выпуск «v1.3.0» уже назван
    # схемой, и вторая находка о той же причине была бы шумом, а не сведением.
    version, release = facts.get("version"), facts.get("release")
    series = schema.get("properties", {}).get("release", {}).get("pattern", "")
    if isinstance(version, str) and isinstance(release, str) \
            and re.search(series, release) and not version.startswith(f"{release}."):
        found.append(f"version: «{version}» — не сборка выпуска «{release}»: "
                     f"версия обязана начинаться с «{release}.»")
    return found


#: Поля корня, которые договор знает, но не держит: подпись-комментарий ``_``.
COMMENT_KEYS = {"_"}


def advise(facts: object, schema: dict, current: str) -> list[str]:
    """Предупреждения договора 1.4 — то, что 2.0 запретит. Код возврата не меняют.

    * поле корня вне договора: своё проекта живёт в ``exchange.<тема>``, корень —
      только договор. В 1.4 это совет, в 2.0 — отказ (решение владельца, #309);
    * ``rules`` отдельно и с причиной: доли механизмов считает каталог одной
      формулой на всех, второй источник того же числа расходится (090) —
      замер 9 октября: у пяти издателей пять форм;
    * версия формата ниже договора: файл верен своему минору, но отстал, и без
      сигнала отставание незаметно — схема пропускает любой ``1.x``.
    """
    if not isinstance(facts, dict):
        return []
    said: list[str] = []
    known = set(schema.get("properties", {})) | COMMENT_KEYS
    for name in sorted(set(facts) - known):
        if name == "rules":
            said.append("rules: доли механизмов считает каталог по ответу проекта — "
                        "в фактах это второй источник того же числа (090); убрать")
        else:
            said.append(f"{name}: поле вне договора в корне — место ему в "
                        f"exchange.<тема> со своей schema")
    published = facts.get("schema")
    if isinstance(published, str) and re.fullmatch(r"\d+\.\d+", published):
        if tuple(map(int, published.split("."))) < tuple(map(int, current.split("."))):
            said.append(f"schema: формат {published} при договоре {current} — файл отстал")
    return said


def advise_family(manifest: object | None) -> list[str]:
    """Совет договора 1.6 о манифесте семьи — наличие и мажор формы. Кода не меняет.

    Каталог собирает манифесты семьи в сводку, и семейный значок каждого
    проекта сверяет по ней издателей; без манифеста издатель для семьи серый.
    Здесь читается только номер формы (157) — форму целиком держит каталог
    своим кодом, и вторая её запись разошлась бы с первой (090). В 2.0
    манифест обязателен (решение владельца 9 октября, #309, #316).
    """
    if manifest is None:
        return [f"манифеста семьи нет: {MANIFEST_PATH} в ветке {FACTS_REF} рядом с "
                f"facts.json — форма у каталога (контракт family {FAMILY_MAJOR}.x); "
                f"в 2.0 обязателен"]
    published = manifest.get("schema") if isinstance(manifest, dict) else None
    if not (isinstance(published, str) and re.fullmatch(r"\d+\.\d+", published)
            and published.split(".")[0] == FAMILY_MAJOR):
        return [f"манифест семьи: формат {published!r} — не family {FAMILY_MAJOR}.x "
                f"строкой; форму держит каталог (scripts/family.py, изъян_формы)"]
    return []


def contract_version(text: str) -> str:
    """Номер договора ``X.Y.Z`` из ``.rules/facts.version``. Иная форма — ``ValueError``."""
    number = text.strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", number):
        raise ValueError(f"номер договора «{number}» не формы X.Y.Z")
    return number


#: Метки шага для CI издателя в прозе договора: между ними — блок YAML, который
#: издатель вставляет к себе и который страница выпуска берёт отсюда же.
STEP_OPEN, STEP_CLOSE = "<!-- facts-ci-step -->", "<!-- /facts-ci-step -->"


def ci_step(prose: str) -> str | None:
    """Шаг для CI издателя из прозы договора — текст между метками. Нет меток — ``None``."""
    start, end = prose.find(STEP_OPEN), prose.find(STEP_CLOSE)
    if start < 0 or end < start:
        return None
    return prose[start + len(STEP_OPEN):end].strip()


def contract_drift(number: str, schema: dict, prose: str) -> list[str]:
    """Заголовки схемы и прозы против номера договора. Пусто — номер один.

    Номер вписан в два заголовка руками — читатель видит его, не открывая
    третьего файла, — и потому обязан сверяться с источником (005, 035):
    поднятый в одном месте договор иначе расходится молча.
    """
    series = ".".join(number.split(".")[:2])
    found: list[str] = []
    if not str(schema.get("title", "")).endswith(f"договор {series}"):
        found.append(f"facts.schema.json: заголовок «{schema.get('title')}» не "
                     f"кончается на «договор {series}»")
    if f"## Единые требования · договор {series}" not in prose:
        found.append(f"facts-contract.md: нет заголовка «## Единые требования · "
                     f"договор {series}»")
    # Тег в шаге для CI — третье место номера: устаревший тег прибил бы
    # издателей к прошлому выпуску молча, и шаг остался бы зелёным.
    step = ci_step(prose)
    if step is None:
        found.append(f"facts-contract.md: нет шага для CI между {STEP_OPEN} и {STEP_CLOSE}")
    elif f"FACTS_CONTRACT: facts-v{number}" not in step:
        found.append(f"facts-contract.md: шаг для CI прибит не к facts-v{number}")
    if f"^{series.split('.')[0]}\\." not in schema.get("properties", {}).get(
            "schema", {}).get("pattern", ""):
        found.append(f"facts.schema.json: schema.pattern не принимает мажор "
                     f"{series.split('.')[0]} договора")
    return found


def fetch(repo: str, path: str = FACTS_PATH) -> object | None:
    """Файл соседа по адресу договора. ``None`` — файла нет (404).

    Иной отказ площадки — исключение: «не ответил» и «нет файла» разные вещи.
    Без ``checks`` витрины спрашивать площадку нечем — это ``OSError``, то есть
    «не отработала», а не «не отвечает».
    """
    if checks is None:
        raise OSError("режим соседей — витринный: рядом нет checks.py, "
                      "издателю нужен --file")
    try:
        payload = checks.rest(f"/repos/{repo}/contents/{path}?ref={FACTS_REF}")
    except urllib.error.HTTPError as refusal:
        if refusal.code == 404:
            return None
        raise
    return json.loads(base64.b64decode(payload["content"]))


def read_manifest(path: pathlib.Path) -> object | None:
    """Манифест семьи с диска. ``None`` — файла нет; не JSON — строка-причина для совета."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except ValueError:
        return "не JSON"


def selftest() -> int:
    """Набор двусторонний (правило 140): эталон проходит, каждая порча — ловится."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    repo = "Owner/Name"
    good = {
        "schema": "1.2", "schema_of": "факты проекта для витрины", "repo": repo,
        "generated_at": "2026-10-01T07:22:31+00:00", "commit": "a" * 40,
        "ci": {"workflow": "ci.yml"}, "version": "1.3.45", "release": "1.3",
        "coverage_percent": 92.1, "tests": {"functions": 10, "modules": 2},
        "python": {"supported": ["3.12"]},
        "checks_per_pr": {"count": 3, "names": ["a", "b", "c"]},
    }
    reasons = {k: v for k, v in good.items()
               if k not in ("version", "release", "tests", "checks_per_pr")}
    reasons["none"] = {"version": "не версионируется", "release": "выпусков нет",
                       "tests": "кода нет", "checks_per_pr": "проверок нет"}

    def without(key: str) -> dict:
        return {k: v for k, v in good.items() if k != key}

    def with_(**changes: object) -> dict:
        return {**good, **changes}

    cases = [
        ("эталон", good, None),
        ("предмета нет — причиной в none", reasons, None),
        ("незнакомое поле сверх договора — не находка", with_(extra={"x": 1}), None),
        ("доли правил любой формы — не предмет договора",
         with_(rules={"by_mechanism": {"gate": 3}}), None),
        ("причина о долях правил — не из договора", {**good, "none": {"rules": "нет"}},
         "имя не из допустимых"),
        ("нет repo", without("repo"), "«repo»"),
        ("нет commit", without("commit"), "«commit»"),
        ("нет ci", without("ci"), "«ci»"),
        ("нет версии и нет причины", without("version"), "none.version"),
        ("нет выпуска и нет причины", without("release"), "none.release"),
        ("нет покрытия и нет причины", without("coverage_percent"), "none.coverage_percent"),
        ("python_versions вместо python", {**without("python"), "python_versions": ["3.12"]},
         "none.python"),
        ("схема числом", with_(schema=1), "ожидался string"),
        ("схема другого мажора", with_(schema="2.0"), "не той формы"),
        ("время без пояса", with_(generated_at="2026-10-01T07:22:31"), "не той формы"),
        ("короткий SHA", with_(commit="abc123"), "не той формы"),
        ("покрытие больше ста", with_(coverage_percent=120), "больше 100"),
        ("тестов дробное число", with_(tests={"functions": 1.5, "modules": 1}),
         "ожидался integer"),
        ("пустой список версий Python", with_(python={"supported": []}), "не меньше 1"),
        ("причина пустая", {**reasons, "none": {**reasons["none"], "version": ""}},
         "пустая строка"),
        ("причина о незнакомом показателе", {**good, "none": {"stars": "нет"}},
         "имя не из допустимых"),
        ("прогон CI не файлом", with_(ci={"workflow": "CI"}), "не той формы"),
        ("файл о другом репозитории", with_(repo="Owner/Other"), "лежит у Owner/Name"),
        # Выпуск — серия X.Y, версия — сборка X.Y.Z внутри неё (договор 1.3).
        ("выпуск тегом с v", with_(release="v1.3.0"), "release: «v1.3.0» не той формы"),
        ("ошибка формы выпуска — одна находка, не две", with_(release="v1.3.0"), 1),
        ("выпуск с нулевым хвостом", with_(release="1.3.0"), "release: «1.3.0» не той формы"),
        ("версия из двух чисел", with_(version="1.3"), "version: «1.3» не той формы"),
        ("версия с v", with_(version="v1.3.45"), "version: «v1.3.45» не той формы"),
        ("версия из чужой серии", with_(version="1.4.2"), "не сборка выпуска «1.3»"),
        ("серия — префикс без точки не считается", with_(release="1.1", version="1.11.157"),
         "не сборка выпуска «1.1»"),
        ("двузначные части — законно", with_(release="1.11", version="1.11.157"), None),
        ("версия без выпуска — сверять не с чем", {**without("release"),
                                                  "none": {"release": "выпусков нет"}}, None),
        ("не объект", [1, 2], "ожидался object"),
    ]
    broken = []
    for name, facts, expected in cases:
        found = check(facts, repo, schema)
        if isinstance(expected, int):
            ok = len(found) == expected
        else:
            ok = (not found) if expected is None else any(expected in line for line in found)
        if not ok:
            broken.append(f"{name}: ждали {'чисто' if expected is None else expected!r}, "
                          f"вышло {found}")
        print(f"  {'да ' if ok else 'НЕТ'} — {name}")

    # Обмен между проектами (1.4): тема со своей версией — законна; тема без
    # версии и тема с именем не той формы — находки, а не советы.
    exchange_cases = [
        ("тема обмена со своей версией", with_(exchange={"glossary": {"schema": "1.0",
                                                                     "cards": 2817}}), None),
        ("тема без своей версии", with_(exchange={"glossary": {"cards": 1}}),
         "exchange.glossary: нет обязательного поля «schema»"),
        ("версия темы числом", with_(exchange={"glossary": {"schema": 1}}), "ожидался string"),
        ("имя темы не той формы", with_(exchange={"Glossary!": {"schema": "1.0"}}),
         "имя не из допустимых"),
    ]
    for name, facts, expected in exchange_cases:
        found = check(facts, repo, schema)
        ok = (not found) if expected is None else any(expected in line for line in found)
        if not ok:
            broken.append(f"{name}: ждали {'чисто' if expected is None else expected!r}, "
                          f"вышло {found}")
        print(f"  {'да ' if ok else 'НЕТ'} — {name}")

    # Советы 1.4 — обе стороны: что 2.0 запретит, названо; договорное и
    # подпись «_» — молчат; свой минор не отстаёт от себя.
    advise_cases = [
        ("эталон текущего формата — молчит", with_(schema="1.4"), []),
        ("подпись «_» — не поле корня", with_(schema="1.4", _="комментарий"), []),
        ("обмен — не поле корня", with_(schema="1.4", exchange={"x": {"schema": "1.0"}}), []),
        ("своё поле в корне", with_(schema="1.4", glossary={"cards": 1}), ["glossary:"]),
        ("rules — отдельно и с причиной", with_(schema="1.4", rules={}), ["rules:", "090"]),
        ("отставший формат", with_(schema="1.2"), ["формат 1.2 при договоре 1.4"]),
        ("формат новее договора — не отставание", with_(schema="1.5"), []),
        ("двузначный минор — сравнение числом", with_(schema="1.10"), []),
    ]
    for name, facts, expected in advise_cases:
        said = advise(facts, schema, "1.4")
        ok = (not said) if not expected else all(any(part in line for line in said)
                                                 for part in expected)
        if not ok:
            broken.append(f"совет, {name}: ждали {expected or 'молчание'}, вышло {said}")
        print(f"  {'да ' if ok else 'НЕТ'} — совет: {name}")

    # Манифест семьи (1.6) — обе стороны: нет файла, не та форма — совет;
    # family 1.x любого минора — молчание. Форму целиком судит каталог.
    family_cases = [
        ("манифест family 1.1 — молчит", {"schema": "1.1"}, None),
        ("двузначный минор формы — законно", {"schema": "1.10"}, None),
        ("манифеста нет", None, "манифеста семьи нет"),
        ("мажор формы не тот", {"schema": "2.0"}, "не family 1.x"),
        ("номер числом, а не строкой", {"schema": 1.1}, "не family 1.x"),
        ("номер не той формы", {"schema": "1"}, "не family 1.x"),
        ("файл не JSON", "не JSON", "не family 1.x"),
        ("не объект", [1], "не family 1.x"),
    ]
    for name, manifest, expected in family_cases:
        said = advise_family(manifest)
        ok = (not said) if expected is None else any(expected in line for line in said)
        if not ok:
            broken.append(f"манифест, {name}: ждали {expected or 'молчание'}, вышло {said}")
        print(f"  {'да ' if ok else 'НЕТ'} — манифест: {name}")

    # Номер договора один: заголовки схемы и прозы сверяются с источником.
    titled = {**schema, "title": "facts.json — договор 1.4"}
    prose = ("x\n## Единые требования · договор 1.4\n"
             f"{STEP_OPEN}\n    FACTS_CONTRACT: facts-v1.4.0\n{STEP_CLOSE}\n")
    drift_cases = [
        ("заголовки совпадают с номером", "1.4.0", titled, prose, 0),
        ("схема на прежнем номере", "1.4.0", {**titled, "title": "договор 1.3"}, prose, 1),
        ("проза на прежнем номере", "1.4.0", titled, prose.replace("договор 1.4", "договор 1.3"), 1),
        ("мажор договора не принят схемой", "2.0.0",
         {**titled, "title": "договор 2.0"}, prose.replace("1.4", "2.0"), 1),
        ("тег шага на прежнем номере", "1.4.7", titled, prose, 1),
        ("шага для CI нет вовсе", "1.4.0", titled, prose.split(STEP_OPEN)[0], 1),
        ("метки шага перепутаны", "1.4.0", titled,
         prose.replace(STEP_OPEN, "@@").replace(STEP_CLOSE, STEP_OPEN).replace("@@", STEP_CLOSE), 1),
    ]
    for name, number_, schema_, prose_, expected in drift_cases:
        got = len(contract_drift(number_, schema_, prose_))
        if got != expected:
            broken.append(f"номер договора, {name}: ждали {expected}, вышло {got}")
        print(f"  {'да ' if got == expected else 'НЕТ'} — номер договора: {name}")
    # Живой путь --contract: main на подставной прозе. Старый номер в
    # заголовке — исход 1, верный — 0; сравнение прямо с main(), так его
    # считает и храповик непрогнанных исходов (check_mechanisms).
    import contextlib                                          # noqa: PLC0415
    import io                                                  # noqa: PLC0415
    import tempfile                                            # noqa: PLC0415
    real_prose = CONTRACT_PATH.read_text(encoding="utf-8")
    before = len(broken)
    saved_path, saved_argv = CONTRACT_PATH, sys.argv
    with tempfile.TemporaryDirectory(dir=os.environ.get("RUNNER_TEMP")) as tmp:
        stale = pathlib.Path(tmp) / "facts-contract.md"
        stale.write_text(re.sub(r"(## Единые требования · договор )\d+\.\d+",
                                r"\g<1>0.9", real_prose), encoding="utf-8")
        fresh = pathlib.Path(tmp) / "fresh.md"
        fresh.write_text(real_prose, encoding="utf-8")
        sys.argv = ["check_facts.py", "--contract"]
        try:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                globals()["CONTRACT_PATH"] = stale
                if main() != 1:
                    broken.append("--contract: проза на старом номере не отвергнута")
                globals()["CONTRACT_PATH"] = fresh
                if main() != 0:
                    broken.append("--contract: верная проза отвергнута")
        finally:
            globals()["CONTRACT_PATH"] = saved_path
            sys.argv = saved_argv
    print(f"  {'да ' if len(broken) == before else 'НЕТ'} — --contract: старый номер в прозе — 1, верный — 0")

    for bad in ("1.4", "v1.4.0", " ", "1.4.0.1"):
        try:
            contract_version(bad)
            broken.append(f"номер договора «{bad}» принят")
        except ValueError:
            pass

    # Образец выпуска — по текущему договору, без единой находки и совета:
    # издатель берёт его за основу, и устаревший образец учил бы старому.
    number = contract_version(VERSION_PATH.read_text(encoding="utf-8"))
    current = ".".join(number.split(".")[:2])
    example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    said = check(example, str(example.get("repo")), schema) + advise(example, schema, current)
    if said or example.get("schema") != current:
        broken.append(f"образец: формат {example.get('schema')} при договоре {current}, "
                      f"находок и советов {len(said)} — {said}")
    print(f"  {'да ' if not said and example.get('schema') == current else 'НЕТ'} — "
          f"образец по договору {current} без находок и советов")

    # Проба переноса: файл, скопированный в пустой каталог со схемой, номером и
    # образцом, — ровно так он лежит в выпуске, — работает без checks витрины.
    # Обе стороны: образец — исход 0, испорченный образец — исход 1.
    import shutil                                              # noqa: PLC0415
    import subprocess                                          # noqa: PLC0415
    with tempfile.TemporaryDirectory(dir=os.environ.get("RUNNER_TEMP")) as tmp:
        for source in (pathlib.Path(__file__), SCHEMA_PATH, VERSION_PATH, EXAMPLE_PATH):
            shutil.copy(source, tmp)
        spoiled = pathlib.Path(tmp) / "spoiled.json"
        spoiled.write_text(json.dumps({**example, "commit": "abc"}), encoding="utf-8")
        # Манифест рядом с фактами — так он лежит у издателя перед публикацией.
        # Без него совет «манифеста нет», код тот же: 1.x советует (051).
        family = pathlib.Path(tmp) / "family"
        family.mkdir()
        (family / "contracts.json").write_text('{"schema": "1.1"}', encoding="utf-8")
        shutil.copy(EXAMPLE_PATH, family / "facts.json")
        for name, target, expected, warns in (
                ("образец", EXAMPLE_PATH.name, 0, True),
                ("испорченный образец", spoiled.name, 1, True),
                ("образец с манифестом рядом", "family/facts.json", 0, False)):
            run = subprocess.run([sys.executable, "-I", "check_facts.py", "--file", target,
                                  "--repo", str(example["repo"])], cwd=tmp,
                                 capture_output=True, text=True, encoding="utf-8")
            warned = "манифеста семьи нет" in run.stdout
            ok = run.returncode == expected and warned == warns
            if not ok:
                last = (run.stderr.strip().splitlines() or ["вывода нет"])[-1]
                broken.append(f"перенос, {name}: ждали исход {expected} и совет "
                              f"{'есть' if warns else 'нет'}, вышло {run.returncode} и "
                              f"{'есть' if warned else 'нет'} — последняя строка: {last}")
            print(f"  {'да ' if ok else 'НЕТ'} — перенос без checks витрины: {name} — "
                  f"исход {run.returncode}, совет о манифесте {'есть' if warned else 'нет'}")

    # Незнакомое ключевое слово в схеме — отказ, а не пропуск требования.
    try:
        validate({}, {"type": "object", "dependentRequired": {}})
        broken.append("незнакомое ключевое слово пропущено молча")
    except ValueError:
        print("  да  — незнакомое ключевое слово схемы — отказ")

    if broken:
        print(annotate("error", "самопроверка провалена"), file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: договор фактов держит каждое требование схемы")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", help="проверить локальный файл вместо соседей")
    parser.add_argument("--repo", help="чей это файл — для --file")
    parser.add_argument("--manifest", type=pathlib.Path,
                        help="манифест семьи для --file; по умолчанию — contracts.json "
                             "рядом с файлом фактов")
    parser.add_argument("--schema", type=pathlib.Path, default=SCHEMA_PATH,
                        help="схема договора; по умолчанию — из дерева или рядом")
    parser.add_argument("--version", type=pathlib.Path, default=VERSION_PATH,
                        help="номер договора; по умолчанию — из дерева или рядом")
    parser.add_argument("--contract", action="store_true",
                        help="только сверить номер договора со схемой и прозой — без сети")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    try:
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        number = contract_version(args.version.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(annotate("error", f"проверка не отработала: схема или номер договора "
                              f"не прочитаны — {error}"), file=sys.stderr)
        return 2
    current = ".".join(number.split(".")[:2])

    if args.contract:
        try:
            drift = contract_drift(number, schema, CONTRACT_PATH.read_text(encoding="utf-8"))
        except OSError as error:
            print(f"проверка не отработала: проза договора не прочитана — {error}",
                  file=sys.stderr)
            return 2
        for line in drift:
            print(annotate("error", line), file=sys.stderr)
        if drift:
            return 1
        print(f"договор фактов {number}: схема и проза говорят тот же номер")
        return 0

    if args.file:
        if not args.repo:
            print("проверка не отработала: к --file нужен --repo", file=sys.stderr)
            return 2
        try:
            facts = json.loads(pathlib.Path(args.file).read_text(encoding="utf-8"))
            found = check(facts, args.repo, schema)
            manifest = read_manifest(args.manifest
                                     or pathlib.Path(args.file).parent / "contracts.json")
        except (OSError, ValueError) as error:
            print(f"проверка не отработала: файл не прочитан — {error}", file=sys.stderr)
            return 2
        for line in found:
            print(f"  • {line}")
        for line in advise(facts, schema, current) + advise_family(manifest):
            print(f"  ⚠ {line}")
        print(f"{args.repo}: {'договору отвечает' if not found else f'расхождений {len(found)}'}")
        return 1 if found else 0

    if checks is None:
        print("проверка не отработала: режим соседей — витринный, рядом нет checks.py; "
              "издателю нужен --file <facts.json> --repo <владелец/имя>", file=sys.stderr)
        return 2
    repos = [p["repo"] for p in json.loads(PROJECTS_PATH.read_text(encoding="utf-8"))["projects"]]
    silent: list[str] = []
    total = advised = 0
    for repo in repos:
        try:
            facts = fetch(repo)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
            silent.append(repo)
            print(annotate("warning", f"{repo}: площадка не ответила о facts.json — {error}"))
            continue
        found = ([f"файла нет: {FACTS_PATH} в ветке {FACTS_REF}"] if facts is None
                 else check(facts, repo, schema))
        try:
            manifest = fetch(repo, MANIFEST_PATH)
        except ValueError:      # файл есть, но не JSON — это форма, а не молчание
            manifest = "не JSON"
        except (urllib.error.URLError, OSError, KeyError) as error:
            silent.append(repo)
            print(annotate("warning", f"{repo}: площадка не ответила о contracts.json — {error}"))
            continue
        said = advise(facts, schema, current) + advise_family(manifest)
        total += len(found)
        advised += len(said)
        print(f"{repo}: {'договору отвечает' if not found else f'расхождений {len(found)}'}")
        for line in found:
            print(f"  • {line}")
        for line in said:
            print(f"  ⚠ {line}")

    if silent:
        print(annotate("error", f"проверка не отработала: не ответили о "
                              f"{len(silent)} из {len(repos)}"), file=sys.stderr)
        return 2
    # Предупреждения считаются отдельно и кода не меняют: в 1.4 они совет, в
    # 2.0 — отказ. Ноль здесь и есть условие подъёма мажора (#309).
    print(f"проектов {len(repos)}, расхождений {total}, предупреждений {advised} "
          f"(договор {number})")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
