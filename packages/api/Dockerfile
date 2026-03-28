FROM python:3.12-slim
WORKDIR /app
COPY packages/common /app/packages/common
COPY packages/api /app/packages/api
RUN pip install uv && uv pip install --system -e packages/common -e packages/api
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
