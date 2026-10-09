#!/usr/bin/env python3
"""Манифест семьи витрины: что она отдаёт соседям и последний выпуск (#316, #318).

ЧТО ЭТО. Каталог завёл контракт ``family``: каждый проект семьи кладёт на свою
ветку ``badges`` файл ``.github/badges/contracts.json`` — что он отдаёт
(``gives``), последний выпуск (``release``) и парные связи (``takes``).
Каталог собирает манифесты в сводку, а семейный значок каждого проекта сверяет
по ней, не отстал ли он от издателей. Витрина — издатель договора фактов, и
пока манифеста нет, блок ``AVM`` у всей семьи серый.

ВСЁ ВЫВОДИТСЯ ИЗ ДЕРЕВА, РУКАМИ НЕ ПИШЕТСЯ НИЧЕГО (035):

* ``gives.facts`` — ``мажор.минор`` из ``.rules/facts.version``: третья цифра у
  договора всегда ноль (решение владельца 9 октября), и формы она не меняет;
* ``release`` — последний тег ``facts-v*`` по номеру и его коммит. Выпуск у
  витрины один — договор фактов; страница профиля выпусков не получает;
* ``takes`` — пуст, и это названо, а не забыто. Пару каталог читает из
  JSON-файла по ключу, а номер прочитанной сводки ``where`` у витрины живёт
  в коде (``build_metrics.py::WHERE_READ``). Остальные связи — пины каталога и
  номера ответа — сверка семьи находит в дереве сама.

ФОРМУ СУДИТ КАТАЛОГ, А НЕ КОПИЯ (090). С ``--catalogue`` сборщик зовёт
``family.изъян_формы`` из дерева каталога на закреплённой версии и сверяет
номер формата ``FAMILY_SCHEMA``. Без него — только сборка: так набор
гоняется без сети.

ГРАНИЦА, НАЗВАННАЯ ДЛЯ КАТАЛОГА (#316, пункт 3). Сверка ``family_check``
ищет «последний тег» маской ``v*``, а тег витрины — ``facts-vX.Y.Z``. Судить
витрину её же значком сверка пока не умеет — чинится на стороне каталога.

Запуск::

    python scripts/family_manifest.py --out ФАЙЛ [--catalogue ПУТЬ/scripts]
    python scripts/family_manifest.py --selftest

Исходы: 0 — манифест собран (и, с ``--catalogue``, принят формой каталога);
1 — форма отвергнута каталогом или номер формата разошёлся — причина названа;
2 — не отработал: номер договора или теги не прочитаны, код каталога не
загрузился.
"""

import argparse
import importlib
import json
import pathlib
import subprocess
import sys

import check_facts
import checks

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROJECT = "ArtVsMark/ArtVsMark"
#: Номер формата манифеста семьи, под который собран этот файл. Наше
#: утверждение «собрано под 1.1»; с ``--catalogue`` сверяется с ``FAMILY_SCHEMA``.
FAMILY_SCHEMA = "1.1"
TAG_GLOB = "facts-v*"


def series(number: str) -> str:
    """``мажор.минор`` договора из номера ``X.Y.Z``."""
    return ".".join(check_facts.contract_version(number).split(".")[:2])


def latest_release(tags: list[str], commit_of) -> dict[str, str] | None:
    """Последний выпуск договора — тег с наибольшим номером и его коммит.

    Сравнение по числам, а не строкой: ``facts-v1.10.0`` новее ``facts-v1.9.0``.
    Тег не той формы — не выпуск договора, он пропускается.
    """
    numbered = []
    for tag in tags:
        try:
            numbered.append((tuple(map(int, check_facts.contract_version(
                tag.removeprefix("facts-v")).split("."))), tag))
        except ValueError:
            continue
    if not numbered:
        return None
    tag = max(numbered)[1]
    return {"tag": tag, "sha": commit_of(tag)}


def build(number: str, tags: list[str], commit_of) -> dict:
    """Манифест витрины по номеру договора и тегам дерева."""
    return {
        "schema": FAMILY_SCHEMA,
        "project": PROJECT,
        "release": latest_release(tags, commit_of),
        "gives": {"facts": series(number)},
        "takes": [],
    }


def git(*args: str) -> str:
    """Вывод git в корне витрины."""
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout.strip()


def judged(manifest: dict, catalogue: pathlib.Path) -> list[str]:
    """Что каталог говорит о форме манифеста — его кодом на его версии."""
    sys.path.insert(0, str(catalogue))
    try:
        family = importlib.import_module("family")
    finally:
        sys.path.remove(str(catalogue))
    found = []
    if (flaw := family.изъян_формы(manifest)) is not None:
        found.append(f"каталог отвергает форму манифеста: {flaw}")
    if family.FAMILY_SCHEMA != FAMILY_SCHEMA:
        found.append(f"формат манифеста семьи у каталога {family.FAMILY_SCHEMA}, а сборщик "
                     f"собран под {FAMILY_SCHEMA} — перечитать форму и поднять номер")
    return found


