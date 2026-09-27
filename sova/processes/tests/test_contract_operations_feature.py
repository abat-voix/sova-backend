from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.core.tests.media import TemporaryMediaMixin
from sova.interactions.tests.factories import ContractFactory
from sova.processes.models import ActionFeatureExecution
from sova.processes.tests.factories import ActionInstanceFactory
from sova.workflows.tests.factories import ActionFeatureFactory


class ContractOperationsFeatureApiTestCase(TemporaryMediaMixin, APITestCase):
    """Операции workflow меняют только договоры текущего взаимодействия."""

    codes = (
        "contract.update",
        "contract.sign",
        "contract.file.upload",
        "contract.mark_sent",
        "contract.mark_corrected",
    )

    def setUp(self) -> None:
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=self.user)
        self.action_instance = ActionInstanceFactory()
        self.interaction = self.action_instance.stage_instance.workflow_instance.interaction
        for index, code in enumerate(self.codes, start=300):
            ActionFeatureFactory(
                action=self.action_instance.action,
                code=code,
                sort_order=index,
            )
        self.contract = ContractFactory(
            interaction=self.interaction,
            contract_number="Д-1",
        )
        self.base_url = (
            f"/api/processes/action-instances/{self.action_instance.pk}/features"
        )

    def execute(self, code: str, payload: dict, *, format: str = "json"):
        return self.client.post(
            f"{self.base_url}/{code}/execute/",
            payload,
            format=format,
        )

    def test_updates_number_and_contract_dates(self) -> None:
        operations = (
            ("contract.update", {"contract_number": " Д-2 "}),
            ("contract.mark_sent", {"sent_at": "2026-09-01"}),
            ("contract.mark_corrected", {"corrected_at": "2026-09-02"}),
            ("contract.sign", {"signed_at": "2026-09-03"}),
        )

        for code, fields in operations:
            response = self.execute(
                code,
                {"contract": str(self.contract.pk), **fields},
            )
            self.assertEqual(
                response.status_code,
                status.HTTP_200_OK,
                msg=response.data,
            )

        self.contract.refresh_from_db()
        self.assertEqual(self.contract.contract_number, "Д-2")
        self.assertEqual(self.contract.sent_at.isoformat(), "2026-09-01")
        self.assertEqual(self.contract.corrected_at.isoformat(), "2026-09-02")
        self.assertEqual(self.contract.signed_at.isoformat(), "2026-09-03")
        self.assertEqual(
            list(
                ActionFeatureExecution.objects.order_by("performed_at").values_list(
                    "feature_code_snapshot",
                    flat=True,
                ),
            ),
            [item[0] for item in operations],
        )

    def test_rejects_invalid_date_order(self) -> None:
        self.contract.sent_at = "2026-09-10"
        self.contract.save(update_fields=("sent_at",))

        response = self.execute(
            "contract.mark_corrected",
            {
                "contract": str(self.contract.pk),
                "corrected_at": "2026-09-09",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("corrected_at", response.data)
        self.assertFalse(
            ActionFeatureExecution.objects.filter(
                feature_code_snapshot="contract.mark_corrected",
            ).exists(),
        )

    def test_rejects_correction_before_sending_and_repeated_signing(self) -> None:
        correction = self.execute(
            "contract.mark_corrected",
            {
                "contract": str(self.contract.pk),
                "corrected_at": "2026-09-02",
            },
        )
        self.contract.signed_at = "2026-09-03"
        self.contract.save(update_fields=("signed_at",))
        signing = self.execute(
            "contract.sign",
            {
                "contract": str(self.contract.pk),
                "signed_at": "2026-09-04",
            },
        )

        self.assertEqual(correction.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(signing.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(ActionFeatureExecution.objects.exists())

    def test_initial_filters_contracts_for_signing_and_correction(self) -> None:
        self.contract.file.save(
            "current-contract.pdf",
            ContentFile(b"current contract"),
            save=False,
        )
        self.contract.file_name = "current-contract.pdf"
        self.contract.save(update_fields=("file", "file_name"))
        sent = ContractFactory(
            interaction=self.interaction,
            sent_at="2026-09-01",
        )
        ContractFactory(
            interaction=self.interaction,
            sent_at="2026-09-01",
            signed_at="2026-09-02",
        )
        ContractFactory()

        sign = self.client.get(f"{self.base_url}/contract.sign/initial/")
        corrected = self.client.get(
            f"{self.base_url}/contract.mark_corrected/initial/",
        )

        self.assertEqual(sign.status_code, status.HTTP_200_OK, msg=sign.data)
        self.assertEqual(
            {item["id"] for item in sign.data["contracts"]},
            {self.contract.pk, sent.pk},
        )
        current = next(
            item
            for item in sign.data["contracts"]
            if item["id"] == self.contract.pk
        )
        self.assertEqual(current["file_name"], "current-contract.pdf")
        self.assertEqual(
            current["download_url"],
            reverse("interactions:contract-download", args=[self.contract.pk]),
        )
        self.assertEqual(
            [item["id"] for item in corrected.data["contracts"]],
            [sent.pk],
        )

    def test_uploads_file_and_records_version(self) -> None:
        response = self.execute(
            "contract.file.upload",
            {
                "contract": str(self.contract.pk),
                "file": SimpleUploadedFile(
                    "signed-contract.pdf",
                    b"contract content",
                    content_type="application/pdf",
                ),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.file_name, "signed-contract.pdf")
        self.assertEqual(self.contract.files.count(), 1)
        self.assertEqual(self.contract.files.get().uploaded_by, self.user)
        self.assertEqual(response.data["target"]["data"]["files_count"], 1)

    def test_rejects_contract_of_another_interaction(self) -> None:
        foreign = ContractFactory()

        response = self.execute(
            "contract.update",
            {
                "contract": str(foreign.pk),
                "contract_number": "Чужой",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        foreign.refresh_from_db()
        self.assertNotEqual(foreign.contract_number, "Чужой")
