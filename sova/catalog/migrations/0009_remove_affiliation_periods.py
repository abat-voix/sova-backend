from django.db import migrations, models

# Модель связи → FK на организацию.
PAIRS = (
    ("UniversityContact", "university"),
    ("B2CClientContact", "b2c_client"),
    ("VendorContact", "vendor"),
)
PAIR_MESSAGE = "Это контактное лицо уже связано с этой организацией."


def keep_one_affiliation_per_pair(apps, schema_editor):
    """Из нескольких периодов пары остаётся активный, иначе последний; остальные удаляются."""
    for model_name, field in PAIRS:
        model = apps.get_model("catalog", model_name)
        seen = set()
        ordered = model.objects.order_by("contact_id", f"{field}_id", "-is_active", "-started_at", "-created_at")
        for affiliation in ordered:
            key = (affiliation.contact_id, getattr(affiliation, f"{field}_id"))
            if key in seen:
                affiliation.delete()
            else:
                seen.add(key)
    if schema_editor.connection.vendor == "postgresql":
        # Удаление связей с продуктами оставляет отложенные проверки FK, а с ними ALTER TABLE в этой же транзакции
        # невозможен («pending trigger events») — выполняем проверки сейчас.
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0008_contact_affiliations"),
    ]

    operations = [
        migrations.RunPython(keep_one_affiliation_per_pair, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="universitycontact", name="unique_active_university_contact"),
        migrations.RemoveConstraint(model_name="universitycontact", name="university_contact_ended_after_started"),
        migrations.RemoveConstraint(model_name="b2cclientcontact", name="unique_active_b2c_client_contact"),
        migrations.RemoveConstraint(model_name="b2cclientcontact", name="b2c_client_contact_ended_after_started"),
        migrations.RemoveConstraint(model_name="vendorcontact", name="unique_active_vendor_contact"),
        migrations.RemoveConstraint(model_name="vendorcontact", name="vendor_contact_ended_after_started"),
        migrations.RemoveField(model_name="universitycontact", name="is_active"),
        migrations.RemoveField(model_name="universitycontact", name="started_at"),
        migrations.RemoveField(model_name="universitycontact", name="ended_at"),
        migrations.RemoveField(model_name="b2cclientcontact", name="is_active"),
        migrations.RemoveField(model_name="b2cclientcontact", name="started_at"),
        migrations.RemoveField(model_name="b2cclientcontact", name="ended_at"),
        migrations.RemoveField(model_name="vendorcontact", name="is_active"),
        migrations.RemoveField(model_name="vendorcontact", name="started_at"),
        migrations.RemoveField(model_name="vendorcontact", name="ended_at"),
        migrations.AlterModelOptions(
            name="universitycontact",
            options={"ordering": ["contact__full_name"], "verbose_name": "Связь с вузом", "verbose_name_plural": "Связи с вузами"},
        ),
        migrations.AlterModelOptions(
            name="b2cclientcontact",
            options={
                "ordering": ["contact__full_name"],
                "verbose_name": "Связь с B2C-клиентом",
                "verbose_name_plural": "Связи с B2C-клиентами",
            },
        ),
        migrations.AlterModelOptions(
            name="vendorcontact",
            options={"ordering": ["contact__full_name"], "verbose_name": "Связь с вендором", "verbose_name_plural": "Связи с вендорами"},
        ),
        migrations.AddConstraint(
            model_name="universitycontact",
            constraint=models.UniqueConstraint(
                fields=("contact", "university"), name="unique_university_contact", violation_error_message=PAIR_MESSAGE
            ),
        ),
        migrations.AddConstraint(
            model_name="b2cclientcontact",
            constraint=models.UniqueConstraint(
                fields=("contact", "b2c_client"), name="unique_b2c_client_contact", violation_error_message=PAIR_MESSAGE
            ),
        ),
        migrations.AddConstraint(
            model_name="vendorcontact",
            constraint=models.UniqueConstraint(
                fields=("contact", "vendor"), name="unique_vendor_contact", violation_error_message=PAIR_MESSAGE
            ),
        ),
    ]
