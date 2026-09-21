import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Переименовывает поля it_direction/it_product/it_program в direction/product/program на моделях
    InteractionDirection/InteractionProduct/InteractionProgram — вслед за переименованием каталожных
    моделей ITDirection/ITProduct/ITProgram (catalog.0004).

    AlterField с обновлённым `to=` идёт отдельной операцией: Django-автодетектор не пробрасывает
    переименование модели другого приложения в поля, созданные более ранней миграцией.
    """

    dependencies = [
        ("interactions", "0001_initial"),
        ("catalog", "0004_rename_it_direction_it_product_it_program"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="interactiondirection",
            name="unique_direction_per_interaction",
        ),
        migrations.RenameField(
            model_name="interactiondirection",
            old_name="it_direction",
            new_name="direction",
        ),
        migrations.AlterField(
            model_name="interactiondirection",
            name="direction",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="interaction_directions",
                to="catalog.direction",
                verbose_name="ИТ-направление",
            ),
        ),
        migrations.AddConstraint(
            model_name="interactiondirection",
            constraint=models.UniqueConstraint(
                fields=("interaction", "direction"),
                name="unique_direction_per_interaction",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="interactionproduct",
            name="unique_product_per_interaction",
        ),
        migrations.RenameField(
            model_name="interactionproduct",
            old_name="it_product",
            new_name="product",
        ),
        migrations.AlterField(
            model_name="interactionproduct",
            name="product",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="interaction_products",
                to="catalog.product",
                verbose_name="ИТ-продукт",
            ),
        ),
        migrations.AddConstraint(
            model_name="interactionproduct",
            constraint=models.UniqueConstraint(
                fields=("interaction", "product"),
                name="unique_product_per_interaction",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="interactionprogram",
            name="unique_program_per_interaction",
        ),
        migrations.RenameField(
            model_name="interactionprogram",
            old_name="it_program",
            new_name="program",
        ),
        migrations.AlterField(
            model_name="interactionprogram",
            name="program",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="interaction_programs",
                to="catalog.program",
                verbose_name="ИТ-программа",
            ),
        ),
        migrations.AddConstraint(
            model_name="interactionprogram",
            constraint=models.UniqueConstraint(
                fields=("interaction", "program"),
                name="unique_program_per_interaction",
            ),
        ),
    ]
