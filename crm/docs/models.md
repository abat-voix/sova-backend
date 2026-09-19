# Модели CRM «ИТ Школа Ростелекома»

Домен `crm` описывает взаимодействие ИТ Школы РТК с вузами (B2B) и физ/юрлицами
(B2C): от назначения ответственного менеджера за вуз до подписания лицензии
и прохождения сделки по настраиваемому workflow с аудит-логом переходов.

## Карта доменов

| Домен | Модели | Назначение |
|---|---|---|
| Справочники | `University`, `Vendor`, `ITDirection`, `ITProduct` | Каталоги, актуализируемые вручную или импортом xls/xlsx |
| Контакты и ответственность | `ContactPerson`, `ResponsibleAssignment` | Контактное лицо и ответственный КАМ — у вуза **и** у B2C-клиента, один и тот же паттерн |
| Сделка | `Interaction`, `InteractionProduct`, `License` | Взаимодействие с контрагентом, состав продуктов, договор |
| Workflow-движок | `WorkflowTemplate`, `WorkflowStatus`, `WorkflowTransition`, `WorkflowInstance`, `TransitionLog`, `Attachment` | Настраиваемый граф статусов сделки + аудит-трейл |
| Пользователи | `UserProfile` | Роль пользователя, синхронизированная с Keycloak |
| Импорт | `CatalogImportMapping` | Пользовательский маппинг колонок xls/xlsx → поля каталогов |
| B2C / LMS (бонус) | `B2CClient`, `LmsCourseSnapshot` | Физ/юрлица вне вузовской сети, снимки курсов из LMS |

## Диаграмма связей

```
Vendor ──┐
         ├──< ITProduct >── (M2M) ──< ITDirection
         │
University ──┐                    ┌── B2CClient
              ├──< ContactPerson ──┤        (ровно один контрагент — XOR, тот же паттерн у Interaction)
              ├──< ResponsibleAssignment >── manager (User)
              │                    │
              └──< Interaction >───┘──< InteractionProduct >── ITProduct
                       │      \
                       │       └──< License (история: is_active + superseded_at)
                       │
                       └── (1:1) WorkflowInstance ── template (WorkflowTemplate)
                                       │                  │
                                       │                  ├──< WorkflowStatus >──< WorkflowTransition
                                       │
                                       └──< TransitionLog >──< Attachment
```

---

## Терминология: направление, продукт, программа — и почему нет модели ITProgram

В ТЗ и на Q&A-сессии с постановщиком используются три разных по уровню термина,
которые легко перепутать:

- **ИТ-направление** (`ITDirection`) — широкая категория: DevOps, QA, Frontend.
  Просто ярлык.
- **ИТ-продукт** (`ITProduct`) — конкретное ПО/инструмент, которое физически
  передаётся вузу (лицензия + документация) в рамках сделки. Вокруг него и
  строится `Interaction`/`InteractionProduct`/`License`.
- **ИТ-программа** — учебный **курс целиком**: методические материалы,
  практика, расписание. Определение из ТЗ: "программа, содержащая в себе
  методические материалы и практику по тому направлению, по которому она
  написана". Примеры с Q&A-сессии: "Пробное инженерирование", "Secure-разработчик",
  "Аналитика на Python", "DevOps базис".

