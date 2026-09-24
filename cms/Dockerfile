FROM python:3.12-slim
WORKDIR /srv
COPY cms/requirements.txt ./cms/requirements.txt
RUN pip install --no-cache-dir -r cms/requirements.txt
COPY cms/ ./cms/
EXPOSE 8101
# CMS_API_BASE 指向后端 API（docker 网络内用服务名，如 http://api:8000）
ENV CMS_API_BASE=http://api:8000
CMD ["uvicorn", "cms.main:app", "--host", "0.0.0.0", "--port", "8101"]
