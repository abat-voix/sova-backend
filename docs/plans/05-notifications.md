# Шаг 5. Система уведомлений (Telegram, MAX, email)

Источник задачи: прямой запрос пользователя (не из ТЗ хакатона), 2026-09-21. Пример для
вдохновения — `/home/roman/PycharmProjects/kiout-llm-backend/server/apps/user/tasks.py`
(`send_notification` + `TelegramNotifier`/`EmailNotifier`); следовать ему не обязательно,
использован только как референс паттернов.

## Что есть сейчас (проверено)

- Уведомлений в проекте нет вообще — ни одной модели, ни сервиса.
- `sova/celery.py` — заглушка: `celery`/`django-celery-beat` стоят в `.venv`, но их нет в
  `pyproject.toml`/`poetry.lock`, в `settings.py` нет `CELERY_*`, в `Dockerfile` нет
  worker/beat процесса. Шаг 0 «Celery» был откачен пользователем 2026-09-20 (см.
  `docs/plans/README.md`, бэкап `~/sova-backup-20260920/`). **В этом шаге асинхронную
  доставку и периодические проверки не делаем — только сам механизм отправки, синхронно.**
  Встраивание в конкретные события (просрочка этапа, назначение ответственного и т.д.) и
  Celery/beat — отдельные будущие шаги.
- `requests` объявлен только в dev-группе `pyproject.toml`, но уже используется в проде
  (`reports/pdf.py` → Gotenberg). Это значит, что прод-образ (`Dockerfile` ставит
  `poetry install --only main`) сейчас потенциально падает на этом импорте. Перенос в
  main-группу — часть этого шага (нужен и уведомлениям).
- Точки будущей интеграции (не в этом шаге): `ActionInstance.responsible`,
  `StageInstance.added_by`, `WorkflowInstance.created_by`.
- `accounts.UserRole` — прецедент профильной модели: `OneToOneField` на
  `AUTH_USER_MODEL`, обычный `models.Model` (int pk — `UUIDModel` только у бизнес-моделей
  `sova/*`), inline в `SovaUserAdmin`. `accounts/` — плоская структура (`tests.py`,
  `services.py`), без пакетов `tests/`/`services/`.
- `docs/style_guide/service.md` уже содержит иллюстративный вызов
  `notification_service.send(recipient=..., message=...)` — берём эту сигнатуру за основу
  публичного API.
- MAX Bot API — официальный REST API: `POST https://platform-api.max.ru/messages?chat_id=...`,
  `Authorization: Bearer <token>`, JSON-тело. Токена/тестового бота пока нет — добавляем
  настройки-плейсхолдеры, читаем из окружения.

## Принятые решения

1. **Получатели** — точечные (конкретный `User`) и общие (список получателей или один
   «статический» получатель, собранный вызывающим кодом) — единым вызовом
   `notification_service.send(recipient=..., message=...)`, без встроенного понятия
   «категорий» рассылки (в отличие от примера kiout-llm-backend) — набор получателей решает
   вызывающий код, сервис не знает про бизнес-роли.
2. **Контакты пользователя** — новая модель `accounts.NotificationProfile`
   (`user` OneToOne, `telegram_chat_id`, `max_chat_id`, оба `blank=True`); email берётся из
   `user.email`, отдельно не хранится.
3. **Публичный API** (`sova/notifications/services/notifier.py`):

   ```python
   notification_service.send(
       recipient=user_or_recipient,   # AbstractBaseUser | Recipient | Sequence[...]
       message="Текст уведомления",   # str
       channels=None,                 # Sequence[NotificationChannel] | None — все, для которых есть адрес
   ) -> list[NotificationResult]      # NotificationResult: recipient, channel, success (dataclass)
   ```

   Результат — список, а не `dict` с `Recipient` в ключе: `Recipient` — обычный (не
   `frozen`) dataclass, специально не делаем его hashable ради ключей словаря — это лишнее
   ограничение на структуру, не нужное нигде, кроме сигнатуры результата.

   `User` конвертируется в `Recipient` автоматически (`Recipient.for_user`). Если у
   получателя нет адреса для канала — канал для него молча пропускается (не ошибка).
   Ошибка одного канала/получателя логируется (`logger.exception`, только `%`-форматирование
   по `code_style.md`) и не прерывает остальные каналы/получателей.
4. **Email-канал** — `django.core.mail.send_mail` на уже настроенном `EMAIL_BACKEND`; тема
   письма — первая строка `message`, обрезанная до 120 символов (публичный API не даёт
   отдельного `subject`, см. решение 3 и риски).
5. **Telegram-канал** — `requests.post` на Telegram Bot API (`TELEGRAM_BOT_TOKEN`), по
   образцу примера kiout-llm-backend.
6. **MAX-канал** — `requests.post` на `{MAX_API_URL}/messages?chat_id=...` с
   `Authorization: Bearer {MAX_BOT_TOKEN}`, без сторонних библиотек (`maxapi` и т.п. не
   добавляем — не нужны для простого REST-вызова).
7. **Зависимости** — `requests` переносится из dev в main-группу `pyproject.toml`
   (фиксирует и уже существующий прод-баг в `reports/pdf.py`).
8. **Расположение** — новое приложение `sova/notifications/` (без моделей, без `api/` —
   только `enum.py` + `services/`); модель контактов — в `accounts/models.py` (там, где уже
   `UserRole`).
9. **Сознательно вне рамок этого шага**: Celery/периодические проверки, конкретные точки
   вызова в бизнес-логике, аудит-лог отправленных уведомлений, пользовательские
   настройки/отписки по каналам, HTML-письма/кнопки в Telegram.

