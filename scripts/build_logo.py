#!/usr/bin/env python3
"""Рисует фирменный знак витрины и впечатывает его в баннер.

Знак читается как последовательность: шаг, шаг, шаг, пройденная проверка,
подпись. Поэтому его элементы прочерчиваются по очереди слева направо — это
часть замысла, а не украшение: страница показывает не картинку, а порядок
работы, которым она держится.

ЗАЧЕМ СКРИПТ, А НЕ SVG РУКАМИ. Вся геометрия — производная четырёх чисел:
плеча шеврона, шага между ними, зазора до галки и толщины штриха. Координаты,
подобранные на глаз, разъезжаются при первой правке: сдвинули шеврон — поехали
зазор, поля и тайминги появления. Здесь их считает код, а поля обрезаются по
фактическому bbox.

ЗНАК ЖИВЁТ В ДВУХ МЕСТАХ, И ОБА ПИШЕТ ОДИН ИСТОЧНИК. Отдельными файлами
``assets/logo-*.svg`` — и внутри баннера, между маркерами ``<!--logo-->`` в
``assets/header-*.svg``, на месте прежней карточки с ``>>>``. Второе место
появилось не для красоты: знак и карточка несли один и тот же мотив, и
страница показывала его дважды.

СБОРКА ЕГО НЕ ЗАПУСКАЕТ. Знак меняется реже изменений, как ``divider-*``: он
рукодельный ассет и живёт в дереве, а не в ветке ``assets`` среди производных
суточного прогона (правило 160). Запускается руками::

    python scripts/build_logo.py            # перерисовать
    python scripts/build_logo.py --check    # то же, что проверит конвейер
    python scripts/build_logo.py --selftest # отрицательный набор

ПОЧЕМУ ЗНАК ПЕРЕРИСОВАН, А НЕ ОБВЕДЁН. Утверждённый концепт пришёл тремя PNG
(``assets/logo-source/``), и трассировать их нечем и незачем — в них четыре
дефекта, которые обводка перенесла бы в вектор:

* ПРОЗРАЧНОСТИ НЕТ. Все три файла — RGB без альфа-канала: «прозрачный фон»
  нарисован шахматкой прямо в пикселях. На тёмной теме README это был бы белый
  клетчатый прямоугольник, а не логотип;
* ГАЛКА НЕ ЧИТАЛАСЬ. У чекмарка вершина обязана быть нижней точкой фигуры. В
  исходнике третий шеврон стоял ровно там, где у галки короткое плечо, и ряд
  читался зигзагом. Здесь галка отставлена на ``GAP`` — заметно больше шага
  между шевронами, — а её длинное плечо вдвое длиннее короткого;
* МОНОГРАММА ЧИТАЛАСЬ КАК «AM». Буква V была вписана внутрь M и терялась.
  Здесь три буквы стоят раздельно, одной геометрией со знаком;
* ДВА ВАРИАНТА БЫЛИ РАЗНЫМИ ЗНАКАМИ: основной обведён контуром в две линии,
  иконка залита сплошняком. Здесь оба — один знак с разной толщиной.

Палитра при этом НЕ выдумана: она снята пипеткой с утверждённых картинок, а не
взята из палитры витрины (``THEMES``).

БАЗОВОЕ СОСТОЯНИЕ — СОБРАННЫЙ ЗНАК, И ЭТО ВАЖНЕЕ АНИМАЦИИ. ``stroke-dashoffset``
в атрибуте равен нулю, а прячет элемент только сам ``<animate>``. Там, где SMIL
не отработает — старый просмотрщик, конвертер в растр, вставка картинки в
документ, — виден готовый логотип, а не пустое место. Способ выбран не наугад:
им витрина уже анимирует ``typing-*.svg``, то есть он доказан на этой странице.

ТРЕТИЙ ИСХОД У РИСОВАЛЬЩИКА ЕСТЬ, И ЭТО НЕ ФОРМАЛЬНОСТЬ. Знак лежит в дереве
готовыми файлами, а значит его можно поправить руками — и правка потеряется при
следующем запуске, молча. ``--check`` сверяет лежащее с тем, что рисует
генератор, и называет разошедшийся файл.

Исходы: 0 — знак записан или совпадает; 1 — находка: лежащее разошлось с
генератором; 2 — проверка не отработала (файла нет, запись не удалась).
"""

from __future__ import annotations

import argparse
import math
import pathlib
import re
import sys

import checks

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

#: Четыре числа, из которых считается вся геометрия знака.
ARM = 22          #: плечо шеврона; наклонные идут под 45°
STEP = 30         #: шаг между шевронами — ритм «шаг, шаг, шаг»
GAP = 46          #: зазор до галки: больше межшевронного, иначе ряд читается зигзагом
LONG = 44         #: длинное плечо галки — вдвое против короткого
SW = 11           #: толщина знака
SW_MONO = 7       #: подпись тише знака: она про автора, а не про статус
CY = 56           #: середина по вертикали

