from django.db import migrations


class Migration(migrations.Migration):
    """
    Убирает приставку «IT» из названий каталожных моделей и поля ИТ-программы: ITDirection → Direction,
    ITProduct → Product, ITProgram → Program, Program.it_direction → Program.direction.

    Только переименования: related_name и остальные метаданные полей обновляются следующей миграцией —
    иначе Django-автодетектор не распознаёт переименование моделей, ссылающихся друг на друга.
    """

    dependencies = [
        ("catalog", "0003_university_short_name"),
        # interactions.0001_initial создаёт модели с полями, ссылающимися на старые имена
        # (catalog.itdirection/itproduct/itprogram) — оно должно выполниться до переименования,
        # иначе на чистой базе RenameModel не сможет разрешить эти ссылки.
        ("interactions", "0001_initial"),
    ]

    operations = [
        migrations.RenameModel(old_name="ITDirection", new_name="Direction"),
        migrations.RenameModel(old_name="ITProduct", new_name="Product"),
        migrations.RenameModel(old_name="ITProgram", new_name="Program"),
        migrations.RenameField(model_name="program", old_name="it_direction", new_name="direction"),
    ]
