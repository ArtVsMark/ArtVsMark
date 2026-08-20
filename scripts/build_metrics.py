#!/usr/bin/env python3
"""Собирает метрики витрины из живых источников и рисует assets/metrics-*.svg.

Числа на странице профиля устаревают молча: релиз v1.11.0 вышел через четыре
часа после того, как в README было вписано «11 releases shipped». Поэтому они
не вписываются руками, а измеряются — раз в сутки, из репозитория, который их
и порождает.

Что откуда берётся:

* число тестов — подсчётом ``def test_`` в клоне грейдера (грубее, чем
  ``pytest --collect-only``, зато без установки зависимостей; на витрине всё
  равно показывается порядок «4000+», а не точное число);
* проверок на PR — сколько check-runs создано на последнем смерженном PR;
* релизов — длина списка релизов;
* пустой список обходов защиты ветки — статика: ruleset читается только с
  правами admin, которых у ``GITHUB_TOKEN`` нет. За этой цифрой следит гейт в
  самом грейдере, а не витрина.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.request

REPO = "ArtVsMark/Stepik-Python-Grader"
API = "https://api.github.com"
ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT = "Inter,Segoe UI,Helvetica,Arial,sans-serif"


def _api(path: str) -> object:
    request = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {t}"} if (t := os.environ.get("GH_TOKEN")) else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def count_tests(grader_dir: pathlib.Path) -> int:
    """Число тест-функций в клоне грейдера."""
    total = 0
    for path in (grader_dir / "tests").rglob("*.py"):
        total += len(re.findall(r"^\s*def test_", path.read_text(encoding="utf-8"), re.M))
    return total


def checks_per_pr() -> int:
    """Сколько проверок создаётся на PR — по последнему смерженному."""
    for pull in _api(f"/repos/{REPO}/pulls?state=closed&per_page=20"):
        if not pull.get("merged_at"):
            continue
        runs = _api(f"/repos/{REPO}/commits/{pull['head']['sha']}/check-runs?per_page=100")
        if runs["total_count"]:
            return int(runs["total_count"])
    return 0


def release_count() -> int:
    return len(_api(f"/repos/{REPO}/releases?per_page=100"))


def render(tiles: list[tuple[str, str, bool]], dark: bool) -> str:
    width, height, gap = 1000, 118, 18
    tile_w = (width - gap * (len(tiles) - 1)) // len(tiles)
    if dark:
        card, stroke, num, lab, accent = "#0D1117", "#30363D", "#F0F6FC", "#7D8590", "#D29922"
        hot_num = "#E3B341"
    else:
        card, stroke, num, lab, accent = "#FFFFFF", "#D0D7DE", "#1F2328", "#636C76", "#9A6700"
        hot_num = "#9A6700"

    label = ", ".join(f"{value} {name}" for value, name, _ in tiles)
    out = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{label}">',
        '<defs><linearGradient id="a" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%" stop-color="#58A6FF"/><stop offset="100%" stop-color="#7EE787"/>'
        "</linearGradient></defs>",
    ]
    for index, (value, name, hot) in enumerate(tiles):
        x = index * (tile_w + gap)
        font_size = 46 if len(value) <= 3 else 40
        out.append(
            f"  <g>\n"
            f'    <rect x="{x + 0.5}" y="0.5" width="{tile_w - 1}" height="{height - 1}" '
            f'rx="14" fill="{card}" stroke="{stroke}"/>\n'
            f'    <rect x="{x + 22}" y="22" width="44" height="4" rx="2" '
            f'fill="{accent if hot else "url(#a)"}"/>\n'
            f'    <text x="{x + tile_w / 2:.0f}" y="73" fill="{hot_num if hot else num}" '
            f'font-family="{FONT}" font-size="{font_size}" font-weight="800" '
            f'text-anchor="middle" letter-spacing="-1">{value}</text>\n'
            f'    <text x="{x + tile_w / 2:.0f}" y="98" fill="{lab}" font-family="{FONT}" '
            f'font-size="15.5" font-weight="600" text-anchor="middle">{name}</text>\n'
            f"  </g>"
        )
    return "\n".join(out) + "\n</svg>\n"


def patch_readme(releases: int, tests: int, checks: int) -> None:
    """Обновляет числа между маркерами <!--m:key--> … <!--/m:key-->."""
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    for key, value in (("releases", releases), ("tests", f"{tests // 1000}000+"), ("checks", checks)):
        text = re.sub(
            rf"(<!--m:{key}-->).*?(<!--/m:{key}-->)",
            rf"\g<1>{value}\g<2>",
            text,
            flags=re.S,
        )
    readme.write_text(text, encoding="utf-8")


def main() -> int:
    grader = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "grader")
    if not (grader / "tests").is_dir():
        print(f"нет клона грейдера в {grader}/ — ожидается каталог tests/", file=sys.stderr)
        return 1

    tests = count_tests(grader)
    checks = checks_per_pr()
    releases = release_count()
    print(f"тестов: {tests} · проверок на PR: {checks} · релизов: {releases}")

    if not tests or not checks:
        print("метрика не собралась — SVG не переписываю", file=sys.stderr)
        return 1

    tiles = [(f"{tests // 1000}000+", "tests", False), (str(checks), "checks per PR", False),
             ("empty", "bypass list", True)]
    for theme, dark in (("dark", True), ("light", False)):
        (ROOT / f"assets/metrics-{theme}.svg").write_text(render(tiles, dark), encoding="utf-8")
    patch_readme(releases, tests, checks)
    print("assets/metrics-*.svg и README обновлены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
