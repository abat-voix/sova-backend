from typing import Generic, TypeVar

from django.contrib import admin
from django.db import models

ModelT = TypeVar("ModelT", bound=models.Model)


class AbstractBaseModelAdmin(admin.ModelAdmin, Generic[ModelT]):
    """
    Базовая админка моделей проекта.

    Поля created_at/updated_at (если они есть у модели) автоматически становятся
    readonly и выносятся в отдельный блок "Служебная информация" — если fieldsets
    не заданы явно. Не все модели проекта наследуют TimeStampedModel (например,
    WorkflowInstance, License), поэтому список берётся по факту наличия полей
    на конкретной модели, а не жёстко захардкожен.
    """

    _base_model_fields = ("created_at", "updated_at")

    def _existing_base_fields(self):
        field_names = {f.name for f in self.model._meta.get_fields()}
        return tuple(name for name in self._base_model_fields if name in field_names)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        for name in self._existing_base_fields():
            if name not in readonly:
                readonly.append(name)
        return tuple(readonly)

    def get_fieldsets(self, request, obj=None):
        if self.fieldsets:
            return super().get_fieldsets(request, obj)

        base_fields = self._existing_base_fields()
        main_fields = [f for f in self.get_fields(request, obj) if f not in base_fields]

        fieldsets = [(None, {"fields": main_fields})]
        if base_fields:
            fieldsets.append(("Служебная информация", {"fields": base_fields}))
        return fieldsets


class AbstractHistoryModelAdmin(AbstractBaseModelAdmin[ModelT]):
    """
    Админка для моделей-логов: запись создаётся системой (workflow-движком),
    вручную не редактируется. Все поля — readonly, добавление и изменение
    через админку запрещены (доступны только просмотр и удаление).
    """

    def get_readonly_fields(self, request, obj=None):
        return tuple(f.name for f in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
