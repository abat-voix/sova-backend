from django.apps import AppConfig


class CrmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sova.crm"
    verbose_name = "CRM ИТ Школы"

    def ready(self):
        import sova.crm.rules  # noqa: F401 — регистрирует правила django-rules
