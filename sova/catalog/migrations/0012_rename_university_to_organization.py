import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Вуз становится организацией: тип организации (`organization_type`) определяет, вуз это или нет.

    Ограничения со старыми именами снимаются до переименования и создаются заново после — так миграция
    откатывается: ограничение со ссылкой на `university` возвращается, когда поле ещё так называется.
    """

    dependencies = [
        ("catalog", "0011_alter_catalogimportmapping_catalog_type"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="university", name="unique_university_name_ci"),
        migrations.RemoveConstraint(model_name="university", name="unique_university_external_code_ci"),
        migrations.RemoveConstraint(model_name="universitycontact", name="unique_university_contact"),
        migrations.RenameModel(old_name="University", new_name="Organization"),
        migrations.RenameModel(old_name="UniversityContact", new_name="OrganizationContact"),
        migrations.RenameField(model_name="organizationcontact", old_name="university", new_name="organization"),
        migrations.RenameField(model_name="organization", old_name="institution_type", new_name="organization_type"),
        migrations.AddConstraint(
            model_name="organization",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"),
                name="unique_organization_name_ci",
                violation_error_message="Организация с таким названием уже существует.",
            ),
        ),
        migrations.AddConstraint(
            model_name="organization",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("external_code"),
                name="unique_organization_external_code_ci",
                violation_error_message="Организация с таким внешним идентификатором уже существует.",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationcontact",
            constraint=models.UniqueConstraint(
                fields=("contact", "organization"),
                name="unique_organization_contact",
                violation_error_message="Это контактное лицо уже связано с этой организацией.",
            ),
        ),
    ]
