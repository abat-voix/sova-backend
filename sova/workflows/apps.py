from django.apps import AppConfig


class WorkflowsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sova.workflows"
    label = "workflows"
    verbose_name = "Шаблоны процессов"
