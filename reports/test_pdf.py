from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from reports.pdf import HTMLAsset, PDFGenerationError, html_to_pdf


@override_settings(GOTENBERG_URL="http://gotenberg:3000", GOTENBERG_TIMEOUT=15)
class HTMLToPDFTests(SimpleTestCase):
    @patch("reports.pdf.requests.post")
    def test_sends_html_assets_and_print_defaults_to_gotenberg(self, post: Mock) -> None:
        post.return_value.status_code = 200
        post.return_value.content = b"%PDF-1.7\nresult"

        result = html_to_pdf(
            "<html><body><img src='logo.png'></body></html>",
            assets=(HTMLAsset("logo.png", b"image", "image/png"),),
            output_filename="quarterly-report",
        )

        self.assertEqual(result, b"%PDF-1.7\nresult")
        request = post.call_args
        self.assertEqual(
            request.args[0],
            "http://gotenberg:3000/forms/chromium/convert/html",
        )
        self.assertEqual(request.kwargs["timeout"], 15)
        self.assertEqual(
            request.kwargs["headers"],
            {"Gotenberg-Output-Filename": "quarterly-report"},
        )
        self.assertEqual(
            [file_data[1][0] for file_data in request.kwargs["files"]],
            ["index.html", "logo.png"],
        )
        self.assertEqual(request.kwargs["data"]["paperWidth"], "8.27in")
        self.assertEqual(request.kwargs["data"]["paperHeight"], "11.7in")
        self.assertEqual(request.kwargs["data"]["printBackground"], "true")

    @patch("reports.pdf.requests.post")
    def test_allows_conversion_fields_to_be_overridden(self, post: Mock) -> None:
        post.return_value.status_code = 200
        post.return_value.content = b"%PDF-1.7\nresult"

        html_to_pdf(
            "<html></html>",
            form_fields={"landscape": True, "waitDelay": "250ms"},
        )

        self.assertEqual(post.call_args.kwargs["data"]["landscape"], "true")
        self.assertEqual(post.call_args.kwargs["data"]["waitDelay"], "250ms")

    @patch("reports.pdf.requests.post")
    def test_wraps_connection_errors(self, post: Mock) -> None:
        post.side_effect = requests.ConnectionError("connection refused")

        with self.assertRaisesRegex(PDFGenerationError, "connect to Gotenberg"):
            html_to_pdf("<html></html>")

    @patch("reports.pdf.requests.post")
    def test_includes_bounded_error_response(self, post: Mock) -> None:
        post.return_value.status_code = 400
        post.return_value.text = "invalid HTML"

        with self.assertRaisesRegex(PDFGenerationError, "HTTP 400: invalid HTML"):
            html_to_pdf("<html></html>")

    @patch("reports.pdf.requests.post")
    def test_rejects_non_pdf_success_response(self, post: Mock) -> None:
        post.return_value.status_code = 200
        post.return_value.content = b"unexpected"

        with self.assertRaisesRegex(PDFGenerationError, "not a PDF"):
            html_to_pdf("<html></html>")


class HTMLAssetTests(SimpleTestCase):
    def test_rejects_reserved_filename(self) -> None:
        with self.assertRaises(ValueError):
            HTMLAsset("index.html", b"duplicate")

    def test_rejects_parent_path(self) -> None:
        with self.assertRaises(ValueError):
            HTMLAsset("../secret.txt", b"secret")

    def test_rejects_windows_parent_path(self) -> None:
        with self.assertRaises(ValueError):
            HTMLAsset("..\\secret.txt", b"secret")

    def test_rejects_duplicate_asset_filenames(self) -> None:
        asset = HTMLAsset("styles.css", b"body {}", "text/css")

        with self.assertRaisesRegex(ValueError, "unique"):
            html_to_pdf("<html></html>", assets=(asset, asset))

    def test_rejects_output_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "path separators"):
            html_to_pdf("<html></html>", output_filename="reports/quarterly")
