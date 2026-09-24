from django.apps import AppConfig


class CoreConfig(AppConfig):
    """
    Общий код проекта: базовые модели, admin-миксины, работа с файлами и хранилищем.

    Регистрируется как приложение только для того, чтобы Django видел его
    management-команды (`check_storage`, `copy_files_to_storage`); собственных
    моделей и миграций у приложения нет.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "sova.core"
    label = "core"
