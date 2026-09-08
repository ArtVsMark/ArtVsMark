#!/usr/bin/env python3
"""Ставит фирменный знак владельца в баннер витрины.

Знак — не наш рисунок, а утверждённые картинки владельца из
``assets/logo-source/``. Скрипт делает с ними ровно две вещи: снимает
запечённый фон (``--clean``) и впечатывает готовое в баннер между маркерами
``<!--logo-->`` в ``assets/header-*.svg``.

ПОЧЕМУ ФОН ПРИШЛОСЬ СНИМАТЬ. Исходники — RGB без альфа-канала: «прозрачный
фон» в них НАРИСОВАН шахматкой прямо в пикселях. На тёмной теме README такая
картинка — белый клетчатый прямоугольник, а не логотип. Прозрачность
восстанавливается по насыщенности: штрих цветной, фон серый, и альфа растёт
плавно, иначе края штриха стали бы рваными.

ЗНАК ЗАНЯЛ МЕСТО КАРТОЧКИ ``>>>``. Она несла тот же мотив — три шеврона
приглашения Python, — и страница показывала его дважды.

ПОЯВЛЕНИЕ СЛЕВА НАПРАВО — ЧАСТЬ ЗАМЫСЛА. Знак читается как последовательность:
шаг, шаг, шаг, пройденная проверка, подпись. Раскрывающий прямоугольник
(``clipPath`` с анимируемой шириной) показывает её в том же порядке. Способ не
выбирался заново: им же витрина ведёт ``typing-*.svg``.

БАЗОВОЕ СОСТОЯНИЕ — ЗНАК ЦЕЛИКОМ, И ЭТО ВАЖНЕЕ АНИМАЦИИ. Ширина клипа в
атрибуте равна полной, сужает её только сам ``<animate>``. Где SMIL не
отработает — конвертер в растр, старый просмотрщик, — виден весь знак, а не
пустая плашка. Первая редакция держала в атрибуте ноль и при невалидном
``keyTimes`` (последнее значение не 1) показывала пустоту в обоих случаях:
площадка молча выбрасывает всю анимацию, а базовым значением остаётся ноль.

ЗАВИСИМОСТЬ ОТ PILLOW ЖИВЁТ ТОЛЬКО В ``--clean``. Конвейеру он не нужен:
очищенные картинки лежат в дереве готовыми, а встраивание и сверка читают
размер прямо из заголовка PNG. Требовать Pillow в прогоне значило бы ставить
зависимость ради операции, которая делается раз в жизни знака.

Запуск::

    python scripts/build_logo.py --clean   # пересобрать из исходников (нужен Pillow)
    python scripts/build_logo.py           # впечатать в баннер
    python scripts/build_logo.py --check   # то же, что проверит конвейер
    python scripts/build_logo.py --selftest

Исходы: 0 — баннер собран или совпадает; 1 — находка: баннер разошёлся со
знаком; 2 — проверка не отработала (файла нет, запись не удалась).
"""

from __future__ import annotations

import argparse
import base64
import pathlib
import re
import struct
import sys

import checks

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

#: Знак в двух темах: тёмная и светлая версии — обе от владельца.
LOGOS = {"dark": "logo-dark.png", "light": "logo-light.png"}

#: Исходники концепта. Их не правят: это утверждённые картинки владельца.
SOURCES = {"dark": "logo-source/concept-main.png", "light": "logo-source/concept-light.png"}

#: Место знака в баннере. Между маркерами — только машинное: правка руками
#: потеряется при следующем прогоне, и потому её ловит ``--check``.
LOGO_SLOT = re.compile(r"^[ \t]*<!--logo-->.*?^[ \t]*<!--/logo-->", re.S | re.M)

#: Плашка, на которой знак стоит. Числа — от прежней карточки с ``>>>``: знак
#: занял её место, а не сдвинул композицию.
CARD = {"x": 880.5, "y": 72.5, "w": 329.0, "h": 195.0}

#: Доля плашки под знак. Меньше — плашка читается пустой, больше — знак
#: упирается в рамку.
FIT_W, FIT_H = 0.90, 0.74

#: Порог насыщенности, ниже которого пиксель считается фоном, и ширина
#: перехода. Замер на исходниках: шахматка даёт 0–8, штрих — 60 и выше.
BACKGROUND_SATURATION = 12
EDGE_SOFTNESS = 40

