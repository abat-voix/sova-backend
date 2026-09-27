from django.db import migrations, models


def populate_sequence_numbers(apps, schema_editor):
    Interaction = apps.get_model("interactions", "Interaction")
    rows = Interaction.objects.order_by("created_at", "id")
    for sequence_number, interaction in enumerate(rows, start=1):
        Interaction.objects.filter(pk=interaction.pk).update(sequence_number=sequence_number)


class Migration(migrations.Migration):
    dependencies = [("interactions", "0015_document_template")]

    operations = [
        migrations.AddField(
            model_name="interaction",
            name="sequence_number",
            field=models.PositiveBigIntegerField(
                editable=False,
                null=True,
                unique=True,
                verbose_name="Порядковый номер",
            ),
        ),
        migrations.RunPython(populate_sequence_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="interaction",
            name="sequence_number",
            field=models.PositiveBigIntegerField(
                editable=False,
                unique=True,
                verbose_name="Порядковый номер",
            ),
        ),
    ]
