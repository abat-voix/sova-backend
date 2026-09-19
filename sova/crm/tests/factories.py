import factory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from sova.crm.enum import Audience, CatalogType, ClientKind
from sova.crm.models import (
    Attachment,
    B2CClient,
    CatalogImportMapping,
    ContactPerson,
    Interaction,
    InteractionProduct,
    InteractionProductStatus,
    InstanceChecklistProgress,
    ITDirection,
    ITProduct,
    License,
    LmsCourseSnapshot,
    ResponsibleAssignment,
    StatusChecklistItem,
    TransitionLog,
    University,
    UserProfile,
    Vendor,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowTemplate,
    WorkflowTransition,
)

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    """Фабрика пользователя Django."""

    username = factory.Sequence(lambda n: f"user-{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")

    class Meta:
        model = User


class SuperuserFactory(UserFactory):
    """Фабрика суперпользователя Django."""

    is_staff = True
    is_superuser = True


class GroupFactory(factory.django.DjangoModelFactory):
    """Фабрика роли (встроенная Django Group)."""

    name = factory.Sequence(lambda n: f"Роль {n}")

    class Meta:
        model = Group
        django_get_or_create = ("name",)


class VendorFactory(factory.django.DjangoModelFactory):
    """Фабрика вендора."""

    name = factory.Sequence(lambda n: f"Вендор {n}")

    class Meta:
        model = Vendor


class ITDirectionFactory(factory.django.DjangoModelFactory):
    """Фабрика ИТ-направления."""

    name = factory.Sequence(lambda n: f"Направление {n}")

    class Meta:
        model = ITDirection


class ITProductFactory(factory.django.DjangoModelFactory):
    """Фабрика ИТ-продукта."""

    name = factory.Sequence(lambda n: f"Продукт {n}")

    vendor = factory.SubFactory(VendorFactory)

    class Meta:
        model = ITProduct

    @factory.post_generation
    def directions(self, create, extracted, **kwargs):
        """Проставляет M2M-направления после создания объекта."""
        if not create:
            return
        self.directions.set(extracted if extracted is not None else [ITDirectionFactory()])


class UniversityFactory(factory.django.DjangoModelFactory):
    """Фабрика вуза."""

    name = factory.Sequence(lambda n: f"Вуз {n}")

    class Meta:
        model = University


class B2CClientFactory(factory.django.DjangoModelFactory):
    """Фабрика B2C-клиента."""

    full_name = factory.Sequence(lambda n: f"Клиент {n}")
    kind = ClientKind.INDIVIDUAL

    class Meta:
        model = B2CClient


class ContactPersonFactory(factory.django.DjangoModelFactory):
    """Фабрика контактного лица (по умолчанию — вуза как контрагента)."""

    full_name = factory.Sequence(lambda n: f"Контакт {n}")

    university = factory.SubFactory(UniversityFactory)

    class Meta:
        model = ContactPerson


class ResponsibleAssignmentFactory(factory.django.DjangoModelFactory):
    """Фабрика ответственного за контрагента (по умолчанию — вуза)."""

    university = factory.SubFactory(UniversityFactory)
    manager = factory.SubFactory(UserFactory)

    class Meta:
        model = ResponsibleAssignment


class InteractionFactory(factory.django.DjangoModelFactory):
    """Фабрика взаимодействия (по умолчанию — с вузом как контрагентом)."""

    university = factory.SubFactory(UniversityFactory)

    class Meta:
        model = Interaction


class InteractionProductFactory(factory.django.DjangoModelFactory):
    """Фабрика продукта взаимодействия."""

    interaction = factory.SubFactory(InteractionFactory)
    it_product = factory.SubFactory(ITProductFactory)

    class Meta:
        model = InteractionProduct


class LicenseFactory(factory.django.DjangoModelFactory):
    """Фабрика лицензии."""

    contract_number = factory.Sequence(lambda n: f"Д-{n}")

    interaction = factory.SubFactory(InteractionFactory)

    class Meta:
        model = License


class WorkflowTemplateFactory(factory.django.DjangoModelFactory):
    """Фабрика шаблона workflow."""

    name = factory.Sequence(lambda n: f"Шаблон {n}")
    audience = Audience.B2B

    class Meta:
        model = WorkflowTemplate


