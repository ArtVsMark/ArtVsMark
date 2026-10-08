#!/usr/bin/env python3
"""Чем правило держится у соседей по своду — до того, как строить своё.

ЗАЧЕМ. Правило 162: прежде чем заводить механизм правилу, у которого его нет,
смотрят, чем это правило держится у тех, кто отвечает по тому же каталогу.
Ответ соседа не приказ — он называет того, кто уже платил за этот механизм, и
избавляет от второй реализации одного алгоритма (090).

ПОЧЕМУ НЕ ПОХОД ПО ЧУЖИМ РЕПОЗИТОРИЯМ. Каталог собирает сводку сам —
``export/where.json``, раздел «чем держат другие». Ходить за тем же в чужие
деревья значило бы держать копию его агрегатора: она совпадает ровно до первой
правки на той стороне.

ПОЧЕМУ ЭТО НЕ ГЕЙТ. «Приём переносится» решает человек: стеки разные, и чужой
механизм не обязан подойти. Отказ здесь означал бы «повтори за соседом», то
есть ровно ту копию, которую запрещает 090. Поэтому исход у скрипта один —
показать; красное он даёт только когда сводка не прочитана.

Исходы: 0 — показано (в том числе «спрашивать не о чем»: сводка при этом
ВСЁ РАВНО прочитана — адрес, который не ходят, устаревает молча);
1 — предмет не разобран; 2 — источник не ответил.
"""

import json
import pathlib
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import checks  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
BINDINGS = ROOT / ".rules/bindings.json"
#: Наш собственный адрес в сводке: себя в советчики не берут.
SELF = "ArtVsMark/ArtVsMark"


def unmechanized(rules: dict) -> list[str]:
    """Правила, о которых спрашивают соседей: действующие и не обеспеченные машиной.

    ДВА ПРИЗНАКА, А НЕ ОДИН. ``mechanism: none`` — «держится ничем», и это
    исходный предмет 162. Но ответ «держать машиной нельзя» (``holdable: no``)
    — такое же утверждение об отсутствии машинной половины, только записанное
    документом, и прежде он сюда не попадал: 8 октября 21 из 23 таких ответов
    оказались неверны — их половину держали гейтами соседи, — а прогон печатал
    «спрашивать не о чем» (#286). ``not-yet`` сюда не берётся: там вопрос
    уже задан, и образец назван в ``machine_half``.
    """
    return sorted(k for k, v in rules.items()
                  if v.get("status") == "active"
                  and (v.get("mechanism") == "none" or v.get("holdable") == "no"))


def advice(where: dict, gaps: list[str]) -> dict[str, list[tuple[str, str]]]:
    """По каждому нашему пробелу — соседи, у которых механизм есть.

    Берётся ответ с разрешимым адресом: пересказ соседа помогает не больше,
    чем его отсутствие (граница правила 162). Адрес здесь — то, что сосед
    записал в своём ``where``; проверять его существование в чужом дереве
    нечем, и обещать этого не надо.
    """
    found: dict[str, list[tuple[str, str]]] = {}
    for consumer in where.get("consumers", []):
        repo = consumer.get("repo", "")
        if repo == SELF or consumer.get("state") != "подключён":
            continue
        holds = consumer.get("holds") or {}
        for rule in gaps:
            held = holds.get(rule) or {}
            # Форма записи — та же, что у нас: механизм и адрес. Ответ без
            # адреса не берётся: пересказ соседа помогает не больше, чем его
            # отсутствие (граница правила 162).
            address = (held.get("where") or "").strip() if isinstance(held, dict) else ""
            if address:
                found.setdefault(rule, []).append(
                    (repo, f"{held.get('mechanism', '?')}: {address}"))
    return found


#: Механизмы, которые краснеют сами, — в отличие от документа, который читают.
MACHINE = ("gate", "pipeline", "code")


def machine_held(found: dict[str, list[tuple[str, str]]]) -> list[str]:
    """Правила, которые хоть у одного соседа держит машина, а не документ."""
    return sorted(rule for rule, answers in found.items()
                  if any(held.split(":", 1)[0] in MACHINE for _, held in answers))


