from django.contrib import admin

from sova.core.admin import AbstractBaseModelAdmin, AbstractHistoryModelAdmin
from sova.core.masks import mask_email, mask_phone
from sova.training.models import (
    Learner,
    LearnerPersonalData,
    LearnerPersonalDataAccessLog,
    TrainingApplication,
    TrainingApplicationLearner,
    TrainingInstructor,
    TrainingInstructorQualification,
    TrainingStream,
    TrainingStreamInstructor,
)
from sova.training.services.personal_data_access import personal_data_access_service


class NoManualAddingMixin:
    """Обучающиеся приходят только из файла «Пользователи» — вручную их не добавляют."""

    def has_add_permission(self, request, obj=None):
        return False


class PersonalDataAdminMixin:
    """Персональные данные в админке — только администратору платформы; просмотр карточки пишется в журнал."""

    def has_view_permission(self, request, obj=None):
        return personal_data_access_service.can_read(request.user) and super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return personal_data_access_service.can_read(request.user) and super().has_change_permission(request, obj)

    def has_add_permission(self, request):
        return personal_data_access_service.can_read(request.user) and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return personal_data_access_service.can_read(request.user) and super().has_delete_permission(request, obj)

    def has_module_permission(self, request):
        return personal_data_access_service.can_read(request.user) and super().has_module_permission(request)


class TrainingStreamInstructorInline(admin.TabularInline):
    model = TrainingStreamInstructor
    extra = 0
    autocomplete_fields = ("instructor",)
    readonly_fields = ("assigned_by",)


@admin.register(TrainingStream)
class TrainingStreamAdmin(AbstractBaseModelAdmin[TrainingStream]):
    """Админка потоков обучения."""

    list_display = ("id", "name", "interaction_program", "status", "starts_at", "ends_at")
    list_select_related = ("interaction_program__program", "interaction_program__interaction")
    list_filter = ("status",)
    search_fields = ("id", "name", "interaction_program__program__name")
    autocomplete_fields = ("interaction_program",)
    readonly_fields = ("created_by",)
    inlines = (TrainingStreamInstructorInline,)


class TrainingInstructorQualificationInline(admin.TabularInline):
    model = TrainingInstructorQualification
    extra = 0
    autocomplete_fields = ("program", "interaction")
    readonly_fields = ("created_by",)


@admin.register(TrainingInstructor)
class TrainingInstructorAdmin(AbstractBaseModelAdmin[TrainingInstructor]):
    """Админка преподавателей."""

    list_display = ("id", "last_name", "first_name", "middle_name", "organization", "b2c_client", "is_active")
    list_select_related = ("organization", "b2c_client")
    list_filter = ("is_active", "academic_degree", "academic_title")
    search_fields = ("id", "last_name", "first_name", "email", "lms_external_id")
    autocomplete_fields = ("organization", "b2c_client", "directions", "programs")
    inlines = (TrainingInstructorQualificationInline,)


class TrainingApplicationLearnerInline(admin.TabularInline):
    """Участники заявки и факт оплаты; оплатившего участника не удаляют — сначала снимают отметку."""

    model = TrainingApplicationLearner
    extra = 0
    can_delete = False
    fields = ("learner", "is_paid")
    autocomplete_fields = ("learner",)


@admin.register(TrainingApplication)
class TrainingApplicationAdmin(AbstractBaseModelAdmin[TrainingApplication]):
    """Админка заявок на потоки."""

    list_display = ("id", "stream", "status", "created_by", "created_at")
    list_select_related = ("stream", "created_by")
    list_filter = ("status",)
    search_fields = ("id", "stream__name", "comment")
    autocomplete_fields = ("stream",)
    readonly_fields = ("created_by",)
    inlines = (TrainingApplicationLearnerInline,)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        # Заявку с оплатившими участниками не удаляют — её отменяют
        if obj is not None and obj.participants.filter(is_paid=True).exists():
            return False
        return super().has_delete_permission(request, obj)



@admin.register(Learner)
class LearnerAdmin(NoManualAddingMixin, PersonalDataAdminMixin, AbstractBaseModelAdmin[Learner]):
    """Админка обучающихся: в списке email и телефон замаскированы."""

    list_display = ("id", "last_name", "first_name", "middle_name", "masked_email", "masked_phone", "is_active")
    list_filter = ("is_active",)
    search_fields = ("id", "last_name", "first_name")

    @admin.display(description="Email")
    def masked_email(self, obj: Learner) -> str:
        return mask_email(obj.email)

    @admin.display(description="Телефон")
    def masked_phone(self, obj: Learner) -> str:
        return mask_phone(obj.phone)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        response = super().change_view(request, object_id, form_url, extra_context)
        if response.status_code == 200 and (learner := self.get_object(request, object_id)) is not None:
            personal_data_access_service.log_access(
                user=request.user, learner=learner, fields=("email", "phone"), request=request
            )
        return response


@admin.register(LearnerPersonalData)
class LearnerPersonalDataAdmin(
    NoManualAddingMixin, PersonalDataAdminMixin, AbstractBaseModelAdmin[LearnerPersonalData]
):
    """Админка персональных данных; каждый просмотр карточки — запись в журнал доступа."""

    list_display = ("id", "learner", "gender", "education_level")
    list_select_related = ("learner",)
    search_fields = ("id", "learner__last_name")
    autocomplete_fields = ("learner",)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        response = super().change_view(request, object_id, form_url, extra_context)
        if response.status_code == 200 and (data := self.get_object(request, object_id)) is not None:
            personal_data_access_service.log_access(user=request.user, learner=data.learner, request=request)
        return response


@admin.register(LearnerPersonalDataAccessLog)
class LearnerPersonalDataAccessLogAdmin(
    PersonalDataAdminMixin, AbstractHistoryModelAdmin[LearnerPersonalDataAccessLog]
):
    """Журнал доступа к персональным данным — только чтение."""

    list_display = ("accessed_at", "user", "learner", "action", "ip")
    list_select_related = ("user", "learner")
    list_filter = ("action",)

    def has_delete_permission(self, request, obj=None):
        return False
