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
- `CHANNEL_REDIS_URL` (отдельная Redis DB для Channels; не используйте DB cache/Celery);
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

Прикладная роль пользователя хранится в СОВА. Пользователю можно назначить одну
из ролей: `КАМ`, `Руководитель` или `Администратор платформы`. Роль назначает
администратор платформы (`PUT /api/users/{id}/role/`) или суперпользователь в
Django Admin.

У КАМа может быть один руководитель, у руководителя — сколько угодно КАМов
(модель `Supervision`, раздел «Руководители КАМов» в Django Admin или
`PUT /api/users/{id}/head/`). Связь удаляется автоматически, когда участник
меняет роль или деактивируется (`POST /api/users/{id}/deactivate/`, флаг
«Активный» в Django Admin). КАМы, оставшиеся без руководителя, возвращаются в
ответе API (`orphaned_kams`) и показываются предупреждением в Django Admin —
их нужно переназначить. Участники получают уведомления «Назначение
руководителя» / «Снятие руководителя», инициатор — нет. Роль, руководителя и
активность меняет только `account_service`: изменения в обход него (shell,
`loaddata`) уведомлений не шлют и связи не чистят.

Руководитель сам ведёт команду: забирает свободного КАМа
(`POST /api/users/{id}/claim/`) и отпускает своего
(`POST /api/users/{id}/release/`). КАМа с другим руководителем забрать нельзя —
сначала его должен отпустить текущий руководитель (или администратор). В
`/api/users/` руководитель видит свою команду и свободных КАМов (фильтры
`team=mine|free`, `role`, `head`).

Ответственных назначают: администратор — любых активных КАМов и руководителей;
руководитель — себя, КАМов своей команды и свободных (свободный при этом
вступает в его команду); КАМ — только себя, а КАМ, создавший взаимодействие,
становится ответственным автоматически. Снимают: администратор — любого,
руководитель — себя, КАМов своей команды и неактивных КАМов, КАМ — никого.
Деактивация пользователя снимает его со всех взаимодействий: открытые задачи
уходят в пул, взаимодействие без других ответственных становится ничьим.

Руководитель видит взаимодействия, где ответственный — он сам, КАМ его команды
или КАМ без руководителя, а также взаимодействия без ответственного. Процессы,
этапы, результаты и откаты видны по тем же правилам. Связь также
используется в уведомлениях о сроках (режим «Руководитель КАМа»).

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

HTTP API остаётся на Gunicorn/WSGI. WebSocket transport запускается отдельным
ASGI-процессом (локально удобно использовать порт 8001):

```bash
poetry run daphne -b 0.0.0.0 -p 8001 sova.asgi:application
```

Frontend подключается к `/ws/events/`. События доставляются без гарантии и без
истории: PostgreSQL и REST остаются источником истины, а клиент после reconnect
повторно сверяет messaging queries. `CHANNEL_REDIS_URL` должен указывать на
логическую Redis DB, отличную от `REDIS_URL` и `CELERY_BROKER_URL`.

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

## Хранилище файлов

Вложения действий (`ActionAttachment`), файлы договоров (`Contract`, история — `ContractFile`)
и готовые отчёты (`ReportJob`) хранятся через Django Storage API (`STORAGES["default"]` /
`STORAGES["reports"]`), а не напрямую на диске — конкретный провайдер задаётся переменными
окружения и код от него не зависит. Подробности и порядок миграции — в
`docs/plans/2026-09-23-s3-storage.md`.

- `STORAGE_BACKEND=filesystem` (по умолчанию, всегда — в тестах): `MEDIA_ROOT` и
  `REPORTS_STORAGE_ROOT`, как раньше.