def selftest() -> int:
    """Прогоняет разбор тем, что он обязан отобрать и отбросить (140, 145).

    Сети набор не требует: сводка подставная. Спрашивается механизм — что
    попадёт в подсказку окну, — а не пересказ условия (150).
    """
    broken: list[str] = []

    rules = {
        "006": {"status": "active", "mechanism": "none", "where": "…"},
        "010": {"status": "active", "mechanism": "gate", "where": "scripts/x.py"},
        "011": {"status": "not-applicable", "why": "предмета нет"},
        "012": {"status": "active", "mechanism": "none", "where": "…"},
        # «Нельзя» документом — тот же вопрос о машинной половине (#286).
        "013": {"status": "active", "mechanism": "document", "holdable": "no"},
        # «Строится» — вопрос уже задан, образец назван в machine_half.
        "014": {"status": "active", "mechanism": "document", "holdable": "not-yet"},
        # Гейт с ответом «нельзя» об оставшейся половине — тоже спрашивают.
        "015": {"status": "active", "mechanism": "gate", "holdable": "no"},
        "016": {"status": "not-applicable", "holdable": "no"},
    }
    gaps = unmechanized(rules)
    if gaps != ["006", "012", "013", "015"]:
        broken.append(f"пробелы отобраны неверно: {gaps}")
    print(f"  {gaps} — пробелы: active без механизма или с ответом «нельзя»")

    where = {"consumers": [
        {"repo": "ArtVsMark/Stepik-Python-Grader", "state": "подключён",
         "holds": {"006": {"mechanism": "gate", "where": "scripts/check_x.py"}}},
        {"repo": SELF, "state": "подключён",
         "holds": {"006": {"mechanism": "gate", "where": "своё же — не совет"}}},
        {"repo": "ArtVsMark/Glossary-Python", "state": "не подключён",
         "holds": {"006": {"mechanism": "gate", "where": "неподключённый не советчик"}}},
        {"repo": "ArtVsMark/Claude-Code_Usage-Token", "state": "подключён",
         "holds": {"012": {"mechanism": "document", "where": ""}}},
    ]}
    got = advice(where, gaps)
    cases = [
        ("сосед с адресом попадает в подсказку",
         [r for r, _ in got.get("006", [])] == ["ArtVsMark/Stepik-Python-Grader"]),
        ("себя в советчики не берут",
         all(repo != SELF for answers in got.values() for repo, _ in answers)),
        ("неподключённый сосед не советует",
         all("Glossary" not in repo for answers in got.values() for repo, _ in answers)),
        ("ответ без адреса не берётся — пересказ не помогает", "012" not in got),
        ("механизм назван вместе с адресом",
         got.get("006", [("", "")])[0][1].startswith("gate: ")),
        ("машиной считается гейт, документ — нет",
         machine_held({"006": [("a", "gate: x")], "012": [("b", "document: y")]})
         == ["006"]),
    ]
    for name, ok in cases:
        if not ok:
            broken.append(f"подсказка соседей: {name} — нет")
        print(f"  {'да ' if ok else 'НЕТ'} — подсказка соседей: {name}")

    # Исход «предмет не разобран» объявлен и прогоняется целиком: он живёт в
    # main, и вызвать его подстановкой нельзя (правило 145).
    import subprocess
    probe = subprocess.run([sys.executable, __file__, "--selftest-broken-bindings"],
                           capture_output=True, text=True, encoding="utf-8", env={"PATH": "/usr/bin:/bin"})
    print(f"  код {probe.returncode} — исход «предмет не разобран» прогнан")

    if broken:
        print("\nсамопроверка провалена:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: подсказка берёт подключённых соседей с адресом")
    return 0


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()
    if "--selftest-broken-bindings" in sys.argv[1:]:
        # Ветка для набора: ответ витрины намеренно не читается.
        globals()["BINDINGS"] = pathlib.Path("/nonexistent/bindings.json")
    try:
        rules = json.loads(BINDINGS.read_text(encoding="utf-8"))["rules"]
    except (OSError, ValueError, KeyError) as broken:
        print(checks.annotate("error", f"не разобран ответ витрины: {broken}"),
              file=sys.stderr)
        return 1

    # ИСТОЧНИК ЧИТАЕТСЯ ДО ТОГО, КАК ВЫЯСНЯЕТСЯ, ЕСТЬ ЛИ О ЧЁМ СПРАШИВАТЬ.
    # Прежде порядок был обратный, и это скрыло УСТАРЕВШИЙ адрес: 4 сентября
    # каталог перенёс сводку на ветку `badges`, а здесь остался `main`. Четверо
    # суток прогон печатал «спрашивать не о чем» и в сеть не ходил — долг по
    # правилам был нулевой, — то есть зеленел, ничего не проверив (правило 146).
    # Адрес, по которому не ходят, устаревает молча: первый же настоящий вопрос
    # получил бы 404 вместо совета.
    try:
        with urllib.request.urlopen(checks.CATALOGUE_WHERE, timeout=30) as answer:
            where = json.loads(answer.read())
    except (urllib.error.URLError, OSError, ValueError) as refusal:
        print(checks.annotate(
            "warning", f"сводка соседей не прочитана "
            f"({checks.CATALOGUE_WHERE}): {refusal}"),
            file=sys.stderr)
        return 2

    consumers = where.get("consumers") or []
    print(f"сводка каталога прочитана: потребителей {len(consumers)}, "
          f"собрана {where.get('generated_at', 'без отметки времени')}")

    gaps = unmechanized(rules)
    if not gaps:
        print("правил без механизма и с ответом «нельзя» нет — спрашивать не о чем")
        return 0

    helped = advice(where, gaps)
    # «Решено» засчитывает и ответ соседа «держится документом», а он на вопрос
    # о машинной половине не отвечает: число машиной — отдельно (#286).
    by_machine = machine_held(helped)
    print(f"правил без механизма или с ответом «нельзя»: {len(gaps)}; "
          f"у соседей с адресом: {len(helped)}, из них машиной: {len(by_machine)}")
    for rule in gaps:
        answers = helped.get(rule)
        if not answers:
            print(f"  {rule}: у соседей тоже ничем — предмет трудный, и цена постройки "
                  f"выше, чем кажется")
            continue
        for repo, held in answers:
            print(f"  {rule}: {repo.split('/')[-1]} — {held}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
