# Планы развития backend СОВА

Составлено 2026-09-20 после того, как на все 30 моделей добавлен REST API
(serializers/filters/views/routers, 375 тестов). Планы самодостаточны: новая
сессия должна суметь продолжить работу, читая только этот каталог, ТЗ и гайды.

Источник требований: `/home/roman/Загрузки/hackathon/1/6. ИТ Школа Ростелекома.md`
(ТЗ). Гайды по коду: `docs/style_guide/*.md`.

## Порядок и зависимости

| # | План | Зависит от | Статус |
|---|---|---|---|
| 0 | [Подготовка: миграции, CI, Celery](00-prerequisites.md) | — | ⏪ откачено 2026-09-20 (бэкап `~/sova-backup-20260920/`); миграции есть в `8dcaae6`, остальное — не в ветке |
| 1 | [Роли и права](01-keycloak-roles.md) (роли в `accounts.UserRole`, Q0 закрыт) | 0 | ⏪ откачено 2026-09-20 (бэкап там же) |
| 2 | [Правила workflow](02-workflow-rules.md) (подтверждены пользователем); [движок, черновик](02-workflow-engine.md) — **не принят** | — | 🔧 **в работе**: модели, API определений, сервис движка и API движка с доской готовы (разделы 7 и 8 правил); дальше права, PostgreSQL, нагрузка |
| 3 | [Импорт каталогов xls/xlsx](03-catalog-import.md) | 0; 3b — после 2 | ☐ не начат |
| 4 | [Отчёты xls/xlsx/pdf и диаграммы](04-reports.md) | 0, 1, 2 | ☐ не начат |
| 5 | [Уведомления: Telegram, MAX, email](05-notifications.md) (механизм отправки, вне очереди 0→4) | — | ☐ не начат |

Рекомендуемая последовательность: **0 → 1 → 2 → 3a → 3b → 4**. Шаги 2 и 3a
независимы и могут идти параллельно. Обновляйте статус в таблице и чекбоксы
внутри планов по мере выполнения — это и есть «точка возобновления».

> **Актуальный фокус (2026-09-20): шаг 2, логика workflow.** Шаги 0 и 1 пользователь откатил; факты ниже про Celery, права
> и `444 теста` относятся к откаченному состоянию. Реальное состояние ветки: `git status` + `02-workflow-engine.md` (раздел
> «Состояние репозитория»), тестов 396. Правила логики workflow берутся из `02-workflow-rules.md`, а не из
> `02-workflow-engine.md` (тот файл — непринятый черновик).

## Что изменилось в репозитории после составления планов

Планы написаны 2026-09-20 до коммитов коллеги; при старте шага 0 выяснилось (см. `git log`):

- `8dcaae6` — приложения `catalog/interactions/workflows/processes` и мой API **закоммичены вместе с миграциями `0001_initial`**;
  у `WorkflowStage` **удалено поле `type`** (API поправлен).
- `8a845a8` «add base roles» — **роли хранятся в СОВА**: `accounts.UserRole` (`kam`/`head`/`platform_admin`), назначает
  суперпользователь в Django Admin, **не синхронизируются с Keycloak**, пока не влияют на права. План шага 1 переписан под это.
- `131cdcf` «add base document converter» — PDF через **Gotenberg** (`reports/pdf.py::html_to_pdf`, пакет `reports/`). План шага 4
  переписан под это (reportlab не нужен; приложение — существующий top-level пакет `reports/`).

## Как продолжить работу в новой сессии

1. Прочитать этот файл, затем план текущего шага (первый с невыполненными чекбоксами).
2. Проверить фактическое состояние: `git status`, `git log --oneline -10`,
   `.venv/bin/python manage.py test` (должно быть зелёным до начала работы).
3. Открытые вопросы плана: если пользователь не ответил — брать вариант,
   помеченный **«по умолчанию»**, и явно сообщить об этом в итоге.
4. Идти TDD: тесты (RED) → реализация (GREEN), как в `.claude/commands/new-viewset.md`.
5. После шага: обновить чекбоксы, статус в таблице, запустить полный набор проверок (ниже).

