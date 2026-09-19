from django.apps import AppConfig


class CrmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "crm"
    verbose_name = "CRM ИТ Школы"

    def ready(self):
        import crm.rules  # noqa: F401 — регистрирует правила django-rules при старте приложения
