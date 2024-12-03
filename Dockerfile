FROM python:3.12-slim

# 作業ディレクトリを設定
WORKDIR /virtual_light_entity_for_IR

# 依存関係をコピーしてインストール
COPY requirements.txt /virtual_light_entity_for_IR/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのソースコードをコピー
COPY . /virtual_light_entity_for_IR

# Pythonスクリプトを実行
CMD ["python", "virtual_light_entity_for_IR/main.py"]
