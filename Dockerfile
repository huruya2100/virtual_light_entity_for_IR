FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_SYSTEM_PYTHON=1

# 作業ディレクトリを設定
WORKDIR /virtual_light_entity_for_IR

# 依存関係をコピーしてインストール
COPY pyproject.toml uv.lock /virtual_light_entity_for_IR/
RUN uv sync --no-dev --no-install-project --frozen

# アプリケーションのソースコードをコピー
COPY . /virtual_light_entity_for_IR
RUN uv sync --no-dev --frozen

# Pythonスクリプトを実行
CMD ["/virtual_light_entity_for_IR/.venv/bin/python", "virtual_light_entity_for_IR/main.py"]
