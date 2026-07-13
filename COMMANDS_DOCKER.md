# Docker commands for django-b2b-ecommerce

## Build

docker compose build

## Start

docker compose up -d

## Stop

docker compose down

## Logs

docker compose logs -f web

## Migrations

docker compose run --rm web python manage.py migrate

## Create superuser

docker compose run --rm web python manage.py createsuperuser

## Django shell

docker compose run --rm web python manage.py shell

## Check project

docker compose run --rm web python manage.py check

## Open app

http://localhost:8000

## Open admin

http://localhost:8000/admin/
