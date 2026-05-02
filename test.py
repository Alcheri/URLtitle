###
# Copyright (c) 2016 - 2026, Barry Suridge
# All rights reserved.
#
#
###

import unittest
from unittest.mock import MagicMock, patch

from requests import HTTPError, RequestException, ReadTimeout

from .plugin import BLOCKED_HTTP_ERROR_TITLE, URLtitle, YOUTUBE_PLAY_PREFIX


class URLtitleTestCase(unittest.TestCase):
    def setUp(self):
        self.plugin = URLtitle(MagicMock())

    def _registry_value(self, key, channel=None, network=None):
        defaults = {
            "userAgent": "URLtitle-Test/1.0",
            "enabled": True,
            "showExpandedShortUrl": False,
        }
        return defaults[key]

    @patch("URLtitle.plugin.requests.get")
    @patch("URLtitle.plugin.time.time", side_effect=[1000.0, 1001.0, 1002.0])
    def testFetchTitleUsesCache(self, mock_time, mock_get):
        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Example Domain</title></head></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
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
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            result = self.plugin.fetch_title("https://example.com/no-title")
        self.assertEqual(
            result, "Title for https://example.com/no-title: No title found"
        )

    @patch("URLtitle.plugin.requests.get", side_effect=RequestException("boom"))
    def testFetchTitleRequestError(self, mock_get):
        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            result = self.plugin.fetch_title("https://bad.example")
        self.assertEqual(result, "Error fetching https://bad.example: boom")

    @patch("URLtitle.plugin.requests.get", side_effect=ReadTimeout("too slow"))
    def testFetchTitleTimeoutError(self, mock_get):
        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            result = self.plugin.fetch_title("https://slow.example")
        self.assertEqual(
            result,
            "Error fetching https://slow.example: request timed out after 10s",
        )

    @patch("URLtitle.plugin.requests.get")
    def testFetchTitleBlockedHttpErrorReturnsChannelMessage(self, mock_get):
        response = MagicMock()
        response.status_code = 403
        error = HTTPError("403 Client Error: Blocked for url: https://old.reddit.com/")
        error.response = response
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = error
        mock_get.return_value = mock_response

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            result = self.plugin.fetch_title("https://old.reddit.com/")

        self.assertEqual(result, BLOCKED_HTTP_ERROR_TITLE)

    def testDoPrivmsgRepliesWhenFetchIsBlocked(self):
        msg = MagicMock()
        msg.args = ["#chan", "https://old.reddit.com/r/example/"]
        fake_irc = MagicMock()
        fake_irc.network = "testnet"

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(
                self.plugin,
                "fetch_title",
                return_value=(
                    BLOCKED_HTTP_ERROR_TITLE,
                    "https://old.reddit.com/r/example/",
                ),
            ):
                self.plugin.doPrivmsg(fake_irc, msg)

        fake_irc.reply.assert_called_once_with(BLOCKED_HTTP_ERROR_TITLE, to="#chan")

    def testFetchTitlePrefixesYoutubeTitle(self):
        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(
                self.plugin,
                "_fetch_youtube_title",
                return_value="Example Video - Example Channel",
            ):
                result = self.plugin.fetch_title("https://youtu.be/example")

        self.assertEqual(
            result, f"{YOUTUBE_PLAY_PREFIX}Example Video - Example Channel"
        )

    def testDoPrivmsgAddsSchemeAndReplies(self):
        msg = MagicMock()
        msg.args = ["#chan", "check this out www.example.com"]
        fake_irc = MagicMock()
        fake_irc.network = "testnet"

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(
                self.plugin,
                "fetch_title",
                return_value=("Example Domain", "http://www.example.com"),
            ) as mock_fetch:
                self.plugin.doPrivmsg(fake_irc, msg)

        mock_fetch.assert_called_once_with(
            "http://www.example.com", return_resolved_url=True
        )
        fake_irc.reply.assert_called_once_with("Example Domain", to="#chan")

    @patch("URLtitle.plugin.requests.get")
    @patch("URLtitle.plugin.time.time", side_effect=[1000.0, 1001.0, 1002.0])
    def testFetchTitleResolvesKnownShortenerAndCachesResolvedUrl(
        self, mock_time, mock_get
    ):
        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Destination Page</title></head></html>"
        mock_response.raise_for_status.return_value = None
        mock_response.url = "https://example.com/article/123"
        mock_get.return_value = mock_response

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            from_short = self.plugin.fetch_title("https://tinyurl.com/abcd1234")
            from_resolved = self.plugin.fetch_title("https://example.com/article/123")

        self.assertEqual(from_short, "Destination Page")
        self.assertEqual(from_resolved, "Destination Page")
        mock_get.assert_called_once()

    def testDoPrivmsgCanShowExpandedShortUrl(self):
        msg = MagicMock()
        msg.args = ["#chan", "https://tinyurl.com/abcd1234"]
        fake_irc = MagicMock()
        fake_irc.network = "testnet"

        def registry_value(key, channel=None, network=None):
            values = {
                "enabled": True,
                "showExpandedShortUrl": True,
                "userAgent": "URLtitle-Test/1.0",
            }
            return values[key]

        with patch.object(self.plugin, "registryValue", side_effect=registry_value):
            with patch.object(
                self.plugin,
                "fetch_title",
                return_value=("Destination Page", "https://example.com/article/123"),
            ) as mock_fetch:
                self.plugin.doPrivmsg(fake_irc, msg)

        mock_fetch.assert_called_once_with(
            "https://tinyurl.com/abcd1234", return_resolved_url=True
        )
        fake_irc.reply.assert_called_once_with(
            "Destination Page | Expanded URL: https://example.com/article/123",
            to="#chan",
        )


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
