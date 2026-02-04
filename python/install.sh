if ! command -v uv > /dev/null 2>&1; then
  echo "» Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

uv self update

if ! command -v ruff > /dev/null 2>&1; then
  echo "» Installing ruff"
  uv tool install ruff@latest
fi

uv tool upgrade ruff

if ! command -v ty > /dev/null 2>&1; then
  echo "» Installing ty"
  uv tool install ty@latest
fi

uv tool upgrade ty