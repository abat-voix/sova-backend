from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from accounts.models import UserRole


class UserRoleInline(admin.StackedInline):
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
    inlines = (UserRoleInline,)


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role")
    list_filter = ("role",)
    search_fields = ("user__email", "user__first_name", "user__last_name")
    autocomplete_fields = ("user",)
