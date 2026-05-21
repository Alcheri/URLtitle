###
# Copyright (c) 2016 - 2026, Barry Suridge
# All rights reserved.
#
#
###

import re
import json
import socket
import threading
import time
from ipaddress import ip_address
from urllib.parse import urljoin, urlparse

import requests
from requests import HTTPError, RequestException, Timeout

try:
    from bs4 import BeautifulSoup
except ImportError as ie:
    raise ImportError(f"Cannot import module: {ie}")

import supybot.ircutils as ircutils
from supybot import callbacks
from supybot.i18n import PluginInternationalization

_ = PluginInternationalization("URLtitle")

DEFAULT_USER_AGENT = (
    "Limnoria-URLtitle/1.0 (+https://github.com/Alcheri/URLtitle)"
)
URL_PATTERN = re.compile(r"(https?://\S+|www\.\S+)")
CACHE_TTL_SECONDS = 600
REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_MAX_RESPONSE_BYTES = 262144
MAX_TITLE_LENGTH = 400
MAX_REPLY_LENGTH = 500
MAX_REDIRECTS = 3
UNSAFE_CONTROL_CHARS_RE = re.compile(
    r"[\x00-\x01\x04-\x0e\x10-\x15\x17-\x1c\x1e\x7f]"
)
WHITESPACE_RE = re.compile(r"\s+")
HTML_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
)
BLOCKED_HTTP_ERROR_TITLE = (
    "Title: Error retrieving title. 403 Client Error: Blocked for URL."
)
YOUTUBE_HOSTS = (
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "m.youtube.com",
)
YOUTUBE_OEMBED_URL = "https://www.youtube.com/oembed"
YOUTUBE_PLAY_PREFIX = f"{ircutils.mircColor('▶', 'red')} "

SUPPORTED_SHORTENER_HOSTS = (
    "bit.ly",
    "www.bit.ly",
    "tinyurl.com",
    "www.tinyurl.com",
    "minily.me",
    "www.minily.me",
)