Постановщик (Крылов) уточнил на сессии, что программы бывают:
- **продуктозависимые** — курс построен вокруг конкретных продуктов группы
  компаний ("девопс базис, управление проектами... и дальше можете из открытых
  источников узнать, какие там ещё могут быть продукты"), причём **один курс
  может включать сразу несколько продуктов**;
- **продуктонезависимые** — общая теория/практика без привязки к конкретному
  инструменту.

### Почему модели `ITProgram` нет

Программа — это учебный **контент** (методичка, структура курса, расписание),
а это зона ответственности **LMS**, не CRM. CRM не ведёт методические
материалы и не является системой обучения — она ведёт **сделку с вузом**: кто
ответственный, какой договор, какие продукты переданы, на каком этапе workflow.
Поэтому программа как содержательная сущность в CRM не моделируется вовсе, а
появляется только двумя способами:

1. **Косвенно, через `ITProduct` + `ITDirection`.** Когда КАМ заводит сделку
   (`Interaction`) и добавляет в неё продукты (`InteractionProduct`),
   направление подразумевается через `ITProduct.directions`. Для целей сделки
   этого достаточно — не важно, как вуз преподаёт материал внутри программы,
   важно какой продукт и по какому направлению передан.
2. **Как синхронизированный снимок из LMS** (`LmsCourseSnapshot`, см. ниже) —
   если понадобится показать, какие курсы сейчас идут по продукту, или
   посчитать востребованность программы (п.5 ТЗ: "ранжирование программ по
   востребованности... заявки на обучение, количество обучающихся"). Именно
   поэтому у `LmsCourseSnapshot` связь с продуктами — M2M (`it_products`), а
   не одиночный FK: один курс/программа в LMS действительно может тянуть за
   собой несколько продуктов.

```
Interaction (сделка с вузом)
   └─ InteractionProduct → ITProduct → ITDirection (M2M)
                              │
                              └── (опционально) LmsCourseSnapshot ←──┐
                                                                     M2M — курс(=программа) может
                                                                     включать несколько продуктов
```

---

## Справочники

### University — вуз

Учебное заведение, с которым взаимодействует ИТ Школа. Заводится вручную через
админку/UI или строкой импорта xls/xlsx (дедупликация — по `inn`, а не по имени,
т.к. название часто пишут по-разному).

**Поля:** `name` (уникальное), `inn` (уникальный, nullable — не у всех вузов
известен на момент заведения), `external_code` (id в LMS/на сайте — для API-сверки),
`email`/`phone` (контакты вуза **как организации** — общая приёмная/канцелярия,
не путать с личными контактами `ContactPerson`, см. ниже), `is_active`.

**Property:** `current_responsible` — активный КАМ (`responsible_history.filter(unassigned_at__isnull=True).first()`).

**Пример:**
```python
university = University.objects.create(name="МГТУ им. Баумана", inn="7701234567", email="info@bmstu.ru")
```

### Vendor / ITDirection / ITProduct — вендор, направление, продукт

`Vendor` (1С, JetBrains...) и `ITDirection` (DevOps, QA, Frontend...) — плоские
справочники. `ITProduct` — конкретное ПО, привязанное к вендору и к одному или
нескольким направлениям (**M2M**, т.к. один продукт может закрывать сразу
несколько ИТ-направлений — например, платформа для практики и по DevOps, и по QA).

**Ограничения ITProduct:** `unique(vendor, name)`, а для продуктов без вендора —
`unique(name)` при `vendor is null` (частичный уникальный индекс).

```python
vendor = Vendor.objects.create(name="JetBrains")
devops = ITDirection.objects.create(name="DevOps")
qa = ITDirection.objects.create(name="QA")
product = ITProduct.objects.create(name="TeamCity", vendor=vendor)
product.directions.set([devops, qa])
```

---

## ContactPerson и ResponsibleAssignment — контакты и ответственность за контрагента

Обе модели генерализованы под **любого** контрагента — вуз или B2C-клиент
(`university`/`b2c_client`, ровно один из двух, `CheckConstraint`, тот же паттерн,
что у `Interaction`). До обобщения `UniversityContact`/`UniversityResponsible`
работали только с вузом, и это было не просто асимметрией, а реальным багом:
`crm/rules.py`-предикат `is_assigned_manager` проверяет "назначен ли пользователь
ответственным за контрагента этой сделки" — для B2C-сделок назначить ответственного
было физически некуда, и предикат для них всегда возвращал `False`.

### ContactPerson — контактное лицо

Конкретный человек со стороны вуза или B2C-клиента-юрлица (проректор, зав.
кафедрой, директор компании), с которым идёт переписка. Создаётся при первом
контакте, обычно вручную КАМом из карточки контрагента. Для B2C-физлица обычно
не нужен — у самого `B2CClient` уже есть `email`/`phone`.

**Поля:** `full_name`, `position`, `email`, `phone`, `is_active` — личные данные
человека, не путать с общими `email`/`phone` на `University`/`B2CClient` самой
организации.

**Ограничения:** `unique(university, full_name)` и `unique(b2c_client, full_name)`
— нельзя завести тёзку в рамках одного контрагента дважды. Оба — безусловные
`UniqueConstraint`, поэтому DRF на API-уровне автоматически строит из них
`UniqueTogetherValidator`, который форсирует `required=True` на **оба** поля —
это ломает XOR-семантику "ровно один из двух". Поэтому в `WriteContactPersonSerializer.Meta`
эта автогенерация явно отключена (`validators = []`), а проверка "ровно один
контрагент" сделана вручную в `validate()`.

```python
contact = ContactPerson.objects.create(
    university=university, full_name="Иванов И.И.", position="Проректор по науке",
)
```

### ResponsibleAssignment — ответственный КАМ за контрагента

Источник истины "кто ведёт контрагента". КАМ назначается **на контрагента
целиком** (не на отдельную сделку/продукт) — так как в реальности один и тот же
менеджер ведёт все продукты и направления сразу (подтверждено постановщиком на
Q&A-сессии). Поэтому привязки КАМа на уровне `Interaction` нет.

**Когда создаётся:** при первом назначении контрагента менеджеру, и повторно —
при каждой смене ответственного.

**Механизм смены:** запись **не перезаписывается**, а закрывается
(`unassigned_at = now()`), и создаётся новая — так сохраняется полная история
"кто и когда вёл контрагента". Именно поэтому `assigned_at`/`unassigned_at`, а
не просто `manager` на `University`/`B2CClient`.

**Ограничения:** `UniqueConstraint(fields=["university"], condition=Q(unassigned_at__isnull=True))`
и аналогичный по `b2c_client` — на одного контрагента в любой момент времени
может быть только одна **активная** запись (у каждого контрагента — своя, оба
constraint'а с `condition`, поэтому DRF их не трогает — форсированного
`required=True` здесь нет). Смену обязан выполнять сервисный слой транзакционно
(закрыть старую + создать новую), модель это не гарантирует сама.

**Кто может менять:** по ТЗ — роль «Руководитель» (менеджеры менять сами себя
не могут); в семенной миграции `0002_seed_role_groups` группе "Руководитель"
выданы `add/change/delete_responsibleassignment`.

```python
# Первое назначение (вуз)
ResponsibleAssignment.objects.create(university=university, manager=kam_petrov, assigned_by=director)

# Смена ответственного — делает сервисный слой, не модель
old = ResponsibleAssignment.objects.get(university=university, unassigned_at__isnull=True)
old.unassigned_at = timezone.now()
old.save(update_fields=["unassigned_at"])
ResponsibleAssignment.objects.create(university=university, manager=kam_sidorov, assigned_by=director)

# Тот же паттерн для B2C — раньше был невозможен
ResponsibleAssignment.objects.create(b2c_client=client, manager=kam_petrov, assigned_by=director)
```

---

## Сделка: Interaction, InteractionProduct, License

### Interaction — взаимодействие (сделка/договор)

Центральная сущность системы. Контрагент — **либо** вуз, **либо** B2C-клиент,
никогда оба и никогда ни один (`CheckConstraint interaction_exactly_one_counterparty`).
Это позволяет держать B2B- и B2C-сделки в одной таблице (и, соответственно,
использовать один и тот же workflow-движок для обеих веток, различая их только
через `WorkflowTemplate.audience`).

**Когда создаётся:** когда КАМ заводит новую сделку по вузу/клиенту — например,
"обсуждаем поставку набора продуктов по договору №42". По уточнению
постановщика, у одного вуза одновременно редко бывает больше 1–2 параллельных
`Interaction` (обычно это независимые треки, а не части одного процесса) — но
в БД это **не ограничено**, это мягкое бизнес-правило.

**Связи:** `university` (`PROTECT`, nullable), `b2c_client` (`PROTECT`, nullable),
`contact_person` (`SET_NULL`, nullable — контакт мог уволиться, сделка при
этом не удаляется). `clean()` проверяет, что `contact_person` принадлежит тому
же контрагенту, что и сама сделка (нельзя привязать контакт чужого вуза).

**Property:** `current_license` — активная лицензия (`licenses.filter(is_active=True).first()`).

```python
deal = Interaction.objects.create(
    university=university,
    contact_person=contact,
    comment="Пилот по DevOps-направлению на весенний семестр",
)
```

### InteractionProduct — состав сделки

Продукты, включённые в сделку. Отдельная M2M-модель, а не M2M-поле напрямую,
потому что состав **расширяется во времени** — постановщик явно подтвердил:
"к одному договору может сначала быть несколько продуктов, а потом эти продукты
могут расшириться". `added_at` фиксирует, когда именно продукт добавили в сделку.

**Ограничение:** `unique(interaction, it_product)` — нельзя добавить один и тот
же продукт в сделку дважды.

```python
InteractionProduct.objects.create(interaction=deal, it_product=product)
# Через полгода в ту же сделку добавили второй продукт:
InteractionProduct.objects.create(interaction=deal, it_product=another_product)
```

### License — договор/лицензия

Условия договора по сделке. Отдельная модель (не поля на `Interaction`), потому
что договор может быть **перезаключён** — новый номер, новый срок — и это
отдельный юридический факт, который не должен затирать предыдущий.

**Механизм перезаключения** — та же схема "закрыть + создать новую", что и у
`ResponsibleAssignment`: у превзойдённой записи выставляются `is_active=False`
и `superseded_at`, новая создаётся с `is_active=True`.

**Ограничение:** `UniqueConstraint(fields=["interaction"], condition=Q(is_active=True))`
— на сделку в любой момент времени действует не более одной лицензии.

```python
license_v1 = License.objects.create(
    interaction=deal, contract_number="Д-42/2026", is_signed=True,
    signed_at=date(2026, 3, 1), valid_until_year=2027, created_by=kam_petrov,
)

# Перезаключение договора через год
license_v1.is_active = False
license_v1.superseded_at = timezone.now()
license_v1.save(update_fields=["is_active", "superseded_at"])

license_v2 = License.objects.create(
    interaction=deal, contract_number="Д-42/2027", is_signed=True,
    signed_at=date(2027, 3, 1), valid_until_year=2028, created_by=kam_petrov,
)
deal.current_license  # -> license_v2
```

---

## Workflow-движок

Единый для всех сделок одной аудитории граф статусов (версионирования "под
конкретный вуз" нет — постановщик специально это исключил, чтобы не плодить
путаницу между подразделениями). B2B и B2C размечены через `WorkflowTemplate.audience`
и имеют раздельные "базовые" шаблоны.

### WorkflowTemplate — шаблон

**Ограничение:** `UniqueConstraint(fields=["audience"], condition=Q(is_base=True))`
— не более одного базового шаблона на аудиторию (b2b/b2c).

`stale_threshold_days` (по умолчанию 14) — порог, после которого сделка,
зависшая в одном статусе, должна триггерить уведомление ответственному
(сама рассылка — забота сервисного/celery-слоя, модель только хранит порог).

```python
b2b_template = WorkflowTemplate.objects.create(
    name="Базовый B2B-процесс", audience=Audience.B2B, is_base=True, stale_threshold_days=14,
)
```

### WorkflowStatus — статус (узел графа)

Принадлежит шаблону, имеет порядок (`order`), координаты на холсте (`pos_x`/`pos_y`
— для визуального редактора) и флаги `is_initial`/`is_final`.

**Ограничения:** `unique(template, order)`; не более одного `is_initial=True`
статуса на шаблон (`one_initial_status_per_template`).

```python
new = WorkflowStatus.objects.create(template=b2b_template, name="Новая заявка", order=1, is_initial=True)
contact_made = WorkflowStatus.objects.create(template=b2b_template, name="Контакт установлен", order=2)
signed = WorkflowStatus.objects.create(template=b2b_template, name="Договор подписан", order=3, is_final=True)
```

### WorkflowTransition — переход (ребро графа)

Разрешённый переход между двумя статусами **одного и того же** шаблона.
Постановщик подтвердил: ветвления и возвраты назад допустимы (граф, а не строгая
цепочка) — поэтому у статуса может быть несколько `outgoing_transitions`.

`required_permission` — не список строк ролей, а ссылка на встроенное Django
`Permission` в формате `"app_label.codename"` (пусто = переход доступен всем).
Роль пользователя нигде не хранится как отдельное поле — она полностью
выражена через `user.groups` (встроенные `Group`/`Permission`), см. раздел
"UserProfile и роли" ниже.

**Ограничения:** `unique(from_status, to_status)`; `CheckConstraint no_self_loop`
(нельзя вести статус сам в себя); `clean()` дополнительно проверяет, что
`from_status`, `to_status` и `template` принадлежат одному шаблону, и что
`required_permission` (если задан) имеет формат `"app_label.codename"`.

```python
WorkflowTransition.objects.create(template=b2b_template, from_status=new, to_status=contact_made)
WorkflowTransition.objects.create(
    template=b2b_template, from_status=contact_made, to_status=signed,
    required_permission="crm.can_transition_backward", requires_comment=True,
)
```

### WorkflowInstance — живой процесс конкретной сделки

**Когда создаётся:** сервисный слой создаёт `WorkflowInstance` **в момент
создания `Interaction`**, подставляя базовый шаблон нужной аудитории и его
`is_initial=True` статус. В моделях это не автоматизировано сигналом
намеренно — создание завязано на выбор шаблона (может быть не только базовый),
что логичнее оставить на явный вызов сервиса.

`status_changed_at` **не** является `auto_now` — иначе оно бы обновлялось при
любом `save()` объекта, а не только при реальном переходе статуса. Значение
руками выставляет сервисный слой при смене `current_status`.

```python
instance = WorkflowInstance.objects.create(interaction=deal, template=b2b_template, current_status=new)
```

### TransitionLog + Attachment — аудит-трейл

Каждый переход статуса фиксируется записью в `TransitionLog` (кто, когда, из
какого статуса в какой, с каким комментарием). `from_status` может быть `null`
для самой первой записи (переход "из ниоткуда" в начальный статус). К записи
можно приложить файлы (`Attachment`, `on_delete=CASCADE` от лога).

```python
log = TransitionLog.objects.create(
    instance=instance, from_status=new, to_status=contact_made,
    user=kam_petrov, comment="Созвонились, интерес подтверждён",
)
instance.current_status = contact_made
instance.status_changed_at = timezone.now()
instance.save(update_fields=["current_status", "status_changed_at"])

Attachment.objects.create(
    transition_log=log, file=uploaded_file, original_name="protocol.pdf",
    content_type="application/pdf", size_bytes=uploaded_file.size, uploaded_by=kam_petrov,
)
```

---

## UserProfile и роли

`UserProfile` больше не хранит роль — это только связка `User` с его
идентификатором в Keycloak (`keycloak_id`, `last_synced_at`). Роль полностью
выражена через встроенные `django.contrib.auth.models.Group`/`Permission`:
`Group` = роль ("Пользователь"/"Руководитель"/"Администратор" из ТЗ),
`Permission` (включая кастомные, объявленные в `Meta.permissions` моделей,
например `WorkflowTransition.can_transition_backward`) = конкретная
возможность, `user.groups` = какие роли у пользователя.

Django сам джойнит группу→права и кэширует результат на инстансе пользователя
на время запроса — `user.has_perm("crm.can_transition_backward")` не требует
отдельной модели/денормализации.

Для проверок, которым одной роли недостаточно (нужен ещё и объектный контекст,
например "этот пользователь — активный КАМ именно этого вуза") — `django-rules`
как второй authentication backend поверх того же `has_perm`, см.
`crm/rules.py` и `crm/api/authentication.py`.

```python
profile = UserProfile.objects.create(user=django_user, keycloak_id=uuid.uuid4())
django_user.groups.add(Group.objects.get(name="Руководитель"))
django_user.has_perm("crm.can_transition_backward")  # True, если право есть у группы
```

## CatalogImportMapping — маппинг колонок импорта

По требованию постановщика ("второй вариант" — диалоговый менеджер, не
захардкоженный маппинг) пользователь сам сопоставляет колонку xls/xlsx полю
модели через UI, а не через файл конфигурации. Одна запись — одна пара
"колонка → поле" для конкретного типа каталога.

**Ограничение:** `unique(catalog_type, target_field)` — одно поле каталога не
может быть смаплено на две разные колонки одновременно.

```python
CatalogImportMapping.objects.create(
    catalog_type=CatalogType.UNIVERSITY, source_column="Название ВУЗа", target_field="name",
)
```

---

## B2C / LMS (бонус — низкий приоритет)

### B2CClient — физ/юрлицо вне вузовской сети

Аналог `University`, но для B2C-ветки — постановщик подтвердил на сессии
вопрос-ответов, что помимо вузов есть направление работы с физлицами и
юрлицами, и для него нужен **отдельный** workflow (`WorkflowTemplate.audience=b2c`).
Как и `University`, полностью участвует в общих `ContactPerson`/`ResponsibleAssignment`
(`current_responsible` property — то же самое, что у `University`).

```python
client = B2CClient.objects.create(full_name="Петров П.П.", kind=ClientKind.INDIVIDUAL, email="petrov@example.com")
b2c_deal = Interaction.objects.create(b2c_client=client, comment="Индивидуальное обучение по QA")

# kind=LEGAL_ENTITY — компании тоже можно завести контактное лицо и ответственного,
# теми же моделями, что и у вуза:
company = B2CClient.objects.create(full_name="ООО Ромашка", kind=ClientKind.LEGAL_ENTITY, email="info@romashka.ru")
ContactPerson.objects.create(b2c_client=company, full_name="Сидоров С.С.", position="Директор")
ResponsibleAssignment.objects.create(b2c_client=company, manager=kam_petrov, assigned_by=director)
```

### LmsCourseSnapshot — снимок курса из LMS

Копия данных о курсе, полученных по API из LMS (двусторонняя интеграция,
на защите — на заглушках). Связь с `ITProduct` — **M2M** (`it_products`), а не
одиночный FK: постановщик подтвердил, что "продуктозависимая программа" может
включать сразу несколько продуктов ("девопс базис", "управление проектами" и
т.д. в составе одного курса). `raw_payload` хранит исходный JSON целиком — поля,
для которых пока нет конкретного потребителя (отчёта/экрана), в отдельные
колонки намеренно не выносятся, чтобы не копить мёртвые данные; их место —
внутри `raw_payload`, а колонкой они становятся только когда появляется задача,
которой нужен `WHERE`/`ORDER BY` на уровне БД. `synced_at` (`auto_now`) — момент
последней синхронизации.

```python
course = LmsCourseSnapshot.objects.create(
    external_id="lms-course-991", name="DevOps: базовый курс",
    raw_payload={"source": "lms", "id": 991, "duration_hours": 72},
)
course.it_products.set([product, another_product])
```

---

## Известные ограничения (не покрыто на уровне моделей)

- **Не более ~2 параллельных сделок на вуз** — бизнес-правило из Q&A-сессии,
  в БД не enforced (сознательно, чтобы не блокировать легитимные редкие случаи).
- **Создание `WorkflowInstance` при создании `Interaction`** — не сигнал, а
  ответственность сервисного слоя (ещё не реализован).
- **Ремап заявок при изменении workflow-графа** (постановщик: "сопоставление на
  новую [версию] должно происходить", запрет удаления/переименования статуса без
  подтверждения администратора, перенос заявок с удаляемого статуса на соседний) —
  описано в ТЗ как требование к сервисному слою/UI, моделями не реализовано.
- **Уведомления о "зависшей" заявке** (`stale_threshold_days`) — поле есть,
  планировщик (celery-beat / cron), который его читает и шлёт уведомления,
  ещё не написан.
- **Ранжирование программ по востребованности** — по ТЗ опционально ("плюсик в
  карму"), моделями не покрыто.

## Связанные файлы

- `crm/models/*.py` — все модели, один файл на модель
- `crm/models/base.py` — `TimeStampedModel` (общий `created_at`/`updated_at`)
- `crm/enum.py` — `Audience`, `ClientKind`, `CatalogType`
- `crm/rules.py` — django-rules predicate'ы и регистрация правил
- `crm/api/authentication.py` — валидация Keycloak-JWT (DRF authentication class)
- `crm/services/keycloak_sync.py` — синхронизация пользователя/ролей из claims токена
- `crm/services/workflow.py`, `crm/services/checklist.py` — выполнение перехода workflow, прогресс чек-листа
- `crm/admin.py` — регистрация в Django admin
- `crm/migrations/0001_initial.py` — схема; `0002_seed_role_groups.py` — сид ролей из ТЗ
