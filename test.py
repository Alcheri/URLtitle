###
# Copyright (c) 2016 - 2026, Barry Suridge
# All rights reserved.
#
#
###

import unittest
from unittest.mock import MagicMock, patch

from requests import RequestException, ReadTimeout

from .plugin import URLtitle


class URLtitleTestCase(unittest.TestCase):
    def setUp(self):
        self.plugin = URLtitle(MagicMock())

    @patch("URLtitle.plugin.requests.get")
    @patch("URLtitle.plugin.time.time", side_effect=[1000.0, 1001.0, 1002.0])
    def testFetchTitleUsesCache(self, mock_time, mock_get):
        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Example Domain</title></head></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with patch.object(
            self.plugin, "registryValue", return_value="URLtitle-Test/1.0"
        ):
            first = self.plugin.fetch_title("https://example.com")
            second = self.plugin.fetch_title("https://example.com")

        self.assertEqual(first, "Example Domain")
        self.assertEqual(second, "Example Domain")
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["User-Agent"], "URLtitle-Test/1.0")

    @patch("URLtitle.plugin.requests.get")
    def testFetchTitleNoTitleTag(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = "<html><body>No title</body></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with patch.object(
            self.plugin, "registryValue", return_value="URLtitle-Test/1.0"
        ):
            result = self.plugin.fetch_title("https://example.com/no-title")
        self.assertEqual(
            result, "Title for https://example.com/no-title: No title found"
        )

    @patch("URLtitle.plugin.requests.get", side_effect=RequestException("boom"))
    def testFetchTitleRequestError(self, mock_get):
        with patch.object(
            self.plugin, "registryValue", return_value="URLtitle-Test/1.0"
        ):
            result = self.plugin.fetch_title("https://bad.example")
        self.assertEqual(result, "Error fetching https://bad.example: boom")

    @patch("URLtitle.plugin.requests.get", side_effect=ReadTimeout("too slow"))
    def testFetchTitleTimeoutError(self, mock_get):
        with patch.object(
            self.plugin, "registryValue", return_value="URLtitle-Test/1.0"
        ):
            result = self.plugin.fetch_title("https://slow.example")
        self.assertEqual(
            result,
            "Error fetching https://slow.example: request timed out after 10s",
        )

    def testDoPrivmsgAddsSchemeAndReplies(self):
        msg = MagicMock()
        msg.args = ["#chan", "check this out www.example.com"]
        fake_irc = MagicMock()
        fake_irc.network = "testnet"

        with patch.object(self.plugin, "registryValue", return_value=True):
            with patch.object(
                self.plugin, "fetch_title", return_value="Example Domain"
            ) as mock_fetch:
                self.plugin.doPrivmsg(fake_irc, msg)

        mock_fetch.assert_called_once_with("http://www.example.com")
        fake_irc.reply.assert_called_once_with("Example Domain", to="#chan")


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
