#!/bin/bash
# Окно исполняет код на планке, а не на системном python3 образа (217, #269).
#
# ЗАЧЕМ. Планка витрины — requires-python в pyproject.toml, и код написан на
# ней: `except A, B:` без скобок (PEP 758) системный python3 облачного окна
# (3.11) не разбирает вовсе. Свод велит гнать гейты перед пушем — без этого
# хука первый же `python scripts/build_metrics.py --check` в новом окне упал бы
# SyntaxError, а «починить» его вниз значило бы молча вернуть 3.12.
#
# ЧТО ДЕЛАЕТ. Читает планку, ставит её интерпретатор через uv в окружение
# вне дерева, кладёт туда ruff той же версии, что у гейта стиля каталога, и
# ставит окружение первым в PATH окна. Число нигде не вписано: поднимется
# планка — хук поставит новую сам (005).
#
# ИСХОД ГОВОРИТ ОДНА СТРОКА в stdout — её площадка кладёт в контекст окна.
# Отказ не роняет старт: окно без планки должно узнать об этом, а не не
# открыться (051).
set -uo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
ENV_DIR="$HOME/.venvs/artvsmark-floor"
# ruff закреплён тем же числом, что в pr-check.yml и requirements-test.txt
# каталога: новый ruff приносит новые правила UP, и гейт краснел бы по-разному.
RUFF="ruff==0.15.20"

floor=$(sed -n 's/^requires-python *= *"[^0-9]*\([0-9]*\.[0-9]*\).*/\1/p' "$ROOT/pyproject.toml" 2>/dev/null | head -1)
if [ -z "$floor" ]; then
  echo "окно НЕ на планке: в pyproject.toml не найден requires-python — гейты гнать нечем"
  exit 0
fi

# uv свежий из pip: старый не знает стабильных выпусков новой версии и ставит
# кандидата (замер 8 октября: uv 0.8.17 давал 3.14.0rc2 вместо 3.14.8).
python3 -m pip install --quiet --disable-pip-version-check --user --upgrade uv >/dev/null 2>&1 \
  || python3 -m pip install --quiet --disable-pip-version-check --upgrade uv >/dev/null 2>&1
UV="python3 -m uv"

if ! $UV python install "$floor" >/dev/null 2>&1; then
  echo "окно НЕ на планке $floor: uv не поставил интерпретатор — python3 остаётся системным $(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])'), гейты на нём не разберут код"
  exit 0
fi
if [ ! -x "$ENV_DIR/bin/python" ] || ! "$ENV_DIR/bin/python" -c "import sys;sys.exit(sys.version_info[:2]!=tuple(map(int,'$floor'.split('.'))))" 2>/dev/null; then
  rm -rf "$ENV_DIR"
  $UV venv --quiet --python "$floor" "$ENV_DIR" >/dev/null 2>&1
fi
$UV pip install --quiet --python "$ENV_DIR/bin/python" "$RUFF" >/dev/null 2>&1 || true

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$ENV_DIR/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

got=$("$ENV_DIR/bin/python" -c 'import sys;print("%d.%d.%d"%sys.version_info[:3])' 2>/dev/null)
if [ -x "$ENV_DIR/bin/ruff" ]; then ruff_state="ruff есть"; else ruff_state="ruff НЕ поставлен — гейт стиля откажет"; fi
echo "окно на планке $floor: python и python3 — $got из $ENV_DIR, $ruff_state"
