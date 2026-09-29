from django.apps import AppConfig


class TrainingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sova.training"
    label = "training"
    verbose_name = "Обучение"
