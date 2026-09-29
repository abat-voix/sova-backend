from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Преподаватель работает в организации (бывший вуз) либо у B2C-клиента. Проверка «ровно одно место работы»
    снимается до переименования и создаётся заново после, чтобы миграция откатывалась.
    """

    dependencies = [
        ("catalog", "0012_rename_university_to_organization"),
        ("training", "0001_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="traininginstructor",
            name="training_instructor_exactly_one_organization",
        ),
        migrations.RenameField(model_name="traininginstructor", old_name="university", new_name="organization"),
        migrations.AddConstraint(
            model_name="traininginstructor",
            constraint=models.CheckConstraint(
                condition=models.Q(organization__isnull=False, b2c_client__isnull=True)
                | models.Q(organization__isnull=True, b2c_client__isnull=False),
                name="training_instructor_exactly_one_organization",
            ),
        ),
    ]
