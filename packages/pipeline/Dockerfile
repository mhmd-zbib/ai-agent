FROM python:3.12-slim
WORKDIR /app
COPY packages/common /app/packages/common
COPY packages/pipeline /app/packages/pipeline
RUN pip install uv && uv pip install --system -e packages/common -e packages/pipeline
CMD ["python", "-m", "pipeline.main"]