def selftest() -> int:
    """Обе стороны (140): номер и выпуск выводятся из дерева, порча названа."""
    broken: list[str] = []
    shas = {"facts-v1.4.0": "a" * 40, "facts-v1.5.0": "b" * 40, "facts-v1.10.0": "c" * 40}
    cases = [
        ("последний по номеру, а не по строке", list(shas), "facts-v1.10.0"),
        ("один выпуск", ["facts-v1.4.0"], "facts-v1.4.0"),
        ("чужие теги не выпуск договора", ["v2.0.0", "facts-v1.4", "facts-vX"], None),
        ("выпусков нет", [], None),
    ]
    for name, tags, expected in cases:
        got = latest_release(tags, shas.get)
        tag = got["tag"] if got else None
        if tag != expected:
            broken.append(f"выпуск, {name}: ждали {expected}, вышло {tag}")
        print(f"  {'да ' if tag == expected else 'НЕТ'} — выпуск: {name}")

    made = build("1.5.0", ["facts-v1.5.0"], shas.get)
    want = {"schema": FAMILY_SCHEMA, "project": PROJECT,
            "release": {"tag": "facts-v1.5.0", "sha": "b" * 40},
            "gives": {"facts": "1.5"}, "takes": []}
    if made != want:
        broken.append(f"манифест: ждали {want}, вышло {made}")
    print(f"  {'да ' if made == want else 'НЕТ'} — манифест из номера 1.5.0 и тега facts-v1.5.0")
    try:
        series("1.5")
        broken.append("номер «1.5» принят — у договора три числа")
    except ValueError:
        pass

    # Живой номер дерева: манифест говорит ровно то, что лежит в facts.version.
    number = check_facts.contract_version(check_facts.VERSION_PATH.read_text(encoding="utf-8"))
    if build(number, [], shas.get)["gives"]["facts"] != series(number):
        broken.append("gives.facts разошёлся с .rules/facts.version")

    # Живой путь main — три исхода. Каталог подставной: его family отвергает
    # форму (1) или принимает (0); без --out — «не отработал» (2). Сравнение
    # прямо с main(): так его считает храповик непрогнанных исходов.
    import contextlib                                          # noqa: PLC0415
    import io                                                  # noqa: PLC0415
    import os                                                  # noqa: PLC0415
    import tempfile                                            # noqa: PLC0415
    saved_argv, before = sys.argv, len(broken)
    with tempfile.TemporaryDirectory(dir=os.environ.get("RUNNER_TEMP")) as tmp:
        stubs = {"reject": "def изъян_формы(doc):\n    return 'нет ключа «takes»'\n",
                 "accept": "def изъян_формы(doc):\n    return None\n"}
        for name, body in stubs.items():
            (pathlib.Path(tmp) / name).mkdir()
            (pathlib.Path(tmp) / name / "family.py").write_text(
                f"FAMILY_SCHEMA = {FAMILY_SCHEMA!r}\n{body}", encoding="utf-8")
        out = f"{tmp}/contracts.json"
        try:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                sys.argv = ["family_manifest.py", "--out", out, "--catalogue", f"{tmp}/reject"]
                if main() != 1:
                    broken.append("форма, отвергнутая каталогом, не дала исход 1")
                sys.modules.pop("family", None)
                sys.argv = ["family_manifest.py"]
                if main() != 2:
                    broken.append("вызов без --out не назван «не отработал»")
                sys.argv = ["family_manifest.py", "--out", out, "--catalogue", f"{tmp}/accept"]
                if main() != 0:
                    broken.append("форма, принятая каталогом, не дала исход 0")
        finally:
            sys.argv = saved_argv
            sys.modules.pop("family", None)
    print(f"  {'да ' if len(broken) == before else 'НЕТ'} — main: отказ формы 1, без --out 2, "
          f"принятая форма 0")

    if broken:
        print(checks.annotate("error", "самопроверка провалена"), file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: манифест семьи выводится из дерева")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=pathlib.Path, help="куда записать манифест")
    parser.add_argument("--catalogue", type=pathlib.Path,
                        help="каталог scripts/ каталога правил на закреплённой версии")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if not args.out:
        print("сборщик не отработал: нужен --out", file=sys.stderr)
        return 2
    try:
        number = check_facts.contract_version(check_facts.VERSION_PATH.read_text(encoding="utf-8"))
        tags = git("tag", "--list", TAG_GLOB).split()
        manifest = build(number, tags, lambda tag: git("rev-list", "-n", "1", tag))
        found = judged(manifest, args.catalogue) if args.catalogue else []
    except (OSError, ValueError, ImportError, AttributeError,
            subprocess.CalledProcessError) as error:
        print(checks.annotate("error", f"сборщик не отработал: {error}"), file=sys.stderr)
        return 2
    if found:
        for line in found:
            print(checks.annotate("error", line), file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    release = manifest["release"]["tag"] if manifest["release"] else "выпусков нет"
    print(f"манифест семьи собран: отдаю facts {manifest['gives']['facts']}, выпуск {release}"
          f"{', форма принята каталогом' if args.catalogue else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
