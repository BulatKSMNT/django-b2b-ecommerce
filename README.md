# B2B E-Commerce & Analytics Platform

![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)
![Django](https://img.shields.io/badge/Django-6.x-092E20?style=for-the-badge&logo=django)
![DRF](https://img.shields.io/badge/DRF-REST_API-red?style=for-the-badge)
![FastAPI](https://img.shields.io/badge/FastAPI-Scoring_Service-009688?style=for-the-badge&logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-316192?style=for-the-badge&logo=postgresql)
![Docker](https://img.shields.io/badge/Docker_Compose-2496ED?style=for-the-badge&logo=docker)
![Tests](https://img.shields.io/badge/Tests-Django_17%20%7C%20FastAPI_4-brightgreen?style=for-the-badge)

![CI](https://img.shields.io/github/actions/workflow/status/BulatKSMNT/django-b2b-ecommerce/ci.yml?branch=main&style=for-the-badge&logo=github&label=CI%20Pipeline)
   

## О проекте

**B2B E-Commerce & Analytics Platform** — backend-проект для B2B e-commerce сценария.

Проект объединяет:

- Django-приложение;
- каталог товаров;
- корзину и избранное;
- систему заявок;
- server-side tracking;
- внутреннюю аналитику;
- rule-based lead scoring;
- Django REST API;
- отдельный FastAPI-сервис для скоринга;
- PostgreSQL;
- Docker Compose;
- автоматические тесты.

Проект разработан как портфолио-проект для демонстрации практических backend-навыков:

- Python;
- Django;
- Django REST Framework;
- FastAPI;
- REST API;
- PostgreSQL;
- Docker Compose;
- unit/API tests;
- OpenAPI/Swagger.

---

## Основные возможности

### Каталог и e-commerce логика

- Каталог товаров с категориями.
- Гибкие характеристики товаров.
- Изображения товаров.
- Активные и неактивные товары/категории.
- Поиск и фильтрация товаров.
- Корзина и избранное.
- Поддержка гостевой корзины через сессии.
- Снимок товара и цены на момент создания заявки.
- Генерация slug для категорий и товаров.
- Оптимизация запросов через `select_related` и `prefetch_related`.

### Заявки

- Контактные заявки.
- Заявки с карточки товара.
- Заявки из корзины.
- Позиции заявки с сохранением снимка товара.
- Источник заявки.
- Статусы заявок.
- UTM-метки.
- Комментарии клиента.
- Комментарии менеджера.
- Поля обработки заявки.

### Аналитика и tracking

- Server-side tracking через middleware.
- UUID посетителя в cookie.
- Посещения страниц.
- Пользовательские события.
- История просмотров товаров.
- События создания заявок.
- Дневные метрики страниц и товаров.
- Аналитический dashboard в Django Admin.

### Lead Scoring

В проекте реализован rule-based lead scoring — эвристическая система оценки качества заявки.

Скор рассчитывается от `0` до `100` на основе следующих факторов:

- источник заявки;
- наличие товаров в заявке;
- количество позиций;
- общее количество товаров;
- сумма заявки;
- наличие корпоративного email;
- длина комментария;
- активность пользователя;
- просмотры товаров;
- добавления в корзину;
- добавления в избранное;
- повторные обращения;
- UTM-метки.

Приоритет заявки:

- `low`;
- `medium`;
- `high`.

Результат скоринга сохраняется в модели `LeadScore`:

- score;
- priority;
- model name;
- model version;
- features;
- explanation;
- predicted_at.

### REST API

Проект предоставляет Django REST Framework API для:

- категорий;
- товаров;
- заявок;
- скоринга заявок.

Документация API доступна через Swagger/OpenAPI.

### FastAPI Lead Scoring Service

В репозитории также есть отдельный FastAPI-сервис:

```text
services/lead_scoring_api/
```

Он реализует независимый REST endpoint для rule-based скоринга лидов.

Сервис демонстрирует:

- FastAPI;
- Pydantic-схемы;
- async endpoints;
- валидацию входных данных;
- pytest-тесты;
- Docker-упаковку отдельного сервиса.

---

## Технологический стек

### Backend

- Python 3.12
- Django 6.x
- Django REST Framework
- drf-spectacular
- django-filter
- FastAPI
- Pydantic
- Uvicorn

### База данных

- PostgreSQL 17
- SQLite fallback для локального запуска без PostgreSQL

### Frontend / Admin

- Django Templates
- HTML
- Tailwind CSS
- Vanilla JavaScript
- Chart.js
- Django Unfold Admin Theme

### Инфраструктура

- Docker
- Docker Compose
- PostgreSQL container
- FastAPI service container

### Тестирование

- Django TestCase
- DRF APIClient
- pytest
- FastAPI TestClient

---

## Структура проекта

```text
.
├── apps/
│   ├── accounts/              # пользователи, профили, активный профиль
│   ├── analytics/             # метрики, скоринг, аналитический dashboard
│   │   └── api/               # сериализаторы скоринга
│   ├── api/                   # общий DRF API router
│   ├── catalog/               # категории, товары, атрибуты
│   │   └── api/               # API каталога
│   ├── leads/                 # формы, модели и сервисы заявок
│   │   └── api/               # Lead API и scoring endpoints
│   ├── pages/                 # базовые страницы
│   ├── shop/                  # корзина и избранное
│   └── tracking/              # visitor tracking, page visits, user events
│
├── config/                    # настройки Django, urls, ASGI/WSGI
├── services/
│   └── lead_scoring_api/      # отдельный FastAPI scoring service
│       ├── app/
│       │   ├── main.py
│       │   ├── schemas.py
│       │   └── scoring.py
│       ├── tests/
│       ├── Dockerfile
│       └── requirements.txt
│
├── templates/
├── static/
├── media/
├── Dockerfile
├── compose.yaml
├── requirements.txt
├── .env.docker.example
├── .env.local.example
└── README.md
```

---

## Архитектура

Основное Django-приложение:

```text
Client / Browser / API Client
        |
        | HTTP
        v
Django Application
        |
        | HTML pages
        | Django Admin
        | DRF API
        v
PostgreSQL
```

Отдельный FastAPI scoring service:

```text
API Client
        |
        | POST /api/v1/score
        v
FastAPI Lead Scoring Service
        |
        v
Rule-based scoring response
```

Текущее состояние архитектуры:

- Django использует внутренний rule-based scoring.
- FastAPI-сервис работает как отдельный scoring service.
- В дальнейшем можно добавить режим, при котором Django будет отправлять признаки лида во FastAPI-сервис по HTTP.

---

## Переменные окружения

Проект использует отдельные env-файлы для Docker и локальной разработки.

### Docker environment

Создать файл:

```bash
cp .env.docker.example .env.docker
```

Пример:

```env
DJANGO_SECRET_KEY=change_me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
DJANGO_SETTINGS_MODULE=config.settings.dev

DB_ENGINE=postgres
POSTGRES_DB=django_b2b
POSTGRES_USER=django_b2b
POSTGRES_PASSWORD=change_me
POSTGRES_HOST=db
POSTGRES_PORT=5432
```

### Local environment

Создать файл:

```bash
cp .env.local.example .env.local
```

Пример:

```env
DJANGO_SECRET_KEY=change_me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_SETTINGS_MODULE=config.settings.dev

DB_ENGINE=postgres
POSTGRES_DB=django_b2b
POSTGRES_USER=django_b2b
POSTGRES_PASSWORD=change_me
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5433
```

## Быстрый запуск через Docker Compose

Docker Compose поднимает:

- Django web app;
- PostgreSQL;
- FastAPI scoring service.

### 1. Клонировать репозиторий

```bash
git clone https://github.com/BulatKSMNT/django-b2b-ecommerce.git
cd django-b2b-ecommerce
```

### 2. Создать env-файл для Docker

```bash
cp .env.docker.example .env.docker
```

Для локальной разработки можно оставить значения по умолчанию.

### 3. Собрать и запустить сервисы

```bash
docker compose up --build -d
```

### 4. Применить миграции

```bash
docker compose exec web python manage.py migrate
```

### 5. Создать superuser

```bash
docker compose exec web python manage.py createsuperuser
```

### 6. Открыть сервисы

Django-приложение:

```text
http://127.0.0.1:8000
```

Django Admin:

```text
http://127.0.0.1:8000/admin/
```

Swagger-документация Django API:

```text
http://127.0.0.1:8000/api/docs/
```

FastAPI Swagger:

```text
http://127.0.0.1:8001/docs
```

FastAPI health endpoint:

```text
http://127.0.0.1:8001/health
```

---

## Локальный workflow для разработки

Рекомендуемый workflow:

```text
Django запускается локально.
PostgreSQL запускается в Docker.
FastAPI можно запускать локально или в Docker.
```

Такой подход удобен тем, что Django быстро перезапускается после изменений кода без пересборки Docker image.

### 1. Установить зависимости

Если используется `uv`:

```bash
uv pip install -r requirements.txt
uv pip install -r services/lead_scoring_api/requirements.txt
```

### 2. Создать env-файлы

```bash
cp .env.docker.example .env.docker
cp .env.local.example .env.local
```

Пароль и имя базы должны совпадать в `.env.docker` и `.env.local`.

### 3. Запустить PostgreSQL

```bash
docker compose up -d db
```

PostgreSQL будет доступен локально:

```text
127.0.0.1:5433
```

### 4. Запустить Django локально

```bash
export DJANGO_ENV_FILE=.env.local
python manage.py migrate
python manage.py runserver
```

Django будет доступен по адресу:

```text
http://127.0.0.1:8000
```

### 5. Запустить FastAPI локально

В отдельном терминале:

```bash
cd services/lead_scoring_api
uvicorn app.main:app --reload --port 8001
```

FastAPI будет доступен по адресу:

```text
http://127.0.0.1:8001
```

---

## Docker services

| Service | Описание | Порт |
|---|---|---|
| `web` | Django development server | `8000` |
| `db` | PostgreSQL database | host `5433`, container `5432` |
| `scoring-api` | FastAPI lead scoring service | `8001` |

---

## Django REST API

Swagger-документация:

```text
http://127.0.0.1:8000/api/docs/
```

OpenAPI schema:

```text
http://127.0.0.1:8000/api/schema/
```

### Основные endpoints

| Method | Endpoint | Доступ | Описание |
|---|---|---|---|
| `GET` | `/api/v1/categories/` | Public | Список активных категорий |
| `GET` | `/api/v1/categories/{slug}/` | Public | Детали категории |
| `GET` | `/api/v1/products/` | Public | Список активных товаров |
| `GET` | `/api/v1/products/{id}/` | Public | Детали товара |
| `POST` | `/api/v1/leads/contact/` | Public | Создание контактной заявки |
| `GET` | `/api/v1/leads/` | Staff/Admin | Список заявок |
| `GET` | `/api/v1/leads/{id}/` | Staff/Admin | Детали заявки |
| `GET` | `/api/v1/leads/{id}/score/` | Staff/Admin | Получение текущего score заявки |
| `POST` | `/api/v1/leads/{id}/score/recalculate/` | Staff/Admin | Пересчёт score заявки |

### Фильтры товаров

Примеры:

```text
/api/v1/products/?search=pump
/api/v1/products/?category=1
/api/v1/products/?category_slug=pumps
/api/v1/products/?min_price=1000
/api/v1/products/?max_price=50000
/api/v1/products/?has_price=true
/api/v1/products/?ordering=price
/api/v1/products/?ordering=-price
```

### Создать контактную заявку через API

```bash
curl -X POST http://127.0.0.1:8000/api/v1/leads/contact/ \
  -H "Content-Type: application/json" \
  -d '{
    "fullname": "Petr Sidorov",
    "phone_number": "+79998887766",
    "email": "petr@example.com",
    "comment": "Created from API",
    "agree_to_policy": true
  }'
```

### Получить список заявок как администратор

```bash
curl -u "<username>:<password>" http://127.0.0.1:8000/api/v1/leads/
```

### Пересчитать score заявки

```bash
curl -u "<username>:<password>" -X POST http://127.0.0.1:8000/api/v1/leads/1/score/recalculate/
```

### Получить score заявки

```bash
curl -u "<username>:<password>" http://127.0.0.1:8000/api/v1/leads/1/score/
```

---

## FastAPI Lead Scoring Service

FastAPI Swagger:

```text
http://127.0.0.1:8001/docs
```

Health endpoint:

```text
GET /health
```

Scoring endpoint:

```text
POST /api/v1/score
```

### Health check

```bash
curl http://127.0.0.1:8001/health
```

Ожидаемый ответ:

```json
{
  "status": "ok",
  "service": "lead_scoring_api"
}
```

### Рассчитать score по признакам лида

```bash
curl -X POST http://127.0.0.1:8001/api/v1/score \
  -H "Content-Type: application/json" \
  -d '{
    "source": "cart",
    "has_profile": true,
    "items_count": 5,
    "total_quantity": 10,
    "total_amount": 120000,
    "comment_length": 80,
    "is_business_email": true,
    "cart_adds_7d": 2,
    "has_utm": true
  }'
```

Пример ответа:

```json
{
  "score": 100.0,
  "priority": "high",
  "model_name": "rule_based_fastapi_scoring",
  "model_version": "1.0",
  "explanation": [
    {
      "code": "source_cart",
      "label": "Lead was created from cart",
      "points": 25
    }
  ]
}
```

---

## Тестирование

### Django tests

```bash
python manage.py test
```

Текущее состояние:

```text
36 Django tests passed
```

### FastAPI tests

```bash
cd services/lead_scoring_api
pytest
```

Текущее состояние:

```text
7 FastAPI tests passed
```

### Запуск обоих наборов тестов

Из корня проекта:

```bash
python manage.py test
cd services/lead_scoring_api
pytest
```

---

## OpenAPI schema validation

Сгенерировать и проверить Django OpenAPI schema:

```bash
python manage.py spectacular --validate --file schema.yml
```


## Полезные Docker-команды

Собрать сервисы:

```bash
docker compose build
```

Запустить сервисы:

```bash
docker compose up -d
```

Запустить с пересборкой:

```bash
docker compose up --build -d
```

Остановить сервисы:

```bash
docker compose down
```

Логи Django:

```bash
docker compose logs -f web
```

Логи FastAPI:

```bash
docker compose logs -f scoring-api
```

Миграции:

```bash
docker compose exec web python manage.py migrate
```

Создать superuser:

```bash
docker compose exec web python manage.py createsuperuser
```

Django shell:

```bash
docker compose exec web python manage.py shell
```

PostgreSQL shell:

```bash
docker compose exec db psql -U django_b2b -d django_b2b
```

Сбросить dev-БД:

```bash
docker compose down -v
docker compose up --build -d
docker compose exec web python manage.py migrate
```

Важно: `docker compose down -v` удаляет локальный PostgreSQL volume.

---

## Полезные локальные команды

Django check:

```bash
python manage.py check
```

Применить миграции:

```bash
python manage.py migrate
```

Создать миграции:

```bash
python manage.py makemigrations
```

Создать superuser:

```bash
python manage.py createsuperuser
```

Запустить Django:

```bash
export DJANGO_ENV_FILE=.env.local
python manage.py runserver
```

Запустить FastAPI:

```bash
cd services/lead_scoring_api
uvicorn app.main:app --reload --port 8001
```

---

## Статус проекта

Реализовано:

- Django web application;
- PostgreSQL Docker setup;
- каталог товаров;
- корзина и избранное;
- система заявок;
- tracking middleware;
- аналитические модели;
- rule-based lead scoring;
- Django REST API;
- Swagger/OpenAPI документация;
- FastAPI scoring service;
- Django tests;
- FastAPI tests.
- GitHub Actions CI;

Ближайшие улучшения:

- screenshots для README;
- demo data seed command;
- интеграция Django scoring backend с FastAPI-сервисом;
- production-like Docker setup с Gunicorn/Nginx.

---

## Что демонстрирует проект

Проект демонстрирует практические backend-навыки:

- архитектура Django-приложения;
- Django models/services/forms;
- Django REST Framework;
- permission-protected API endpoints;
- Swagger/OpenAPI;
- FastAPI service;
- Pydantic request/response schemas;
- PostgreSQL;
- Docker Compose;
- unit/API tests;
- server-side analytics;
- lead scoring business logic;
- базовое понимание service-oriented architecture;
- Git-based workflow.

---

## Назначение репозитория

Этот репозиторий является портфолио-проектом для демонстрации backend-разработки на Python.

Основной фокус:

```text
Python
Django
Django REST Framework
FastAPI
PostgreSQL
Docker Compose
REST API
Tests
OpenAPI documentation
Backend architecture
```
