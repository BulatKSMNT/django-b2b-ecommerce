FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /service

COPY requirements.txt /service/requirements.txt

RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app /service/app

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
