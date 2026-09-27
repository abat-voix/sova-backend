import asyncio
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from sova.realtime.healthcheck import _check_channel_layer, _check_http


class RealtimeHealthcheckTestCase(SimpleTestCase):
    @patch("sova.realtime.healthcheck.urllib.request.urlopen")
    def test_http_probe_requires_healthy_api_response(self, urlopen) -> None:
        response = MagicMock()
        response.status = 200
        response.__enter__.return_value = response
        response.read.return_value = b'{"status":"ok"}'
        urlopen.return_value = response

        _check_http()

        urlopen.assert_called_once()

    @patch("sova.realtime.healthcheck.urllib.request.urlopen")
    def test_http_probe_fails_when_api_reports_unhealthy(self, urlopen) -> None:
        response = MagicMock()
        response.status = 503
        response.__enter__.return_value = response
        urlopen.return_value = response

        with self.assertRaises(RuntimeError):
            _check_http()

    @override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
    def test_channel_probe_round_trips_through_configured_layer(self) -> None:
        asyncio.run(_check_channel_layer())
