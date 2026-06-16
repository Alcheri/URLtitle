###
# Copyright (c) 2016 - 2026, Barry Suridge
# All rights reserved.
#
#
###

import unittest
from unittest.mock import MagicMock, patch

from requests import HTTPError, RequestException, ReadTimeout

from .plugin import (
    BLOCKED_HTTP_ERROR_TITLE,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_USER_AGENT,
    URLtitle,
    YOUTUBE_PLAY_PREFIX,
)


class URLtitleTestCase(unittest.TestCase):
    def setUp(self):
        self.plugin = URLtitle(MagicMock())

    def _registry_value(self, key, channel=None, network=None):
        defaults = {
            "userAgent": "URLtitle-Test/1.0",
            "enabled": True,
            "showExpandedShortUrl": False,
            "maxUrlsPerMessage": 2,
            "cooldownSeconds": 0,
            "maxResponseBytes": DEFAULT_MAX_RESPONSE_BYTES,
        }
        return defaults[key]

    @staticmethod
    def _html_response(html, url="https://example.com"):
        response = MagicMock()
        response.headers = {"Content-Type": "text/html"}
        response.encoding = "utf-8"
        response.is_redirect = False
        response.url = url
        response.iter_content.return_value = [html.encode("utf-8")]
        response.raise_for_status.return_value = None
        return response

    def testDefaultUserAgentIsBrowserLike(self):
        self.assertTrue(DEFAULT_USER_AGENT.startswith("Mozilla/5.0"))
        self.assertIn("AppleWebKit", DEFAULT_USER_AGENT)
        self.assertIn("Safari", DEFAULT_USER_AGENT)

    @patch("URLtitle.plugin.requests.get")
    @patch("URLtitle.plugin.time.time", side_effect=[1000.0, 1001.0, 1002.0])
    def testFetchTitleUsesCache(self, mock_time, mock_get):
        mock_response = self._html_response(
            "<html><head><title>Example Domain</title></head></html>"
        )
        mock_get.return_value = mock_response

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(self.plugin, "_url_is_safe", return_value=True):
                first = self.plugin.fetch_title("https://example.com")
                second = self.plugin.fetch_title("https://example.com")

        self.assertEqual(first, "Example Domain")
        self.assertEqual(second, "Example Domain")
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["User-Agent"], "URLtitle-Test/1.0")

    @patch("URLtitle.plugin.requests.get")
    def testFetchTitleNoTitleTag(self, mock_get):
        mock_response = self._html_response(
            "<html><body>No title</body></html>",
            url="https://example.com/no-title",
        )
        mock_get.return_value = mock_response

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(self.plugin, "_url_is_safe", return_value=True):
                result = self.plugin.fetch_title(
                    "https://example.com/no-title"
                )
        self.assertEqual(
            result, "Title for https://example.com/no-title: No title found"
        )

    @patch(
        "URLtitle.plugin.requests.get", side_effect=RequestException("boom")
    )
    def testFetchTitleRequestError(self, mock_get):
        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(self.plugin, "_url_is_safe", return_value=True):
                result = self.plugin.fetch_title("https://bad.example")
        self.assertEqual(
            result,
            "Error fetching https://bad.example: RequestException",
        )

    @patch("URLtitle.plugin.requests.get", side_effect=ReadTimeout("too slow"))
    def testFetchTitleTimeoutError(self, mock_get):
        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(self.plugin, "_url_is_safe", return_value=True):
                result = self.plugin.fetch_title("https://slow.example")
        self.assertEqual(
            result,
            "Error fetching https://slow.example: request timed out after 10s",
        )

    @patch("URLtitle.plugin.requests.get")
    def testFetchTitleBlockedHttpErrorReturnsChannelMessage(self, mock_get):
        response = MagicMock()
        response.status_code = 403
        error = HTTPError(
            "403 Client Error: Blocked for url: https://old.reddit.com/"
        )
        error.response = response
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = error
        mock_response.is_redirect = False
        mock_get.return_value = mock_response

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(self.plugin, "_url_is_safe", return_value=True):
                result = self.plugin.fetch_title("https://old.reddit.com/")

        self.assertEqual(result, BLOCKED_HTTP_ERROR_TITLE)

    @patch("URLtitle.plugin.requests.get")
    def testFetchTitleForbiddenHttpErrorUsesGenericError(self, mock_get):
        response = MagicMock()
        response.status_code = 403
        error = HTTPError(
            "403 Client Error: Forbidden for url: https://www.dailymail.com/"
        )
        error.response = response
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = error
        mock_response.is_redirect = False
        mock_get.return_value = mock_response

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(self.plugin, "_url_is_safe", return_value=True):
                result = self.plugin.fetch_title("https://www.dailymail.com/")

        self.assertEqual(
            result,
            "Error fetching https://www.dailymail.com: HTTPError",
        )

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

        fake_irc.reply.assert_called_once_with(
            BLOCKED_HTTP_ERROR_TITLE, to="#chan"
        )

    def testFetchTitlePrefixesYoutubeTitle(self):
        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(
                self.plugin,
                "_fetch_youtube_title",
                return_value="Example Video - Example Channel",
            ):
                with patch.object(
                    self.plugin, "_url_is_safe", return_value=True
                ):
                    result = self.plugin.fetch_title(
                        "https://youtu.be/example"
                    )

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
        mock_response = self._html_response(
            "<html><head><title>Destination Page</title></head></html>",
            url="https://example.com/article/123",
        )
        mock_get.return_value = mock_response

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(self.plugin, "_url_is_safe", return_value=True):
                from_short = self.plugin.fetch_title(
                    "https://tinyurl.com/abcd1234"
                )
                from_resolved = self.plugin.fetch_title(
                    "https://example.com/article/123"
                )

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
                "maxUrlsPerMessage": 2,
                "cooldownSeconds": 0,
                "maxResponseBytes": DEFAULT_MAX_RESPONSE_BYTES,
            }
            return values[key]

        with patch.object(
            self.plugin, "registryValue", side_effect=registry_value
        ):
            with patch.object(
                self.plugin,
                "fetch_title",
                return_value=(
                    "Destination Page",
                    "https://example.com/article/123",
                ),
            ) as mock_fetch:
                self.plugin.doPrivmsg(fake_irc, msg)

        mock_fetch.assert_called_once_with(
            "https://tinyurl.com/abcd1234", return_resolved_url=True
        )
        fake_irc.reply.assert_called_once_with(
            "Destination Page | Expanded URL: https://example.com/article/123",
            to="#chan",
        )

    def testUrlIsSafeRejectsPrivateIpLiteral(self):
        self.assertFalse(self.plugin._url_is_safe("http://127.0.0.1/admin"))
        self.assertFalse(self.plugin._url_is_safe("http://169.254.169.254/"))

    @patch("URLtitle.plugin.requests.get")
    def testFetchTitleRejectsRedirectToPrivateIp(self, mock_get):
        redirect = MagicMock()
        redirect.is_redirect = True
        redirect.headers = {"Location": "http://127.0.0.1/admin"}
        redirect.url = "https://example.com"
        mock_get.return_value = redirect

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(
                self.plugin,
                "_url_is_safe",
                side_effect=lambda url: "127.0.0.1" not in url,
            ):
                result = self.plugin.fetch_title("https://example.com")

        self.assertIsNone(result)

    @patch("URLtitle.plugin.requests.get")
    def testFetchTitleRejectsLargeResponse(self, mock_get):
        response = self._html_response("")
        response.headers = {
            "Content-Type": "text/html",
        }
        response.iter_content.return_value = [
            b"x" * (DEFAULT_MAX_RESPONSE_BYTES + 1)
        ]
        mock_get.return_value = response

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(self.plugin, "_url_is_safe", return_value=True):
                result = self.plugin.fetch_title("https://example.com")

        self.assertIsNone(result)

    @patch("URLtitle.plugin.requests.get")
    def testFetchTitleUsesEarlyTitleFromLargeStreamingPage(self, mock_get):
        def chunks():
            yield "<html><head><title>AP News</title></head><body>".encode(
                "utf-8"
            )
            raise AssertionError("fetch_title read past the title chunk")

        response = self._html_response("", url="https://apnews.com/")
        response.headers = {
            "Content-Type": "text/html;charset=UTF-8",
            "Content-Length": "785483",
        }
        response.iter_content.side_effect = lambda chunk_size: chunks()
        mock_get.return_value = response

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(self.plugin, "_url_is_safe", return_value=True):
                result = self.plugin.fetch_title("https://apnews.com/")

        self.assertEqual(result, "AP News")

    @patch("URLtitle.plugin.requests.get")
    def testFetchTitleUsesTitleAfterOldResponseLimit(self, mock_get):
        response = self._html_response("", url="https://edition.cnn.com/")
        response.headers = {
            "Content-Type": "text/html;charset=utf-8",
            "Content-Length": "785483",
        }
        response.iter_content.return_value = [
            b" " * 300000,
            (
                b"<html><head><title>Breaking News, Latest News and "
                b"Videos | CNN</title></head>"
            ),
        ]
        mock_get.return_value = response

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(self.plugin, "_url_is_safe", return_value=True):
                result = self.plugin.fetch_title("https://edition.cnn.com/")

        self.assertEqual(result, "Breaking News, Latest News and Videos | CNN")

    def testDoPrivmsgLimitsUrlsPerMessage(self):
        msg = MagicMock()
        msg.args = [
            "#chan",
            "https://one.example https://two.example https://three.example",
        ]
        fake_irc = MagicMock()
        fake_irc.network = "testnet"

        with patch.object(
            self.plugin, "registryValue", side_effect=self._registry_value
        ):
            with patch.object(
                self.plugin,
                "fetch_title",
                return_value=("Example Domain", "https://one.example"),
            ) as mock_fetch:
                self.plugin.doPrivmsg(fake_irc, msg)

        self.assertEqual(mock_fetch.call_count, 2)

    def testReplyPreservesYoutubeColourPrefixAndStripsUnsafeControls(self):
        fake_irc = MagicMock()

        self.plugin._reply(
            fake_irc,
            "#chan",
            f"{YOUTUBE_PLAY_PREFIX}Video\x00 Title",
        )

        reply = fake_irc.reply.call_args.args[0]
        self.assertIn("\x03", reply)
        self.assertNotIn("\x00", reply)


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
