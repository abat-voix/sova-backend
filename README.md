# SOVA Backend

Django + Django REST Framework backend для проекта СОВА.

## Runtime contract

Production image:

```text
ghcr.io/abat-voix/sova-backend:<tag>
```

Контейнер запускает Gunicorn на `0.0.0.0:8000`, работает от непривилегированного пользователя `sova` и предоставляет readiness endpoint `GET /api/health/`. Endpoint проверяет соединения с основной базой данных и настроенным cache/Redis.

Обязательные production-переменные:

- `DJANGO_SECRET_KEY`;
- `DATABASE_URL`;
- `REDIS_URL`;
- `DJANGO_ALLOWED_HOSTS`;
- `CSRF_TRUSTED_ORIGINS`;
- `EMAIL_HOST`, `EMAIL_HOST_USER` и `EMAIL_HOST_PASSWORD`.

Исходящая почта отправляется через SMTP. Для RU-CENTER используются
`mail.nic.ru:465`, SSL и полный адрес почтового ящика в качестве логина.
Пароль ящика храните только в runtime-окружении и не коммитьте в Git.

Полный пример находится в `.env.example`.

## Local development

```bash
poetry install

cp .env.example .env
set -a
source .env
set +a

poetry run python manage.py migrate
poetry run python manage.py runserver
```

Для быстрого запуска без PostgreSQL и Redis переменные `DATABASE_URL` и `REDIS_URL` можно временно удалить: development-конфигурация использует SQLite и локальный memory cache.

## API documentation

После запуска backend доступны:

- Swagger UI: `http://127.0.0.1:8000/api/docs/`;
- OpenAPI-схема: `http://127.0.0.1:8000/api/schema/`.

Оба endpoint публичны, чтобы документацию можно было открыть без авторизации.

## Checks

```bash
poetry check --lock
poetry run python manage.py check
poetry run python manage.py migrate --noinput
poetry run python manage.py test
```

## Docker

```bash
docker build -t sova-backend:local .
docker run --rm -p 8000:8000 \
  -e ENVIRONMENT=development \
  -e DJANGO_SECRET_KEY=development-only \
  -e DATABASE_URL=sqlite:////tmp/sova.sqlite3 \
  sova-backend:local
```

В dev-инфраструктуре migrations и `collectstatic` запускает `sova-infra/scripts/deploy.sh`; image не выполняет миграции автоматически.

## Container publication

Workflow `.github/workflows/publish-image.yml` публикует при push в `main`:

- `ghcr.io/abat-voix/sova-backend:dev`;
- `ghcr.io/abat-voix/sova-backend:sha-<full-commit-sha>`.

Для workflow используется встроенный `GITHUB_TOKEN`; отдельный registry token не требуется.
