from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from accounts.models import Supervision, SystemRole, UserRole
from accounts.services import account_service, get_system_role
from sova.core.admin import AbstractBaseModelAdmin


def full_name(user) -> str:
    """ФИО пользователя, а при его отсутствии — логин."""
    return user.get_full_name() or user.get_username()


def warn_orphans(request, head, orphans: list) -> None:
    """Предупреждает инициатора, что команда руководителя осталась без руководителя."""
    if orphans:
        names = ", ".join(full_name(kam) for kam in orphans)
        messages.warning(request, f"Команда «{full_name(head)}» осталась без руководителя: {names}")


class UserRoleInline(admin.StackedInline):
    """Роль СОВА в карточке пользователя; сохраняется через `account_service.change_role`."""

    model = UserRole
    can_delete = True
    extra = 0
    max_num = 1
    verbose_name = "Роль в СОВА"
    verbose_name_plural = "Роль в СОВА"


User = get_user_model()
admin.site.unregister(User)


@admin.register(User)
class SovaUserAdmin(UserAdmin):
    """
    Пользователи с ролью СОВА.

    Роль и флаг «Активный» меняются через `account_service`: при смене роли или деактивации удаляются связи
    «руководитель — КАМ», а инициатор видит, чья команда осталась без руководителя.
    """

    readonly_fields = ("supervision_info",)
    fieldsets = (*UserAdmin.fieldsets, ("СОВА", {"fields": ("supervision_info",)}))
    inlines = (UserRoleInline,)

    @admin.display(description="Руководитель / команда")
    def supervision_info(self, obj) -> str:
        """Руководитель КАМа или команда руководителя; меняется в разделе «Руководители КАМов»."""
        role = get_system_role(obj)
        if role == SystemRole.KAM:
            supervision = Supervision.objects.select_related("head").filter(kam=obj).first()
            return full_name(supervision.head) if supervision else "—"
        if role == SystemRole.HEAD:
            return ", ".join(full_name(kam) for kam in account_service.kams_of(head=obj)) or "—"
        return "—"

    def save_model(self, request, obj, form, change) -> None:
        """Сохраняет пользователя; смену флага «Активный» проводит через сервис."""
        if not change or "is_active" not in form.changed_data:
            super().save_model(request, obj, form, change)
            return

        is_active = obj.is_active
        obj.is_active = not is_active
        super().save_model(request, obj, form, change)
        if is_active:
            account_service.activate(user=obj, actor=request.user)
        else:
            warn_orphans(request=request, head=obj, orphans=account_service.deactivate(user=obj, actor=request.user))

    def save_formset(self, request, form, formset, change) -> None:
        """Роль из inline сохраняет сервис; остальные inline — как обычно."""
        if formset.model is not UserRole:
            super().save_formset(request, form, formset, change)
            return

        user = form.instance
        # Django Admin строит журнал изменений по этим спискам, которые обычно заполняет formset.save()
        formset.new_objects, formset.changed_objects, formset.deleted_objects = [], [], []
        for role_form in formset.forms:
            if role_form in formset.deleted_forms:
                if role_form.instance.pk is None:
                    continue
                orphans = account_service.change_role(user=user, role=None, actor=request.user)
                formset.deleted_objects.append(role_form.instance)
            elif role_form.has_changed():
                orphans = account_service.change_role(
                    user=user,
                    role=role_form.cleaned_data["role"],
                    actor=request.user,
                )
                assignment = UserRole.objects.get(user=user)
                if role_form.instance.pk is None:
                    formset.new_objects.append(assignment)
                else:
                    formset.changed_objects.append((assignment, role_form.changed_data))
            else:
                continue
            warn_orphans(request=request, head=user, orphans=orphans)

    def delete_model(self, request, obj) -> None:
        """Удаляет пользователя и предупреждает о его команде; связи удаляет CASCADE."""
        orphans = account_service.kams_of(head=obj)
        super().delete_model(request, obj)
        warn_orphans(request=request, head=obj, orphans=orphans)

    def delete_queryset(self, request, queryset) -> None:
        """Массовое удаление пользователей с предупреждением о командах."""
        teams = [(user, account_service.kams_of(head=user)) for user in queryset]
        super().delete_queryset(request, queryset)
        for head, orphans in teams:
            warn_orphans(request=request, head=head, orphans=orphans)


@admin.register(UserRole)
class UserRoleAdmin(AbstractBaseModelAdmin[UserRole]):
    """Роли пользователей; меняются через `account_service.change_role`."""

    list_display = ("user", "role")
    list_select_related = ("user",)
    search_fields = ("user__email", "user__first_name", "user__last_name")
    list_filter = ("role",)
    autocomplete_fields = ("user",)

    def get_readonly_fields(self, request, obj=None) -> tuple:
        """Пользователя у существующей роли не меняют: это другая роль."""
        readonly = super().get_readonly_fields(request, obj)
        return (*readonly, "user") if obj is not None else readonly

    def save_model(self, request, obj, form, change) -> None:
        """Назначает или меняет роль через сервис."""
        # Свежий пользователь: у `obj.user` в кеше `system_role` уже изменённая роль
        user = User.objects.get(pk=obj.user_id)
        orphans = account_service.change_role(user=user, role=obj.role, actor=request.user)
        obj.pk = UserRole.objects.get(user=user).pk
        warn_orphans(request=request, head=user, orphans=orphans)

    def delete_model(self, request, obj) -> None:
        """Снимает роль через сервис."""
        user = User.objects.get(pk=obj.user_id)
        warn_orphans(
            request=request,
            head=user,
            orphans=account_service.change_role(user=user, role=None, actor=request.user),
        )

    def delete_queryset(self, request, queryset) -> None:
        """Массовое снятие ролей через сервис."""
        for assignment in queryset.select_related("user"):
            self.delete_model(request=request, obj=assignment)


@admin.register(Supervision)
class SupervisionAdmin(AbstractBaseModelAdmin[Supervision]):
    """Руководители КАМов; назначаются и снимаются через `account_service`."""

    list_display = ("kam", "head")
    list_select_related = ("kam", "head")
    search_fields = ("kam__first_name", "kam__last_name", "kam__email", "head__first_name", "head__last_name")
    list_filter = (("head", admin.RelatedOnlyFieldListFilter),)
    autocomplete_fields = ("kam", "head")

    def get_readonly_fields(self, request, obj=None) -> tuple:
        """КАМа у существующей связи не меняют: сменить КАМа — удалить связь и создать новую."""
        readonly = super().get_readonly_fields(request, obj)
        return (*readonly, "kam") if obj is not None else readonly

    def save_model(self, request, obj, form, change) -> None:
        """Назначает КАМу руководителя через сервис."""
        supervision = account_service.set_supervisor(kam=obj.kam, head=obj.head, actor=request.user)
        obj.pk = supervision.pk

    def delete_model(self, request, obj) -> None:
        """Снимает руководителя через сервис."""
        account_service.remove_supervisor(kam=obj.kam, actor=request.user)

    def delete_queryset(self, request, queryset) -> None:
        """Массовое снятие руководителей через сервис."""
        for supervision in queryset.select_related("kam"):
            self.delete_model(request=request, obj=supervision)