## Технические факты (проверены 2026-09-20)

- Запускать только через `.venv/bin/python`: системный `python3` мог падать из-за pyenv (`.python-version` указывал на
  неустановленную 3.13; сейчас в рабочей копии 3.11). Venv на Python **3.11**, Docker — на **3.13**.
- Тесты: `.venv/bin/python manage.py test` (Django test runner, SQLite, ~5 c, 444 теста на конец шага 1).
  Схема Swagger: `.venv/bin/python manage.py spectacular --validate --file /dev/null`
  (должна проходить без предупреждений; есть тест `sova/core/tests/test_schema.py`).
- Линтера ruff в окружении нет; жёсткий лимит — 120 символов в строке, только двойные кавычки.
- Миграции есть (`0001_initial` во всех приложениях, `accounts.0001_user_role`); новые изменения схем — отдельными миграциями.
- Все pk моделей — UUID (`sova/core/models.py`), кроме пользователя (стандартный `auth.User`, int).
- Пользователь создаётся из Keycloak по `sub` (`accounts/auth.py`); прикладная роль — `accounts.UserRole`
  (одна на пользователя), назначается вручную в Django Admin; `/api/auth/me/` отдаёт `role`, `roleDisplay`, `roles`.
- Celery подключён (шаг 0): `sova.celery_app`, `CELERY_*` в `settings.py`; без `REDIS_URL` задачи eager, с ним — брокер Redis;
  расписание — статический `CELERY_BEAT_SCHEDULE` (`django-celery-beat` не используется).
- PDF: `reports/pdf.py::html_to_pdf` → Gotenberg (`GOTENBERG_URL`); в `sova-infra` Gotenberg и worker пока не описаны.
- Зависимости: `requests` и `celery` — main; `factory-boy` — dev. CI ставит `--with dev`, Docker — `--only main`.
- Версии Python: `.python-version` в рабочей копии = 3.11 (не закоммичено), Dockerfile = 3.13.
- Инфраструктура — соседний репозиторий `../sova-infra` (compose, Keycloak realm
  `keycloak/sova-realm.json`, `scripts/deploy.sh`, который делает `migrate` и `collectstatic`).
  Изменения там указаны в планах явно как «cross-repo».

## Что уже есть в коде (не переписывать)

- `sova/core/api/`: `SovaBaseViewSet`, `SovaReadOnlyViewSet`, `ReadWriteSerializerMixin`,
  `ReadWriteCreateModelMixin`/`ReadWriteUpdateModelMixin`, `SearchFilterMixin`
  (`Meta.exact_search_fields` → фильтры `<поле>__iexact`), `NumberInFilter`, `UUIDInFilter`,
  `UserShortSerializer`, `StandardPagination` (50, `page_size`), `exception_handler`
  (`ProtectedError`/`IntegrityError` → 409 + поле `code`), `ConflictError`, `SovaAutoSchema`,
  валидаторы `validate_exactly_one_counterparty`, `validate_model_clean`.
- `sova/core/tests/`: `BaseApiTestMixin` (типовые list/detail/add/change/delete/search),
  `TemporaryMediaMixin`, `UserFactory`; фабрики приложений в `sova/<app>/tests/factories.py`.
- Приложения `catalog`, `interactions`, `workflows`, `processes`: каждое имеет
  `api/{serializers,filters,views}/`, `routers.py` (`app_name` = имя приложения,
  URL `/api/<app>/…`, имена маршрутов `<app>:<basename>-list|detail`),
  `services/` (`interactions`, `workflows`, `processes`), `api/tests/`.
- Сервисы: `interactions/services/{responsible,license}.py`, `workflows/services/{audit,dependency,outcome,stage_transition}.py`,
  `processes/services/{engine,board}.py` (движок workflow и доска процесса)
  (класс + инстанс-синглтон внизу файла, как в `docs/style_guide/service.md`).
