from django.db import migrations, models


class Migration(migrations.Migration):
    """Переименование полей, ссылающихся на каталог: it_direction/it_program/it_product."""

    dependencies = [
        ('interactions', '0001_initial'),
        ('catalog', '0004_rename_it_models'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='interactiondirection',
            name='unique_direction_per_interaction',
        ),
        migrations.RemoveConstraint(
            model_name='interactionprogram',
            name='unique_program_per_interaction',
        ),
        migrations.RemoveConstraint(
            model_name='interactionproduct',
            name='unique_product_per_interaction',
        ),
        migrations.RenameField(
            model_name='interactiondirection',
            old_name='it_direction',
            new_name='direction',
        ),
        migrations.RenameField(
            model_name='interactionprogram',
            old_name='it_program',
            new_name='program',
        ),
        migrations.RenameField(
            model_name='interactionproduct',
            old_name='it_product',
            new_name='product',
        ),
        migrations.AddConstraint(
            model_name='interactiondirection',
            constraint=models.UniqueConstraint(
                fields=('interaction', 'direction'),
                name='unique_direction_per_interaction',
            ),
        ),
        migrations.AddConstraint(
            model_name='interactionprogram',
            constraint=models.UniqueConstraint(
                fields=('interaction', 'program'),
                name='unique_program_per_interaction',
            ),
        ),
        migrations.AddConstraint(
            model_name='interactionproduct',
            constraint=models.UniqueConstraint(
                fields=('interaction', 'product'),
                name='unique_product_per_interaction',
            ),
        ),
    ]
