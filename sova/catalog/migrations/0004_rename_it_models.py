from django.db import migrations


class Migration(migrations.Migration):
    """Переименование моделей каталога: ITDirection/ITProgram/ITProduct без потери данных."""

    dependencies = [
        ('catalog', '0003_university_short_name'),
        # Переименование должно идти после создания ссылающихся на каталог таблиц,
        # иначе interactions.0001 не найдёт catalog.itdirection.
        ('interactions', '0001_initial'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='ITDirection',
            new_name='Direction',
        ),
        migrations.RenameModel(
            old_name='ITProgram',
            new_name='Program',
        ),
        migrations.RenameModel(
            old_name='ITProduct',
            new_name='Product',
        ),
        migrations.RenameField(
            model_name='program',
            old_name='it_direction',
            new_name='direction',
        ),
    ]
