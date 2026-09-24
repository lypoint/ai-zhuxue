FROM python:3.12-slim
WORKDIR /srv
# build context 为仓库根（docker-compose 统一），路径前缀 server/
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/app ./app
COPY server/tools ./tools
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
