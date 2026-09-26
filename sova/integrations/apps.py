from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sova.integrations"
    label = "integrations"
    verbose_name = "Интеграции"
