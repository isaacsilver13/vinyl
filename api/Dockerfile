# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

COPY vinyl_api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY vinyl_api ./vinyl_api
COPY tests ./tests

ENV VINYL_API_DATABASE_URL=sqlite:////data/vinyl_api.db
EXPOSE 8000

CMD ["uvicorn", "vinyl_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