class URLtitle(callbacks.Plugin):
    """
    Automatically detects URLs in messages and replies with the website title, with caching.
    """

    threaded = True

    def __init__(self, irc):
        self.__parent = super(URLtitle, self)
        self.__parent.__init__(irc)
        self.cache = {}  # Simple cache for storing URL titles
        self._cooldowns = {}
        self._cooldown_lock = threading.Lock()

    def _request_headers(self):
        return {"User-Agent": self.registryValue("userAgent")}

    def _clean_text(self, value, max_length=None, preserve_formatting=True):
        text = str(value or "")
        if not preserve_formatting:
            text = ircutils.stripFormatting(text)
        text = UNSAFE_CONTROL_CHARS_RE.sub(" ", text)
        text = WHITESPACE_RE.sub(" ", text).strip()
        if max_length is not None and len(text) > max_length:
            return f"{text[: max(0, max_length - 3)].rstrip()}..."
        return text

    def _safe_log_text(self, value):
        return self._clean_text(
            value, max_length=120, preserve_formatting=False
        )

    def _safe_url_for_log(self, url):
        try:
            parsed = urlparse(url)
        except ValueError:
            return "<invalid-url>"
        host = parsed.hostname or "<unknown-host>"
        return self._safe_log_text(f"{parsed.scheme}://{host}")

    def _max_response_bytes(self):
        try:
            value = int(self.registryValue("maxResponseBytes"))
        except (TypeError, ValueError):
            return DEFAULT_MAX_RESPONSE_BYTES
        return max(1024, min(value, DEFAULT_MAX_RESPONSE_BYTES))

    def _normalise_url(self, url):
        cleaned = self._clean_text(url, max_length=2048)
        cleaned = cleaned.rstrip(".,;:!?)\"]}'")
        if cleaned.startswith("www."):
            cleaned = "http://" + cleaned
        return cleaned

    def _ip_is_safe(self, address):
        try:
            ip = ip_address(address)
        except ValueError:
            return False
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )

    def _host_is_safe(self, hostname):
        if not hostname:
            return False

        try:
            return self._ip_is_safe(str(ip_address(hostname)))
        except ValueError:
            pass

        try:
            results = socket.getaddrinfo(hostname, None)
        except OSError:
            return False

        addresses = {result[4][0] for result in results if result[4]}
        if not addresses:
            return False
        return all(self._ip_is_safe(address) for address in addresses)

    def _url_is_safe(self, url):
        try:
            parsed = urlparse(url)
        except ValueError:
            return False

        if parsed.scheme not in ("http", "https"):
            return False
        if not parsed.hostname:
            return False
        return self._host_is_safe(parsed.hostname)

    def _content_type_is_html(self, response):
        content_type = response.headers.get("Content-Type", "")
        content_type = content_type.split(";", 1)[0].strip().lower()
        return any(
            content_type.startswith(expected)
            for expected in HTML_CONTENT_TYPES
        )

    def _read_limited_response(self, response, max_bytes):
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    return None
            except ValueError:
                pass

        content = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            content.extend(chunk)
            if len(content) > max_bytes:
                return None
        encoding = response.encoding or "utf-8"
        return bytes(content).decode(encoding, errors="replace")

    def _cooldown_remaining(self, irc, msg, channel):
        cooldown = self.registryValue("cooldownSeconds", channel, irc.network)
        if not cooldown:
            return 0

        cooldown = max(0, int(cooldown))
        if cooldown <= 0:
            return 0

        now = time.monotonic()
        key = (irc.network, channel, msg.prefix)
        with self._cooldown_lock:
            expired = [
                item
                for item, last_seen in self._cooldowns.items()
                if now - last_seen >= cooldown
            ]
            for item in expired:
                del self._cooldowns[item]

            last_seen = self._cooldowns.get(key)
            if last_seen is None or now - last_seen >= cooldown:
                self._cooldowns[key] = now
                return 0
            return max(1, int(cooldown - (now - last_seen)))

    def _reply(self, irc, channel, text):
        irc.reply(
            self._clean_text(text, max_length=MAX_REPLY_LENGTH),
            to=channel,
        )

    def _hostname_for_url(self, url):
        try:
            parsed = urlparse(url)
        except ValueError:
            return ""
        return (parsed.hostname or "").lower()

    def _is_supported_shortener_url(self, url):
        return self._hostname_for_url(url) in SUPPORTED_SHORTENER_HOSTS

    def _is_youtube_url(self, url):
        return self._hostname_for_url(url) in YOUTUBE_HOSTS

    def _fetch_youtube_title(self, url):
        """Use YouTube's oEmbed API to get the real video title."""
        if not self._url_is_safe(url):
            self.log.debug(
                "Blocked unsafe YouTube URL: %s", self._safe_url_for_log(url)
            )
            return None

        try:
            response = requests.get(
                YOUTUBE_OEMBED_URL,
                params={"url": url, "format": "json"},
                headers=self._request_headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
                stream=True,
            )
            response.raise_for_status()
            body = self._read_limited_response(
                response, self._max_response_bytes()
            )
            if body is None:
                self.log.debug("YouTube oEmbed response exceeded size limit.")
                return None
            data = json.loads(body)
            title = self._clean_text(data.get("title", ""), MAX_TITLE_LENGTH)
            author = self._clean_text(
                data.get("author_name", ""), MAX_TITLE_LENGTH
            )
            if title and author:
                return f"{title} - {author}"
            return title or None
        except (RequestException, ValueError) as e:
            self.log.debug(
                "YouTube oEmbed failed for %s: %s",
                self._safe_url_for_log(url),
                e.__class__.__name__,
            )
            return None

    def _format_request_error(self, url, error):
        if isinstance(error, Timeout):
            return (
                f"Error fetching {self._safe_url_for_log(url)}: request timed out after "
                f"{REQUEST_TIMEOUT_SECONDS}s"
            )

        return (
            f"Error fetching {self._safe_url_for_log(url)}: "
            f"{error.__class__.__name__}"
        )

    def _is_blocked_http_error(self, error):
        if not isinstance(error, HTTPError):
            return False
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code == 403:
            return True
        return str(error).strip().startswith("403 Client Error: Blocked")

    def fetch_title(self, url, return_resolved_url=False):
        url = self._normalise_url(url)
        if not self._url_is_safe(url):
            self.log.debug(
                "Blocked unsafe URL: %s", self._safe_url_for_log(url)
            )
            if return_resolved_url:
                return None, url
            return None

        # Check the cache first to avoid duplicate network calls.
        if url in self.cache:
            cached = self.cache[url]
            if len(cached) == 3:
                title, timestamp, resolved_url = cached
            else:
                title, timestamp = cached
                resolved_url = url
            if time.time() - timestamp < CACHE_TTL_SECONDS:
                if return_resolved_url:
                    return title, resolved_url
                return title

        # Use YouTube oEmbed API to bypass bot-detection pages.
        if self._is_youtube_url(url):
            yt_title = self._fetch_youtube_title(url)
            if yt_title:
                yt_title = f"{YOUTUBE_PLAY_PREFIX}{yt_title}"
                self.cache[url] = (yt_title, time.time(), url)
                if return_resolved_url:
                    return yt_title, url
                return yt_title

        try:
            current_url = url
            response = None
            for _redirect_count in range(MAX_REDIRECTS + 1):
                if not self._url_is_safe(current_url):
                    self.log.debug(
                        "Blocked unsafe URL: %s",
                        self._safe_url_for_log(current_url),
                    )
                    if return_resolved_url:
                        return None, current_url
                    return None
                response = requests.get(
                    current_url,
                    headers=self._request_headers(),
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    allow_redirects=False,
                    stream=True,
                )
                if response.is_redirect:
                    location = response.headers.get("Location")
                    if not location:
                        break
                    current_url = urljoin(current_url, location)
                    continue
                break
            else:
                self.log.debug(
                    "URL fetch exceeded redirect limit for %s",
                    self._safe_url_for_log(url),
                )
                if return_resolved_url:
                    return None, url
                return None

            if response is None:
                if return_resolved_url:
                    return None, url
                return None

            response.raise_for_status()
            resolved_url = url
            response_url = getattr(response, "url", None)
            if isinstance(response_url, str) and response_url:
                resolved_url = self._normalise_url(response_url)
            if resolved_url == url and response.url != url:
                resolved_url = self._normalise_url(response.url)
            if not self._url_is_safe(resolved_url):
                self.log.debug(
                    "Blocked unsafe resolved URL: %s",
                    self._safe_url_for_log(resolved_url),
                )
                if return_resolved_url:
                    return None, resolved_url
                return None
            if self._is_supported_shortener_url(url) and resolved_url != url:
                self.log.debug(
                    "Resolved short URL %s -> %s",
                    self._safe_url_for_log(url),
                    self._safe_url_for_log(resolved_url),
                )

            if not self._content_type_is_html(response):
                self.log.debug(
                    "URL fetch returned non-HTML content for %s",
                    self._safe_url_for_log(resolved_url),
                )
                if return_resolved_url:
                    return None, resolved_url
                return None

            html = self._read_limited_response(
                response, self._max_response_bytes()
            )
            if html is None:
                self.log.debug(
                    "URL fetch response exceeded size limit for %s",
                    self._safe_url_for_log(resolved_url),
                )
                if return_resolved_url:
                    return None, resolved_url
                return None

            # Parse the HTML and extract the title
            soup = BeautifulSoup(html, "html.parser")
            title_tag = soup.find("title")

            if title_tag:
                formatted_title = self._clean_text(
                    title_tag.get_text(strip=True), MAX_TITLE_LENGTH
                )
            else:
                formatted_title = f"Title for {resolved_url}: No title found"

            # Update the cache
            cache_timestamp = time.time()
            self.cache[url] = (formatted_title, cache_timestamp, resolved_url)
            if resolved_url != url:
                self.cache[resolved_url] = (
                    formatted_title,
                    cache_timestamp,
                    resolved_url,
                )
            if return_resolved_url:
                return formatted_title, resolved_url
            return formatted_title
        except RequestException as e:
            if self._is_blocked_http_error(e):
                self.log.debug(
                    "URL fetch blocked for %s: %s",
                    self._safe_url_for_log(url),
                    e.__class__.__name__,
                )
                if return_resolved_url:
                    return BLOCKED_HTTP_ERROR_TITLE, url
                return BLOCKED_HTTP_ERROR_TITLE
            self.log.error(
                "Error fetching %s: %s",
                self._safe_url_for_log(url),
                e.__class__.__name__,
            )
            error_text = self._format_request_error(url, e)
            if return_resolved_url:
                return error_text, url
            return error_text

    def doPrivmsg(self, irc, msg):
        """
        Triggered when a message is sent in a channel.
        """
        channel = msg.args[0]
        if not self.registryValue("enabled", channel, irc.network):
            return
        text = msg.args[1]
        cooldown = self._cooldown_remaining(irc, msg, channel)
        if cooldown:
            return

        max_urls = self.registryValue(
            "maxUrlsPerMessage", channel, irc.network
        )
        urls = URL_PATTERN.findall(text)[: max(1, int(max_urls))]

        if urls:
            for url in urls:
                url = self._normalise_url(url)

                title, resolved_url = self.fetch_title(
                    url, return_resolved_url=True
                )
                show_expanded = self.registryValue(
                    "showExpandedShortUrl", channel, irc.network
                )
                if (
                    title
                    and show_expanded
                    and self._is_supported_shortener_url(url)
                ):
                    if resolved_url and resolved_url != url:
                        self._reply(
                            irc,
                            channel,
                            f"{title} | Expanded URL: {resolved_url}",
                        )
                        continue

                if title:
                    self._reply(irc, channel, title)


Class = URLtitle


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