class WorkflowStatusFactory(factory.django.DjangoModelFactory):
    """Фабрика статуса workflow."""

    name = factory.Sequence(lambda n: f"Статус {n}")
    order = factory.Sequence(lambda n: n)

    template = factory.SubFactory(WorkflowTemplateFactory)

    class Meta:
        model = WorkflowStatus


class InteractionProductStatusFactory(factory.django.DjangoModelFactory):
    """Фабрика прогресса продукта по подстатусам."""

    # === ОБЫЧНЫЕ ПОЛЯ ===
    status_changed_at = factory.LazyFunction(timezone.now)

    # === FK ПОЛЯ ===
    interaction_product = factory.SubFactory(InteractionProductFactory)
    # current_status должен быть подстатусом (непустой parent) — проверяется в
    # InteractionProductStatus.clean(). Родитель создаётся отдельным вложенным SubFactory.
    current_status = factory.SubFactory(
        WorkflowStatusFactory,
        parent=factory.SubFactory(WorkflowStatusFactory),
    )

    class Meta:
        model = InteractionProductStatus


class StatusChecklistItemFactory(factory.django.DjangoModelFactory):
    """Фабрика пункта чек-листа статуса."""

    label = factory.Sequence(lambda n: f"Пункт чек-листа {n}")
    order = factory.Sequence(lambda n: n)

    status = factory.SubFactory(WorkflowStatusFactory)

    class Meta:
        model = StatusChecklistItem


class WorkflowTransitionFactory(factory.django.DjangoModelFactory):
    """Фабрика перехода workflow (from_status/to_status по умолчанию из разных шаблонов — при необходимости консистентности передавайте template/статусы явно)."""

    template = factory.SubFactory(WorkflowTemplateFactory)
    from_status = factory.SubFactory(WorkflowStatusFactory)
    to_status = factory.SubFactory(WorkflowStatusFactory)

    class Meta:
        model = WorkflowTransition


class WorkflowInstanceFactory(factory.django.DjangoModelFactory):
    """Фабрика процесса workflow."""

    interaction = factory.SubFactory(InteractionFactory)
    template = factory.SubFactory(WorkflowTemplateFactory)
    current_status = factory.SubFactory(WorkflowStatusFactory)

    class Meta:
        model = WorkflowInstance


class InstanceChecklistProgressFactory(factory.django.DjangoModelFactory):
    """Фабрика прогресса по пункту чек-листа заявки."""

    instance = factory.SubFactory(WorkflowInstanceFactory)
    checklist_item = factory.SubFactory(StatusChecklistItemFactory)

    class Meta:
        model = InstanceChecklistProgress


class TransitionLogFactory(factory.django.DjangoModelFactory):
    """Фабрика записи журнала переходов."""

    instance = factory.SubFactory(WorkflowInstanceFactory)
    to_status = factory.SubFactory(WorkflowStatusFactory)
    user = factory.SubFactory(UserFactory)

    class Meta:
        model = TransitionLog


class AttachmentFactory(factory.django.DjangoModelFactory):
    """Фабрика вложения."""

    file = factory.django.FileField(filename="test.pdf")
    original_name = "test.pdf"
    content_type = "application/pdf"
    size_bytes = 1024

    transition_log = factory.SubFactory(TransitionLogFactory)

    class Meta:
        model = Attachment


class UserProfileFactory(factory.django.DjangoModelFactory):
    """Фабрика профиля пользователя CRM."""

    keycloak_id = factory.Faker("uuid4")

    user = factory.SubFactory(UserFactory)

    class Meta:
        model = UserProfile


class CatalogImportMappingFactory(factory.django.DjangoModelFactory):
    """Фабрика маппинга импорта каталога."""

    catalog_type = CatalogType.UNIVERSITY
    source_column = factory.Sequence(lambda n: f"Колонка {n}")
    target_field = factory.Sequence(lambda n: f"field_{n}")

    class Meta:
        model = CatalogImportMapping


class LmsCourseSnapshotFactory(factory.django.DjangoModelFactory):
    """Фабрика снимка курса LMS."""

    external_id = factory.Sequence(lambda n: f"lms-{n}")
    name = factory.Sequence(lambda n: f"Курс {n}")
    raw_payload = factory.LazyFunction(dict)

    class Meta:
        model = LmsCourseSnapshot

    @factory.post_generation
    def it_products(self, create, extracted, **kwargs):
        """Проставляет M2M-продукты после создания объекта."""
        if not create or not extracted:
            return
        self.it_products.set(extracted)