#: Палитра снята с утверждённых картинок задачи (``assets/logo-source/``), а не
#: подобрана заново: голубой в начале ряда, мятный в конце. Светлая тема — тот
#: же ход в тёмно-тиловом, как во втором исходнике.
THEMES: dict[str, dict[str, object]] = {
    "dark": {"start": (0x40, 0xC8, 0xF8), "end": (0x58, 0xE8, 0xA8), "mono": "#8FE8D0"},
    "light": {"start": (0x0A, 0x4F, 0x5E), "end": (0x0C, 0x7F, 0x6C), "mono": "#0E6E70"},
}

#: Место знака в баннере. Между маркерами — только машинное: правка руками
#: потеряется при следующем прогоне, и потому её ловит ``--check``.
LOGO_SLOT = re.compile(r"^[ \t]*<!--logo-->.*?^[ \t]*<!--/logo-->", re.S | re.M)

#: Плашка, на которой знак стоит в баннере. Числа — от прежней карточки с
#: ``>>>``: знак занял её место, а не сдвинул композицию.
CARD = {"x": 880.5, "y": 72.5, "w": 329.0, "h": 195.0}

Point = tuple[float, float]


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> str:
    """Точка шкалы между двумя цветами: ``t`` от 0 до 1."""
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def path_len(points: list[Point]) -> float:
    """Длина ломаной — она же длина штриха для прочерчивания."""
    return sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def draw(points: list[Point]) -> str:
    """Ломаная в атрибут ``d``."""
    head, *rest = points
    return "M%g %g" % head + "".join("L%g %g" % p for p in rest)


def monogram(x0: float, color: str) -> list[dict[str, object]]:
    """A · V · M раздельными буквами: в исходнике V тонула в M и читалось «AM»."""
    top, bot, w, gap = CY - 22, CY + 22, 24, 11
    half = w / 2
    return [
        {"pts": [(x0, bot), (x0 + half, top), (x0 + w, bot)], "color": color, "sw": SW_MONO,
         "extra": [(x0 + 5, CY + 6), (x0 + w - 5, CY + 6)]},
        {"pts": [(x0 + w + gap, top), (x0 + w + gap + half, bot), (x0 + 2 * w + gap, top)],
         "color": color, "sw": SW_MONO},
        {"pts": [(x0 + 2 * (w + gap), bot), (x0 + 2 * (w + gap), top),
                 (x0 + 2 * (w + gap) + half, CY + 4), (x0 + 2 * (w + gap) + w, top),
                 (x0 + 2 * (w + gap) + w, bot)], "color": color, "sw": SW_MONO},
    ]


def strokes(theme_name: str, with_mono: bool) -> list[dict[str, object]]:
    """Элементы знака в порядке появления: три шага, проверка, подпись."""
    theme = THEMES[theme_name]
    start, end = theme["start"], theme["end"]
    items: list[dict[str, object]] = []
    for i in range(3):
        x = i * STEP
        items.append({"pts": [(x, CY - ARM), (x + ARM, CY), (x, CY + ARM)],
                      "color": mix(start, end, i / 3), "sw": SW})
    gx = 2 * STEP + GAP
    items.append({"pts": [(gx, CY - ARM), (gx + ARM, CY), (gx + ARM + LONG, CY - LONG)],
                  "color": mix(start, end, 1.0), "sw": SW})
    if with_mono:
        items += monogram(gx + ARM + LONG + 34, str(theme["mono"]))
    return items


def bbox(items: list[dict[str, object]], pad: float = 3) -> tuple[float, float, float, float]:
    """Габарит фигуры с учётом половины толщины штриха."""
    xs: list[float] = []
    ys: list[float] = []
    for item in items:
        half = float(item["sw"]) / 2
        for points in (item["pts"], item.get("extra", [])):
            for x, y in points:
                xs += [x - half, x + half]
                ys += [y - half, y + half]
    x0, y0 = min(xs) - pad, min(ys) - pad
    return x0, y0, max(xs) - x0 + pad, max(ys) - y0 + pad


