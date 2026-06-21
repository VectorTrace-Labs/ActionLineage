FROM python:3.13-slim

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir ".[service]"

ENTRYPOINT ["actionlineage"]
