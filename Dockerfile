FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 作業ディレクトリを設定
WORKDIR /virtual_light_entity_for_IR

# 依存関係をコピーしてインストール
COPY pyproject.toml /virtual_light_entity_for_IR/
RUN uv sync --no-dev

# アプリケーションのソースコードをコピー
COPY . /virtual_light_entity_for_IR

# Pythonスクリプトを実行
CMD ["uv", "run", "python", "virtual_light_entity_for_IR/main.py"]