def paths(items: list[dict[str, object]], dur: float, indent: str = "") -> str:
    """Штрихи знака, прочерчивающиеся по очереди слева направо."""
    lead = 0.06                                   # пауза до первого штриха
    slot = (1 - lead) / (len(items) * 0.72 + 0.28)
    out: list[str] = []
    for i, item in enumerate(items):
        start = lead + i * slot * 0.72            # следующий стартует, не дожидаясь конца
        end = min(start + slot, 1.0)
        length = round(path_len(item["pts"]) + path_len(item.get("extra", [])), 1)
        # Смещение на длину ПЛЮС толщину: иначе круглый конец штриха рисует точку
        # там, где ещё ничего не должно быть видно, — семь точек по всему знаку.
        hidden = round(length + float(item["sw"]), 1)
        shape = draw(item["pts"])
        if item.get("extra"):
            shape += " " + draw(item["extra"])
        out.append(
            f'{indent}<path d="{shape}" stroke="{item["color"]}" stroke-width="{item["sw"]}" '
            f'stroke-dasharray="{hidden} {hidden}" stroke-dashoffset="0">'
            f'<animate attributeName="stroke-dashoffset" dur="{dur}s" begin="0s" fill="freeze" '
            f'calcMode="spline" keySplines="0 0 1 1;0.25 0 0.15 1;0 0 1 1" '
            f'values="{hidden};{hidden};0;0" keyTimes="0;{start:.4f};{end:.4f};1"/></path>')
    return ("\n" if indent else "").join(out)


def build(theme_name: str, with_mono: bool, dur: float = 2.6) -> str:
    """Знак отдельным файлом: геометрия, поля по bbox, поочерёдное появление."""
    items = strokes(theme_name, with_mono)
    x0, y0, width, height = bbox(items)
    label = ("ArtVsMark — three steps, a passed check and a signature"
             if with_mono else "ArtVsMark — three steps and a passed check")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:g} {y0:g} '
            f'{width:g} {height:g}" role="img" aria-label="{label}">'
            f'<g fill="none" stroke-linecap="round" stroke-linejoin="round">'
            f'{paths(items, dur)}</g></svg>')


def build_icon(box: int = 64) -> str:
    """Квадратная иконка: тот же набор на подложке, статичная.

    Широкий знак в квадрате 16×16 не живёт — при пяти элементах на строку
    приходится по три пикселя. Здесь ряд ужат, а фигура центрируется по своему
    bbox: жёсткий ``viewBox`` срезал галку по правому краю.
    """
    theme = THEMES["dark"]
    arm, sw, step, gap, cy = 9, 6, 12, 17, box / 2
    items: list[dict[str, object]] = [
        {"pts": [(9 + i * step, cy - arm), (9 + i * step + arm, cy), (9 + i * step, cy + arm)],
         "color": mix(theme["start"], theme["end"], i / 3), "sw": sw} for i in range(3)]
    gx = 9 + 2 * step + gap
    items.append({"pts": [(gx, cy - arm), (gx + arm, cy), (gx + arm + 2 * arm, cy - 2 * arm)],
                  "color": mix(theme["start"], theme["end"], 1.0), "sw": sw})

    x0, y0, figure_w, figure_h = bbox(items, pad=0)
    scale = min(box * 0.72 / figure_w, box * 0.72 / figure_h)
    dx = (box - figure_w * scale) / 2 - x0 * scale
    dy = (box - figure_h * scale) / 2 - y0 * scale
    body = "".join(f'<path d="{draw(item["pts"])}" stroke="{item["color"]}" '
                   f'stroke-width="{sw}"/>' for item in items)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {box} {box}" role="img" '
            f'aria-label="ArtVsMark"><rect width="{box}" height="{box}" rx="{box * 0.22:g}" '
            f'fill="#0D1117"/><g fill="none" stroke-linecap="round" stroke-linejoin="round" '
            f'transform="translate({dx:.2f} {dy:.2f}) scale({scale:.4f})">{body}</g></svg>')


def banner_block(theme_name: str, dur: float = 2.6) -> str:
    """Знак на плашке баннера — без монограммы: имя рядом уже написано словами."""
    fill = "#0D1117" if theme_name == "dark" else "#FFFFFF"
    edge = "#30363D" if theme_name == "dark" else "#D0D7DE"
    items = strokes(theme_name, with_mono=False)
    x0, y0, width, height = bbox(items)
    # Знак занимает плашку, а не сидит в её середине точкой: прежняя карточка
    # держалась крупной надписью, и с мелким знаком плашка читалась пустой.
    scale = min(CARD["w"] * 0.80 / width, CARD["h"] * 0.62 / height)
    dx = CARD["x"] + (CARD["w"] - width * scale) / 2 - x0 * scale
    dy = CARD["y"] + (CARD["h"] - height * scale) / 2 - y0 * scale
    glow = "#40C8F8" if theme_name == "dark" else "#0C7F6C"
    return (
        f'  <!--logo-->\n'
        f'  <radialGradient id="logo-glow" cx="0.5" cy="0.5" r="0.5">\n'
        f'    <stop offset="0%" stop-color="{glow}" stop-opacity="0.18"/>\n'
        f'    <stop offset="100%" stop-color="{glow}" stop-opacity="0"/>\n'
        f'  </radialGradient>\n'
        f'  <g opacity="0.95">\n'
        f'    <rect x="{CARD["x"]:g}" y="{CARD["y"]:g}" width="{CARD["w"]:g}" '
        f'height="{CARD["h"]:g}" rx="14" fill="{fill}" stroke="{edge}"/>\n'
        f'    <rect x="{CARD["x"]:g}" y="{CARD["y"]:g}" width="{CARD["w"]:g}" '
        f'height="{CARD["h"]:g}" rx="14" fill="url(#logo-glow)"/>\n'
        f'    <g fill="none" stroke-linecap="round" stroke-linejoin="round" '
        f'transform="translate({dx:.2f} {dy:.2f}) scale({scale:.4f})">\n'
        f'{paths(items, dur, indent="      ")}\n'
        f'    </g>\n'
        f'  </g>\n'
        f'  <!--/logo-->')


