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
- `GOTENBERG_URL`;
- `EMAIL_HOST`, `EMAIL_HOST_USER` и `EMAIL_HOST_PASSWORD`.

Исходящая почта отправляется через SMTP. Для RU-CENTER используются
`mail.nic.ru:465`, SSL и полный адрес почтового ящика в качестве логина.
Пароль ящика храните только в runtime-окружении и не коммитьте в Git.
В development можно оставить `EMAIL_HOST`, `EMAIL_HOST_USER` и
`EMAIL_HOST_PASSWORD` пустыми — письма будут выводиться в консоль. SMTP-поля
нужно задавать либо все вместе, либо не задавать вовсе.

Полный пример находится в `.env.example`.

## Keycloak authentication

Keycloak подключён как OpenID Connect provider. Django выполняет server-side
Authorization Code flow с PKCE, создаёт локального пользователя по стабильному
claim `sub` и выдаёт браузеру обычную HttpOnly session cookie. Access и refresh
tokens не передаются frontend и не сохраняются в browser storage.

Маршруты:

- `GET /api/auth/me/` — состояние сессии, текущий пользователь и CSRF token;
- `GET /api/auth/oidc/authenticate/` — начало входа;
- `GET /api/auth/oidc/callback/` — callback Keycloak;
- `POST /api/auth/oidc/logout/` — выход из Django и Keycloak.

Для локального запуска настройте realm/client в Keycloak или используйте realm
из `sova-infra/keycloak/sova-realm.json`. Callback при запуске frontend через
его proxy: `http://localhost:3000/api/auth/oidc/callback/`.

Обязательные production-переменные авторизации:

- `APP_PUBLIC_URL`;
- `KEYCLOAK_PUBLIC_URL` и `KEYCLOAK_INTERNAL_URL`;
- `KEYCLOAK_REALM` и `KEYCLOAK_CLIENT_ID`;
- `KEYCLOAK_CLIENT_SECRET`.

Сессия продлевается молча: раз в `OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS` первый же
запрос переспрашивает Keycloak с `prompt=none`. Навигация браузера получает при
этом редирект, а запросы к `/api/` — `401` с кодом `session_expired`
(`accounts/middleware.py`), чтобы браузерный `fetch` не уходил по редиректу на
чужой origin и не падал с ошибкой CORS.

OIDC-пользователи получают unusable Django password. Локальный Django
`ModelBackend` сохранён для аварийного superuser в `/admin/`; не назначайте
OIDC-пользователям пароль вручную.

## System roles

Прикладная роль пользователя хранится в СОВА и выбирается суперпользователем в
Django Admin. Пользователю можно назначить одну из ролей: `КАМ`, `Руководитель`
или `Администратор платформы`. Пока роль используется только как классификация и
не меняет права доступа.

Роли не синхронизируются с Keycloak: Keycloak является источником личности и
аутентификации, а СОВА — источником прикладной роли. Django superuser остаётся
отдельным техническим признаком и не является ролью СОВА.

## Local development

Сначала поднимите инфраструктуру — PostgreSQL, Redis и Keycloak — из
репозитория `sova-infra`:

```bash
cd ../sova-infra
cp .env.local.example .env.local   # заполните пароли и client secret
docker compose --env-file .env.local -f compose.local.yml up -d
```

Затем backend:

```bash
poetry install

cp .env.example .env
# DATABASE_URL, REDIS_URL и KEYCLOAK_CLIENT_SECRET должны соответствовать
# значениям из sova-infra/.env.local
set -a
source .env
set +a

poetry run python manage.py migrate
poetry run python manage.py runserver
```

Файл читается через `source`, поэтому значения должны быть shell-safe: без
пробелов, `$` и `#` вне кавычек.

Для быстрого запуска без PostgreSQL и Redis переменные `DATABASE_URL` и `REDIS_URL` можно временно удалить: development-конфигурация использует SQLite и локальный memory cache.

## Шаблон workflow

Готовый шаблон процесса собирается одной командой — вручную создавать этапы,
действия, исходы и связи через API не нужно:

```bash
poetry run python manage.py create_workflow_template
```

Команда создаёт базовый процесс работы с вузом (`base-b2b`): 5 этапов —
«Подготовка и контакт», «Согласование и документы», «Поставка ПО» (этап на
каждый продукт взаимодействия), «Обучение преподавателей» (этап на каждую
программу) и «Сопровождение», — 12 действий с плановыми длительностями,
зависимостями внутри этапов, исходами и ветвлением: исход «Нужны правки»
запускает действие «Доработать документы». Декларация шаблона лежит в
`sova/workflows/presets.py`, сборку графа делает
`sova.workflows.services.workflow_template_service`.

Аргументы:

- `--code` и `--name` — код и название шаблона (по умолчанию `base-b2b`);
- `--audience b2b|b2c` — аудитория; граф не меняется;
- `--base` — сделать шаблон базовым для аудитории (базовый один на аудиторию);
- `--username` — автор шаблона; попадёт в `created_by` и в журнал `WorkflowChange`;
- `--recreate` — удалить шаблон с этим кодом и собрать заново. Запрещено, если по
  шаблону уже запущены процессы: каскадное удаление снесло бы их историю.

Без `--recreate` повторный запуск не трогает существующий шаблон и завершается
ошибкой. Правила комментария и вложения заданы по минимуму — их включают на
исходах через API или Django Admin под свой процесс.

Запуск процесса по готовому шаблону:

```http
POST /api/processes/workflow-instances/
Content-Type: application/json

{"workflow": "<id шаблона>", "interaction": "<id взаимодействия>"}
```

## PDF generation

Gotenberg запускается из `sova-infra` и доступен backend по переменной
`GOTENBERG_URL`. При локальной разработке это `http://localhost:3001`, а внутри
Compose-сети стенда — `http://gotenberg:3000`. API Gotenberg не должен быть
доступен из интернета.

Для преобразования готового HTML используйте единый клиент:

```python
from reports.pdf import HTMLAsset, html_to_pdf

pdf = html_to_pdf(
    "<html><body><img src='logo.png'><h1>Отчёт</h1></body></html>",
    assets=(HTMLAsset("logo.png", logo_bytes, "image/png"),),
    output_filename="report",
)
```

По умолчанию клиент генерирует A4, печатает CSS-фоны, учитывает `@page` и
завершает запрос ошибкой, если локальный ресурс не загрузился. Дополнительные
поля Chromium route можно передать через `form_fields`.

## API documentation

После запуска backend доступны:

- Swagger UI: `http://127.0.0.1:8000/api/docs/`;
- OpenAPI-схема: `http://127.0.0.1:8000/api/schema/`.

Оба endpoint публичны, чтобы документацию можно было открыть без авторизации.

Инструкции для frontend:

- `docs/frontend/users-api.md` — список пользователей;
- `docs/frontend/session-refresh.md` — продление сессии и ошибка CORS на
  Keycloak при истёкшем id token.

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
