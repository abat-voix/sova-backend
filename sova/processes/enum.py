from django.db.models import TextChoices


class StageInstanceContextType(TextChoices):
    """На каком уровне создан StageInstance."""

    INTERACTION = "interaction", "Взаимодействие целиком"
    IT_DIRECTION = "it_direction", "ИТ-направление"
    IT_PROGRAM = "it_program", "ИТ-программа"
    IT_PRODUCT = "it_product", "ИТ-продукт"