def rendered() -> dict[str, str]:
    """Что генератор рисует сейчас: путь до файла — его содержимое целиком."""
    out: dict[str, str] = {}
    for theme in THEMES:
        for with_mono, suffix in ((True, ""), (False, "-mark")):
            out[f"assets/logo{suffix}-{theme}.svg"] = build(theme, with_mono)
    out["assets/logo-icon.svg"] = build_icon()
    for theme in THEMES:
        name = f"assets/header-{theme}.svg"
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if LOGO_SLOT.search(text):
            # Замена ФУНКЦИЕЙ, а не строкой: в строке площадка разобрала бы
            # обратные слэши и группы как ссылки на совпадение.
            out[name] = LOGO_SLOT.sub(lambda _m, t=theme: banner_block(t), text)
    return out


def differing(current: dict[str, str]) -> list[str]:
    """Файлы, чьё содержимое разошлось с тем, что рисует генератор."""
    found = []
    for name, body in sorted(current.items()):
        path = ROOT / name
        if not path.exists():
            found.append(f"{name}: знака нет в дереве, а витрина на него ссылается")
        elif path.read_text(encoding="utf-8") != body:
            found.append(f"{name}: правлен помимо генератора — правка потеряется "
                         f"при следующем запуске build_logo.py")
    return found


def selftest() -> int:
    """Прогоняет через генератор то, что он обязан отвергнуть и обязан пропустить."""
    broken: list[str] = []

    # Разошедшийся файл обязан быть НАЗВАН, а совпадающий — пропущен. Оба случая
    # проверяются одним механизмом, которым пользуется `--check` (правило 150).
    sample = {"assets/logo-icon.svg": build_icon()}
    if differing(sample):
        broken.append("совпадающий файл назван разошедшимся")
    if not differing({"assets/logo-icon.svg": build_icon() + "<!-- правка руками -->"}):
        broken.append("правка помимо генератора не поймана")
    if not differing({"assets/logo-of-nowhere.svg": ""}):
        broken.append("отсутствующий файл не пойман")

    # Знак без анимации обязан быть ВИДЕН: смещение живёт в `<animate>`, а не в
    # атрибуте. Иначе просмотрщик без SMIL покажет пустое место.
    svg = build("dark", with_mono=True)
    if 'stroke-dashoffset="0"' not in svg:
        broken.append("базовое состояние прячет знак: без SMIL будет пусто")
    if svg.count("<animate") != len(strokes("dark", with_mono=True)):
        broken.append("не у каждого штриха своё появление")

    # Галка читается только когда её длинное плечо длиннее короткого, а сама она
    # отставлена дальше, чем идут шевроны: иначе ряд читается зигзагом.
    if LONG <= ARM or GAP <= STEP:
        broken.append(f"геометрия вернулась к зигзагу: GAP={GAP} STEP={STEP} "
                      f"LONG={LONG} ARM={ARM}")

    if broken:
        print(checks.annotate("error", "самопроверка провалена"), file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: разошедшееся названо, знак виден и без анимации")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="не писать, а назвать разошедшееся с генератором")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    try:
        current = rendered()
    except OSError as err:
        print(checks.annotate("error", f"знак не собран: {err}"), file=sys.stderr)
        return 2

    if args.check:
        found = differing(current)
        if found:
            print(checks.annotate("error", "знак в дереве разошёлся с генератором"),
                  file=sys.stderr)
            for line in found:
                print(f"  • {line}", file=sys.stderr)
            print("  Правят генератор и перерисовывают, а не файл: следующий "
                  "запуск перезапишет ручную правку молча.", file=sys.stderr)
            return 1
        print(f"знак совпадает с генератором: {len(current)} файлов")
        return 0

    try:
        for name, body in sorted(current.items()):
            (ROOT / name).write_text(body, encoding="utf-8")
    except OSError as err:
        print(checks.annotate("error", f"знак не записан: {err}"), file=sys.stderr)
        return 2
    print("записано:", " · ".join(sorted(current)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