- `STORAGE_BACKEND=s3`: S3-совместимое хранилище — свой Garage из `sova-infra` (по умолчанию)
  или внешний провайдер (Yandex Object Storage, AWS и т. п.). Обязательные переменные:
  `S3_ENDPOINT_URL`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`,
  `S3_MEDIA_BUCKET`, `S3_REPORTS_BUCKET`. Опциональные: `S3_ADDRESSING_STYLE` (`path`),
  `S3_PRESIGNED_TTL` (300 c), `FILE_UPLOAD_MAX_SIZE_MB` (25).

Файл отдаётся только через API (`.../download/`), с проверкой видимости взаимодействия
(`visible_interactions`), а не напрямую из хранилища — прежний публичный `/media/*` в Caddy
убран. Способ отдачи — `S3_DOWNLOAD_MODE`:

- `proxy` (по умолчанию): Django сам стримит файл; хранилище остаётся только во внутренней сети;
- `redirect` (только `STORAGE_BACKEND=s3`): `302` на подписанный URL — когда endpoint хранилища
  виден браузеру.

Проверить доступность хранилищ и поставить lifecycle-правило на бакет отчётов:

```bash
poetry run python manage.py check_storage --apply-lifecycle
```

Перенос уже загруженных файлов при включении S3 (идемпотентно, можно запускать повторно):

```bash
poetry run python manage.py copy_files_to_storage --source-root ./media --storage default
poetry run python manage.py copy_files_to_storage --source-root ./private/reports --storage reports
```

## Отчёты

Модуль `sova.reports` строит отчёт по взаимодействиям с вузами (`/api/reports/`):

| Метод и путь | Назначение |
| --- | --- |
| `POST /api/reports/interactions/preview/` | страница строк, общее число строк и метаданные (`page_size` ≤ 200) |
| `POST /api/reports/interactions/summary/` | уникальные взаимодействия и распределения по ответственным, вузам, статусам процесса и этапам |
| `POST /api/reports/interactions/exports/` | задание на файл `xlsx`/`xls`/`pdf`/`json`, ответ `202` |
| `GET /api/reports/exports/{id}/` | состояние задания `queued/running/ready/failed` |
| `GET /api/reports/exports/{id}/download/` | готовый файл; `409` — не готов, `410` — срок хранения истёк |

Семантика отчёта:

- **Период** (`date_from`, `date_to`) — даты создания взаимодействия
  (`Interaction.created_at`, часовой пояс `Europe/Moscow`).
- **Состояние** — статус процесса, актуальные этапы, ответственный и состав отражают
  состояние на момент построения (`meta.generated_at`), а не на конец периода.
  Исторического среза «как было на дату» нет.
- **Строка** — активный продукт взаимодействия с программой и направлением
  (`Program.direction`); затем активные программы без продуктов и направления без программ;
  взаимодействие без состава — одна строка. Фильтры по направлению/программе/продукту
  ограничивают и сами строки.
- **Актуальный этап** — `StageInstance` со статусом `in_progress` на уровне взаимодействия
  или контекста строки. Несколько этапов возвращаются массивом, в файлах — через `; `.
- **Статистика** считает уникальные `Interaction.id`; число строк, программ и продуктов
  возвращается отдельно.
- Все ответы и файлы строятся из `visible_interactions(user)`; фоновое задание заново
  применяет видимость владельца. Задания и файлы доступны только владельцу.

Выгрузки выполняет Celery. Worker запускается из того же образа:

```bash
celery -A sova worker --loglevel=info --concurrency=2
celery -A sova beat --loglevel=info   # очистка просроченных файлов и зависших заданий
```

При локальном запуске на macOS пул worker по умолчанию — `solo`: он обходит сбой
`fast_trace_task` в дочерних процессах `SpawnPoolWorker`. Перезапустите уже
работающий worker после обновления настроек. Для явного запуска используйте
`celery -A sova worker --loglevel=info --pool=solo`; задания выполняются по одному.
В Linux-контейнере остаётся стандартный `prefork`.

Переменные: `CELERY_BROKER_URL` (по умолчанию `REDIS_URL`), `REPORTS_STORAGE_ROOT` —
приватный каталог файлов, общий для API и worker (общий том), `REPORTS_RETENTION_HOURS`
(72), `REPORTS_JOB_TIMEOUT_SECONDS` (1800), `REPORTS_PDF_MAX_ROWS` (5000),
`REPORTS_XLS_MAX_SHEETS` (4 листа по 65 536 строк), `REPORTS_MAX_ACTIVE_JOBS_PER_USER` (5).
Без брокера задания выполняются синхронно в процессе API — это режим только для разработки.

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