#: Сколько времени идёт раскрытие и когда оно начинается. Пауза в начале —
#: чтобы появление было заметно, а не случилось до первого кадра; хвост после
#: раскрытия — чтобы собранный знак постоял, а не сменился следующим циклом.
#: Появление НАРОЧНО медленное: знак читается как последовательность шагов, и
#: на быстром раскрытии порядок не успевает прочитаться.
DURATION = 3.4
LEAD, DONE = 0.06, 0.86


def png_size(data: bytes) -> tuple[int, int]:
    """Размер PNG из заголовка: Pillow ради двух чисел в прогон не тащат."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("это не PNG")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def banner_block(theme: str, image: bytes) -> str:
    """Знак на плашке баннера, раскрывающийся слева направо."""
    iw, ih = png_size(image)
    scale = min(CARD["w"] * FIT_W / iw, CARD["h"] * FIT_H / ih)
    width, height = iw * scale, ih * scale
    x = CARD["x"] + (CARD["w"] - width) / 2
    y = CARD["y"] + (CARD["h"] - height) / 2
    fill = "#0D1117" if theme == "dark" else "#FFFFFF"
    edge = "#30363D" if theme == "dark" else "#D0D7DE"
    data = base64.b64encode(image).decode()
    return (
        f'  <!--logo-->\n'
        f'  <clipPath id="logo-reveal">\n'
        f'    <rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}">\n'
        f'      <animate attributeName="width" values="0;0;{width:.1f};{width:.1f}" '
        f'keyTimes="0;{LEAD};{DONE};1" dur="{DURATION}s" begin="0s" fill="freeze" '
        f'calcMode="spline" keySplines="0 0 1 1;0.35 0 0.4 1;0 0 1 1"/>\n'
        f'    </rect>\n'
        f'  </clipPath>\n'
        f'  <g opacity="0.97">\n'
        f'    <rect x="{CARD["x"]:g}" y="{CARD["y"]:g}" width="{CARD["w"]:g}" '
        f'height="{CARD["h"]:g}" rx="14" fill="{fill}" stroke="{edge}"/>\n'
        f'    <image x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
        f'clip-path="url(#logo-reveal)" preserveAspectRatio="xMidYMid meet" '
        f'href="data:image/png;base64,{data}"/>\n'
        f'  </g>\n'
        f'  <!--/logo-->')


def rendered() -> tuple[dict[str, str], list[str]]:
    """Баннеры со знаком внутри и список того, чего не хватило."""
    out: dict[str, str] = {}
    missing: list[str] = []
    for theme, name in LOGOS.items():
        logo = ASSETS / name
        header = ASSETS / f"header-{theme}.svg"
        if not logo.exists():
            missing.append(f"assets/{name}: знака нет — баннеру нечего показывать")
            continue
        if not header.exists():
            missing.append(f"assets/header-{theme}.svg: баннера нет")
            continue
        text = header.read_text(encoding="utf-8")
        if not LOGO_SLOT.search(text):
            missing.append(f"assets/header-{theme}.svg: маркеров <!--logo--> нет — "
                           f"знак вставить некуда")
            continue
        # Замена ФУНКЦИЕЙ, а не строкой: в строке площадка разобрала бы
        # обратные слэши и группы как ссылки на совпадение.
        block = banner_block(theme, logo.read_bytes())
        out[f"assets/header-{theme}.svg"] = LOGO_SLOT.sub(lambda _m: block, text)
    return out, missing


def differing(current: dict[str, str]) -> list[str]:
    """Баннеры, чьё содержимое разошлось с тем, что собирает скрипт."""
    found = []
    for name, body in sorted(current.items()):
        path = ROOT / name
        if not path.exists():
            found.append(f"{name}: файла нет")
        elif path.read_text(encoding="utf-8") != body:
            found.append(f"{name}: правлен помимо скрипта — правка потеряется "
                         f"при следующем запуске build_logo.py")
    return found


def clean(source: pathlib.Path, target: pathlib.Path, width: int = 560) -> tuple[int, int]:
    """Снимает запечённую шахматку, обрезает поля, ужимает до ``width``.

    Запускается руками при смене знака. Pillow нужен только здесь — в прогоне
    очищенные картинки уже лежат готовыми.
    """
    from PIL import Image                                   # noqa: PLC0415

    image = Image.open(source).convert("RGB")
    pixels = image.load()
    result = Image.new("RGBA", image.size)
    out = result.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b = pixels[x, y]
            saturation = max(r, g, b) - min(r, g, b)
            if saturation <= BACKGROUND_SATURATION:
                continue
            # Альфа растёт плавно: резкий порог оставил бы рваные края.
            alpha = min(255, int((saturation - BACKGROUND_SATURATION) * 255 / EDGE_SOFTNESS))
            out[x, y] = (r, g, b, alpha)
    box = result.getbbox()
    if box is None:
        raise ValueError(f"{source.name}: после снятия фона не осталось ничего")
    result = result.crop(box)
    result.thumbnail((width, width), Image.LANCZOS)
    result.save(target, optimize=True)
    return result.size


def selftest() -> int:
    """Прогоняет через сборку то, что она обязана отвергнуть и обязана пропустить."""
    broken: list[str] = []

    current, missing = rendered()
    if missing:
        broken.append(f"знак не собрался на живом дереве: {'; '.join(missing)}")
    if differing(current):
        broken.append("совпадающий баннер назван разошедшимся")
    if not differing({name: body + "<!-- правка руками -->"
                      for name, body in current.items()}):
        broken.append("правка помимо скрипта не поймана")
    if not differing({"assets/header-of-nowhere.svg": ""}):
        broken.append("отсутствующий файл не пойман")

    # Знак обязан быть виден и БЕЗ анимации: ширину клипа сужает только
    # `<animate>`, а в атрибуте она полная. Обратное давало пустую плашку.
    for name, body in current.items():
        block = LOGO_SLOT.search(body)
        head = block.group(0) if block else ""
        if 'width="0"' in head.split("<animate")[0]:
            broken.append(f"{name}: базовая ширина клипа нулевая — без SMIL плашка пуста")
        if not head.rstrip().endswith("<!--/logo-->") or "<image" not in head:
            broken.append(f"{name}: знак в баннер не попал")
        # keyTimes обязан доходить до 1: иначе площадка выбрасывает анимацию
        # целиком, и остаётся только базовое значение.
        for times in re.findall(r'keyTimes="([^"]+)"', head):
            if not times.split(";")[-1] == "1":
                broken.append(f"{name}: keyTimes не доходит до 1 — анимация будет отброшена")

    # Размер читается из заголовка, а не Pillow: прогон не должен тащить его.
    try:
        if png_size((ASSETS / LOGOS["dark"]).read_bytes())[0] <= 0:
            broken.append("размер знака прочитан неверно")
    except (OSError, ValueError) as err:
        broken.append(f"заголовок PNG не разобран: {err}")

    if broken:
        print(checks.annotate("error", "самопроверка провалена"), file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("самопроверка пройдена: разошедшееся названо, знак виден и без анимации")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--clean", action="store_true",
                        help="пересобрать знак из исходников концепта (нужен Pillow)")
    parser.add_argument("--check", action="store_true",
                        help="не писать, а назвать разошедшееся со знаком")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    if args.clean:
        try:
            for theme, source in SOURCES.items():
                size = clean(ASSETS / source, ASSETS / LOGOS[theme])
                print(f"{LOGOS[theme]}: {size[0]}×{size[1]}")
        except (OSError, ValueError) as err:
            print(checks.annotate("error", f"знак не очищен: {err}"), file=sys.stderr)
            return 2
        except ImportError:
            print(checks.annotate("error", "для --clean нужен Pillow: pip install pillow"),
                  file=sys.stderr)
            return 2

    try:
        current, missing = rendered()
    except (OSError, ValueError) as err:
        print(checks.annotate("error", f"баннер не собран: {err}"), file=sys.stderr)
        return 2
    if missing:
        print(checks.annotate("error", "знак в баннер не поставить"), file=sys.stderr)
        for line in missing:
            print(f"  • {line}", file=sys.stderr)
        return 2

    if args.check:
        found = differing(current)
        if found:
            print(checks.annotate("error", "баннер разошёлся со знаком"), file=sys.stderr)
            for line in found:
                print(f"  • {line}", file=sys.stderr)
            print("  Правят знак и пересобирают баннер, а не баннер: следующий "
                  "запуск перезапишет ручную правку молча.", file=sys.stderr)
            return 1
        print(f"баннер совпадает со знаком: {len(current)} файлов")
        return 0

    try:
        for name, body in sorted(current.items()):
            (ROOT / name).write_text(body, encoding="utf-8")
    except OSError as err:
        print(checks.annotate("error", f"баннер не записан: {err}"), file=sys.stderr)
        return 2
    print("собрано:", " · ".join(sorted(current)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
