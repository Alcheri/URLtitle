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
from html import unescape
from datetime import datetime
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
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
URL_PATTERN = re.compile(r"(https?://\S+|www\.\S+)")
CACHE_TTL_SECONDS = 600
REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_MAX_RESPONSE_BYTES = 1048576
YOUTUBE_METADATA_MAX_RESPONSE_BYTES = 1048576
YOUTUBE_METADATA_TIMEOUT_SECONDS = 3
YOUTUBE_METADATA_READ_SECONDS = 3
MAX_TITLE_LENGTH = 400
MAX_REPLY_LENGTH = 500
MAX_REDIRECTS = 3
UNSAFE_CONTROL_CHARS_RE = re.compile(
    r"[\x00-\x01\x04-\x0e\x10-\x15\x17-\x1c\x1e\x7f]"
)
WHITESPACE_RE = re.compile(r"\s+")
TITLE_RE = re.compile(
    r"<title\b[^>]*>(.*?)</title\s*>", re.IGNORECASE | re.DOTALL
)
YOUTUBE_ISO_DURATION_RE = re.compile(
    r"^P(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$"
)
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
        self._cache_lock = threading.Lock()
        self._cooldowns = {}
        self._cooldown_lock = threading.Lock()
        self._session_local = threading.local()
        self._sessions = set()
        self._sessions_lock = threading.Lock()

    def die(self):
        with self._sessions_lock:
            sessions = list(self._sessions)
            self._sessions.clear()
        for session in sessions:
            session.close()
        self.__parent.die()

    def _http_session(self):
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = requests.Session()
            self._session_local.session = session
            with self._sessions_lock:
                self._sessions.add(session)
        return session

    def _http_get(self, *args, **kwargs):
        session = self._http_session()
        session.cookies.clear()
        try:
            return session.get(*args, **kwargs)
        finally:
            session.cookies.clear()

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

    def _read_partial_response(self, response, max_bytes, max_seconds=None):
        content = bytearray()
        deadline = None
        if max_seconds is not None:
            deadline = time.monotonic() + max_seconds

        for chunk in response.iter_content(chunk_size=8192):
            if deadline is not None and time.monotonic() >= deadline:
                break
            if not chunk:
                continue
            remaining = max_bytes - len(content)
            if remaining <= 0:
                break
            content.extend(chunk[:remaining])
            if len(content) >= max_bytes:
                break
        encoding = response.encoding or "utf-8"
        return bytes(content).decode(encoding, errors="replace")

    def _title_from_html(self, html):
        match = TITLE_RE.search(html)
        if not match:
            return None
        return self._clean_text(unescape(match.group(1)), MAX_TITLE_LENGTH)

    def _get_cached_title(self, url):
        with self._cache_lock:
            cached = self.cache.get(url)
        if not cached:
            return None
        if len(cached) == 3:
            title, timestamp, resolved_url = cached
        else:
            title, timestamp = cached
            resolved_url = url
        if time.time() - timestamp >= CACHE_TTL_SECONDS:
            return None
        return title, resolved_url

    def _store_cached_title(self, url, title, resolved_url):
        cache_timestamp = time.time()
        with self._cache_lock:
            self.cache[url] = (title, cache_timestamp, resolved_url)
            if resolved_url != url:
                self.cache[resolved_url] = (
                    title,
                    cache_timestamp,
                    resolved_url,
                )

    def _extract_title_from_response(self, response, max_bytes, resolved_url):
        content = bytearray()
        encoding = response.encoding or "utf-8"
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            content.extend(chunk)
            if len(content) > max_bytes:
                return None

            html = bytes(content).decode(encoding, errors="replace")
            title = self._title_from_html(html)
            if title:
                return title

        html = bytes(content).decode(encoding, errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        if title_tag:
            return self._clean_text(
                title_tag.get_text(strip=True), MAX_TITLE_LENGTH
            )

        return f"Title for {resolved_url}: No title found"

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
            response = self._http_get(
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

    def _metadata_value_from_ld_json(self, value, key):
        if isinstance(value, dict):
            if key in value:
                return value[key]
            for child in value.values():
                result = self._metadata_value_from_ld_json(child, key)
                if result:
                    return result
        if isinstance(value, list):
            for item in value:
                result = self._metadata_value_from_ld_json(item, key)
                if result:
                    return result
        return None

    def _youtube_meta_content(self, soup, *names):
        for name in names:
            tag = soup.find("meta", attrs={"itemprop": name})
            if tag and tag.get("content"):
                return tag["content"]
            tag = soup.find("meta", attrs={"property": name})
            if tag and tag.get("content"):
                return tag["content"]
        return None

    def _format_youtube_upload_date(self, value):
        if not value:
            return None
        text = self._clean_text(value, max_length=32)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
        day = str(int(parsed.strftime("%d")))
        return f"{day} {parsed.strftime('%b %Y')}"

    def _format_youtube_duration(self, value):
        if not value:
            return None
        text = self._clean_text(value, max_length=32)
        try:
            total_seconds = int(text)
        except (TypeError, ValueError):
            match = YOUTUBE_ISO_DURATION_RE.match(text)
            if not match:
                return None
            hours, minutes, seconds = (
                int(part or 0) for part in match.groups()
            )
            total_seconds = (hours * 3600) + (minutes * 60) + seconds
        if total_seconds <= 0:
            return None
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def _youtube_initial_player_response(self, body):
        marker = "ytInitialPlayerResponse"
        index = 0
        decoder = json.JSONDecoder()
        while True:
            index = body.find(marker, index)
            if index == -1:
                return None
            json_start = body.find("{", index + len(marker))
            if json_start == -1:
                return None
            try:
                data, _end = decoder.raw_decode(body[json_start:])
            except ValueError:
                index = json_start + 1
                continue
            if isinstance(data, dict):
                return data
            index = json_start + 1

    def _fetch_youtube_metadata(self, url):
        if not self._url_is_safe(url):
            return {}

        try:
            response = self._http_get(
                url,
                headers=self._request_headers(),
                timeout=YOUTUBE_METADATA_TIMEOUT_SECONDS,
                stream=True,
            )
            response.raise_for_status()
            body = self._read_partial_response(
                response,
                YOUTUBE_METADATA_MAX_RESPONSE_BYTES,
                max_seconds=YOUTUBE_METADATA_READ_SECONDS,
            )
        except RequestException as e:
            self.log.debug(
                "YouTube metadata fetch failed for %s: %s",
                self._safe_url_for_log(url),
                e.__class__.__name__,
            )
            return {}

        soup = BeautifulSoup(body, "html.parser")
        upload_date = self._youtube_meta_content(soup, "uploadDate")
        duration = self._youtube_meta_content(soup, "duration")

        for script in soup.find_all(
            "script", attrs={"type": "application/ld+json"}
        ):
            try:
                data = json.loads(script.get_text())
            except (TypeError, ValueError):
                continue
            upload_date = upload_date or self._metadata_value_from_ld_json(
                data, "uploadDate"
            )
            duration = duration or self._metadata_value_from_ld_json(
                data, "duration"
            )

        player_response = self._youtube_initial_player_response(body)
        if player_response:
            upload_date = upload_date or self._metadata_value_from_ld_json(
                player_response, "uploadDate"
            )
            upload_date = upload_date or self._metadata_value_from_ld_json(
                player_response, "publishDate"
            )
            duration = duration or self._metadata_value_from_ld_json(
                player_response, "lengthSeconds"
            )

        return {
            "duration": self._format_youtube_duration(duration),
            "upload_date": self._format_youtube_upload_date(upload_date),
        }

    def _format_youtube_output(self, title, metadata):
        parts = [f"{YOUTUBE_PLAY_PREFIX}{title}"]
        details = []
        if metadata.get("duration"):
            details.append(metadata["duration"])
        if metadata.get("upload_date"):
            details.append(f"Uploaded {metadata['upload_date']}")
        if details:
            parts.append(" | ".join(details))
        return " | ".join(parts)

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
        cached = self._get_cached_title(url)
        if cached:
            title, resolved_url = cached
            if return_resolved_url:
                return title, resolved_url
            return title

        # Use YouTube oEmbed API to bypass bot-detection pages.
        if self._is_youtube_url(url):
            yt_title = self._fetch_youtube_title(url)
            if yt_title:
                yt_title = self._format_youtube_output(
                    yt_title, self._fetch_youtube_metadata(url)
                )
                self._store_cached_title(url, yt_title, url)
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
                response = self._http_get(
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

            formatted_title = self._extract_title_from_response(
                response,
                self._max_response_bytes(),
                resolved_url,
            )
            if formatted_title is None:
                self.log.debug(
                    "URL fetch response exceeded size limit for %s",
                    self._safe_url_for_log(resolved_url),
                )
                if return_resolved_url:
                    return None, resolved_url
                return None

            self._store_cached_title(url, formatted_title, resolved_url)
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
