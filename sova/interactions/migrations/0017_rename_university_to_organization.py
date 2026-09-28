from django.db import migrations, models

COUNTERPARTY = models.Q(organization__isnull=False, b2c_client__isnull=True) | models.Q(
    organization__isnull=True, b2c_client__isnull=False
)


class Migration(migrations.Migration):
    """
    Контрагент-вуз взаимодействия и договора теперь — организация. Проверка «ровно один контрагент» снимается
    до переименования и создаётся заново после, чтобы миграция откатывалась.
    """

    dependencies = [
        ("catalog", "0012_rename_university_to_organization"),
        ("interactions", "0016_interaction_sequence_number"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="contract", name="contract_exactly_one_counterparty"),
        migrations.RemoveConstraint(model_name="interaction", name="interaction_exactly_one_counterparty"),
        migrations.RenameField(model_name="interaction", old_name="university", new_name="organization"),
        migrations.RenameField(model_name="contract", old_name="university", new_name="organization"),
        migrations.AddConstraint(
            model_name="contract",
            constraint=models.CheckConstraint(condition=COUNTERPARTY, name="contract_exactly_one_counterparty"),
        ),
        migrations.AddConstraint(
            model_name="interaction",
            constraint=models.CheckConstraint(condition=COUNTERPARTY, name="interaction_exactly_one_counterparty"),
        ),
    ]
