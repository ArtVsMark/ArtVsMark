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

Запуск::

    python scripts/check_facts.py              # все проекты из projects.json
    python scripts/check_facts.py --file f.json --repo владелец/имя
    python scripts/check_facts.py --selftest

Исходы: 0 — все файлы отвечают договору; 1 — есть расхождения, перечислены по
проектам; 2 — проверка не отработала: схема не прочитана, площадка не ответила
о чьём-то файле (правило 039: «не ответил» не записывается в «не отвечает»).
"""

import argparse
import base64
import json
import pathlib
import re
import sys
import urllib.error

import checks

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / ".rules" / "facts.schema.json"
PROJECTS_PATH = ROOT / "projects.json"

#: Адрес файла у издателя. Один на всех — в этом и решение.
FACTS_PATH = ".github/badges/facts.json"
FACTS_REF = "badges"

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


def fetch(repo: str) -> object | None:
    """Файл соседа по адресу договора. ``None`` — файла нет (404).

    Иной отказ площадки — исключение: «не ответил» и «нет файла» разные вещи.
    """
    try:
        payload = checks.rest(f"/repos/{repo}/contents/{FACTS_PATH}?ref={FACTS_REF}")
    except urllib.error.HTTPError as refusal:
        if refusal.code == 404:
            return None
        raise
    return json.loads(base64.b64decode(payload["content"]))


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

    # Незнакомое ключевое слово в схеме — отказ, а не пропуск требования.
    try:
        validate({}, {"type": "object", "dependentRequired": {}})
        broken.append("незнакомое ключевое слово пропущено молча")
    except ValueError:
        print("  да  — незнакомое ключевое слово схемы — отказ")

    if broken:
        print(checks.annotate("error", "самопроверка провалена"), file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: договор фактов держит каждое требование схемы")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", help="проверить локальный файл вместо соседей")
    parser.add_argument("--repo", help="чей это файл — для --file")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(checks.annotate("error", f"проверка не отработала: схема не прочитана — {error}"),
              file=sys.stderr)
        return 2

    if args.file:
        if not args.repo:
            print("проверка не отработала: к --file нужен --repo", file=sys.stderr)
            return 2
        try:
            found = check(json.loads(pathlib.Path(args.file).read_text(encoding="utf-8")),
                          args.repo, schema)
        except (OSError, ValueError) as error:
            print(f"проверка не отработала: файл не прочитан — {error}", file=sys.stderr)
            return 2
        for line in found:
            print(f"  • {line}")
        print(f"{args.repo}: {'договору отвечает' if not found else f'расхождений {len(found)}'}")
        return 1 if found else 0

    repos = [p["repo"] for p in json.loads(PROJECTS_PATH.read_text(encoding="utf-8"))["projects"]]
    silent: list[str] = []
    total = 0
    for repo in repos:
        try:
            facts = fetch(repo)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
            silent.append(repo)
            print(checks.annotate("warning", f"{repo}: площадка не ответила о facts.json — {error}"))
            continue
        found = ([f"файла нет: {FACTS_PATH} в ветке {FACTS_REF}"] if facts is None
                 else check(facts, repo, schema))
        total += len(found)
        print(f"{repo}: {'договору отвечает' if not found else f'расхождений {len(found)}'}")
        for line in found:
            print(f"  • {line}")

    if silent:
        print(checks.annotate("error", f"проверка не отработала: не ответили о "
                              f"{len(silent)} из {len(repos)}"), file=sys.stderr)
        return 2
    print(f"проектов {len(repos)}, расхождений {total}")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
