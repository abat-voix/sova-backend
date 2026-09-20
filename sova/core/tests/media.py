import tempfile

from django.test import override_settings


class TemporaryMediaMixin:
    """Подменяет MEDIA_ROOT временным каталогом на время класса тестов с загрузкой файлов."""

    @classmethod
    def setUpClass(cls) -> None:
        """Создаёт временный MEDIA_ROOT."""
        cls._media_dir = tempfile.TemporaryDirectory()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_dir.name)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls) -> None:
        """Возвращает настройки и удаляет временный каталог."""
        super().tearDownClass()
        cls._media_override.disable()
        cls._media_dir.cleanup()