- Аудит структуры workflow: `WorkflowAuditMixin` → `WorkflowChange`.

## Конвенции кода (коротко; полные — в `docs/style_guide/`)

- Пары сериализаторов `<Model>Serializer` (read) / `Write<Model>Serializer` (write),
  вложенные `<Model>ShortSerializer`; `label` и `help_text` (с большой буквы, не дублируют друг друга)
  у каждого явно объявленного поля.
- `read_serializer_class` + `serializer_class` во ViewSet; если read использует `annotate()` —
  переопределить `perform_create` с refetch через `get_queryset()`. `annotate()` с GROUP BY сбрасывает
  `Meta.ordering` → добавлять `.order_by(...)`.
- Условные `UniqueConstraint`/`CheckConstraint` DRF сам не проверяет — дублировать в `validate()`.
  DRF не подставляет model default в `attrs` — учитывать при кросс-полевых проверках.
- Именованные аргументы при вызове функций, аннотации типов, docstring у каждого класса/метода.
- Тесты: `# Проверяем …` перед каждым assert, docstring — факт о поведении, имена
  `test_<действие>_<результат>`.
- Ответ `Response(data=..., status=...)` — `data` всегда именованный и первый.

## Итоговая проверка любого шага

```bash
.venv/bin/python manage.py test
.venv/bin/python manage.py spectacular --validate --file /dev/null
.venv/bin/python manage.py makemigrations --check --dry-run   # после шага 0 — обязательно чистый
```

Плюс: скрипт-проверка длины строк ≤120 и отсутствия неиспользуемых импортов (см. историю сессии —
AST-скрипт по `sova/**`), либо установить ruff.

## Общий открытый список решений (нужен ответ пользователя)

Сводка вопросов из планов. Если ответа нет — берётся вариант «по умолчанию».

| # | Вопрос | По умолчанию | План |
|---|---|---|---|
| ~~Q0~~ | ~~Роли остаются в `accounts.UserRole`~~ — **закрыт 2026-09-20: да, Keycloak даёт только личность** | — | 1 |
| Q1 | Кто редактирует определения workflow | только `platform_admin` | 1 |
| Q2 | Что видит роль КАМ | только взаимодействия, где он действующий ответственный | 1 |
| Q3 | Пользователь без назначенной роли | доступа к данным нет (403), пока суперпользователь не назначит роль | 1 |
| Q4 | Нужны ли настраиваемые администратором ограничения видимости (`AccessScope`) | отложить (шаг 1d — по запросу) | 1 |
| Q5 | Убрать «сырое» создание StageInstance/ActionInstance/ActionResult (ломающее изменение API) | убрать, заменить действиями движка | 2 |
| Q6 | Содержимое базового B2C-workflow | не сидировать, только B2B из 14 пунктов ТЗ | 2 |
| Q7 | Стратегия импорта при ошибках в строках | по умолчанию dry-run, затем apply; при apply — `abort` | 3 |
| Q9 | Версия Python: `.python-version` 3.11 vs Dockerfile 3.13 | привести к одной (решает пользователь) | 0 |
| Q8 | Семантика «отчёт за период» | взаимодействие попадает, если создано в периоде или имеет результаты действий в периоде | 4 |

## Вне этих четырёх шагов (бэклог)

- Интеграции с LMS и сайтом на Laravel (JSON API → добавление в существующий/новый workflow) — ТЗ п. 5;
  контракт API заказчик передаст отдельно.
- «Кэш работы действий пользователя» (ТЗ, функц. требование 13) — формулировка неоднозначна, уточнить.
- Документация, встроенная в платформу; описание архитектуры в Archi; презентация (ТЗ п. 6–7).
- Метрики востребованности программ (заявки на обучение, число обучающихся, потоки — ТЗ п. 2):
  в моделях таких данных нет.
- Админка (`update-admin`) для новых сущностей, README приложений (`docs/style_guide/readme.md`).
- Нагрузочное тестирование (50 пользователей, 10 параллельных отчётов) — отдельно после шага 4.
