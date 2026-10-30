FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY engine /app/engine
COPY networking /app/networking
COPY server /app/server
RUN useradd --create-home --uid 10001 surakarta
USER surakarta
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8765
EXPOSE 8765
CMD ["python", "-m", "server"]