## Открытые вопросы (по умолчанию)

| # | Вопрос | По умолчанию |
|---|---|---|
| N1 | Тема письма при отсутствии явного `subject` | первая строка `message`, обрезанная до 120 символов |
| N2 | У получателя нет ни одного канала с адресом | вернуть пустой `dict` результатов, не логировать как ошибку |
| N3 | Таймаут HTTP-запросов Telegram/MAX | 10 секунд (как `OIDC_TIMEOUT` в `settings.py`), настраивается через `NOTIFICATION_HTTP_TIMEOUT` |

## Модели (миграция; приложение `accounts`)

### `accounts.NotificationProfile`

- `user` — `OneToOneField(AUTH_USER_MODEL, on_delete=CASCADE, related_name="notification_profile")`
- `telegram_chat_id` — `CharField(max_length=64, blank=True)`
- `max_chat_id` — `CharField(max_length=64, blank=True)`
- `Meta`: `verbose_name`/`verbose_name_plural`; `__str__` → `str(self.user)`
- Регистрация: inline в `SovaUserAdmin` (по образцу `UserRoleInline`), без отдельной
  `ModelAdmin`-страницы — это 1:1 профиль, самостоятельного списка не нужно.

## Настройки (`sova/settings.py`)

```python
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "")
MAX_API_URL = os.getenv("MAX_API_URL", "https://platform-api.max.ru").rstrip("/")
NOTIFICATION_HTTP_TIMEOUT = float(os.getenv("NOTIFICATION_HTTP_TIMEOUT", "10"))
```

## Структура `sova/notifications/`

```
sova/notifications/
├── README.md
├── apps.py
├── enum.py                    # NotificationChannel(TextChoices): EMAIL, TELEGRAM, MAX
├── services/
│   ├── __init__.py            # реэкспорт NotificationService, notification_service, Recipient
│   ├── recipient.py           # Recipient (dataclass) + Recipient.for_user
│   ├── notifier.py            # NotificationService + notification_service
│   └── channels/
│       ├── __init__.py
│       ├── base.py            # NotificationChannelSender (ABC): send(target, message) -> bool
│       ├── email.py           # EmailChannelSender
│       ├── telegram.py        # TelegramChannelSender
│       └── max.py             # MaxChannelSender
└── tests/
    ├── __init__.py
    ├── test_recipient.py
    ├── test_notifier.py
    └── test_channels.py
```

`INSTALLED_APPS`: добавить `"sova.notifications"` (по образцу `sova.catalog` и т.д.,
`label = "notifications"`).

## Задачи

### 5a. Зависимости и настройки

- [ ] Перенести `requests` из dev в main-группу `pyproject.toml`, обновить `poetry.lock`
- [ ] Добавить `TELEGRAM_BOT_TOKEN`, `MAX_BOT_TOKEN`, `MAX_API_URL`,
      `NOTIFICATION_HTTP_TIMEOUT` в `settings.py`

### 5b. Контакты пользователя

- [ ] `accounts.NotificationProfile` + миграция
- [ ] Inline-регистрация в `SovaUserAdmin`
- [ ] `NotificationProfileFactory` в `sova/core/tests/factories.py` (рядом с `UserFactory`)

### 5c. Приложение `sova/notifications/`

- [ ] `enum.py` — `NotificationChannel`
- [ ] `services/recipient.py` — `Recipient`, `Recipient.for_user`
- [ ] `services/channels/{base,email,telegram,max}.py`
- [ ] `services/notifier.py` — `NotificationService`, `notification_service`
- [ ] `apps.py`, добавление в `INSTALLED_APPS`
- [ ] `README.md` приложения (по `docs/style_guide/readme.md`)

### 5d. Тесты

- [ ] `tests/test_recipient.py` — `Recipient.for_user`: есть профиль/нет профиля/пустой
      email/пустые `telegram_chat_id`/`max_chat_id`
- [ ] `tests/test_channels.py` — каждый канал: успех (мок `requests`/`send_mail`), HTTP/SMTP
      ошибка → `False` + лог, пустой `target` не вызывается вообще
- [ ] `tests/test_notifier.py` — несколько получателей и каналов, фильтр
      `channels=[...]`, изоляция ошибки одного канала от остальных, получатель без адресов
      → пустой результат без исключения
- [ ] `accounts/tests.py` — тест модели `NotificationProfile` (создание, `__str__`)

## Готово, когда

```bash
.venv/bin/python manage.py test sova.notifications accounts
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py spectacular --validate --file /dev/null
```

- `notification_service.send(recipient=user, message="...")` реально уходит письмом на
  locmem-бэкенде в тестах
- Полный набор тестов проекта зелёный

## Риски и заметки

- MAX Bot API — интеграция не проверена вживую (нет токена/тестового бота на момент
  написания); формат тела запроса предполагается по публичной документации
  (`platform-api.max.ru`), может потребовать правки при первом реальном вызове.
- Публичный `message: str` без отдельного `subject` — осознанный компромисс ради простоты
  вызова (см. пример в `service.md`); если понадобится richer-контент (HTML-письмо, кнопки в
  Telegram/MAX) — расширение сигнатуры отдельным шагом, не сейчас.
- Синхронная отправка блокирует вызывающий код на длительность HTTP-запроса (до
  `NOTIFICATION_HTTP_TIMEOUT`) — осознанно принято для v1, пока Celery не поднят.
