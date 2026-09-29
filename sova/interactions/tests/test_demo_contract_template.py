from io import BytesIO, StringIO
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase, override_settings
from docx import Document

from sova.interactions.models import DocumentTemplate
from sova.interactions.services.document_templates import render_contract_template
from sova.processes.action_features.handlers.contract import ContractDocumentSerializer


class DemoContractTemplateTest(TestCase):
    def test_load_and_render_with_empty_and_filled_document(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            for _ in range(2):
                call_command("load_contract_template", stdout=StringIO())
            template = DocumentTemplate.objects.get(name="Базовый договор СОВА для демонстрации")
            self.assertTrue(template.is_active)
            for extra in ({}, {
                "contract_number": "DEMO-1", "amount": "1000.00",
                "signatory": {"full_name": "Иванов Иван"},
                "directions": [{"id": "1", "name": "Разработка"}],
                "programs": [{"id": "2", "name": "Python", "direction": "Разработка"}],
                "products": [{"id": "3", "name": "Среда разработки", "program": "Python"}],
                "licenses": [{"id": "4", "product": "Среда разработки", "contract_number": "L-1",
                              "signed_at": None, "valid_until_year": 2027, "is_signed": False}],
            }):
                serializer = ContractDocumentSerializer(data={"counterparty": {"name": "Тест & проверка"}, **extra})
                serializer.is_valid(raise_exception=True)
                rendered = render_contract_template(template, serializer.data)
                text = "\n".join(p.text for p in Document(BytesIO(rendered.read())).paragraphs)
                self.assertIn("Тест & проверка", text)
                self.assertNotIn("{{", text)
                self.assertNotIn("{%", text)
                self.assertNotIn("None", text)
