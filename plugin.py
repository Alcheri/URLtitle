###
# Copyright (c) 2016 - 2026, Barry Suridge
# All rights reserved.
#
#
###

import re
import time
import requests
from requests import RequestException, Timeout

try:
    from bs4 import BeautifulSoup
except ImportError as ie:
    raise ImportError(f"Cannot import module: {ie}")

import supybot.ircutils as ircutils
from supybot import callbacks
from supybot.commands import *
from supybot.i18n import PluginInternationalization

_ = PluginInternationalization("URLtitle")

DEFAULT_USER_AGENT = "Limnoria-URLtitle/1.0 (+https://github.com/Alcheri/URLtitle)"
URL_PATTERN = re.compile(r"(https?://\S+|www\.\S+)")
CACHE_TTL_SECONDS = 600
REQUEST_TIMEOUT_SECONDS = 10


class URLtitle(callbacks.Plugin):
    """
    Automatically detects URLs in messages and replies with the website title, with caching.
    """

    threaded = True

    def __init__(self, irc):
        self.__parent = super(URLtitle, self)
        self.__parent.__init__(irc)
        self.cache = {}  # Simple cache for storing URL titles

    def _request_headers(self):
        return {"User-Agent": self.registryValue("userAgent")}

    def _format_request_error(self, url, error):
        if isinstance(error, Timeout):
            return (
                f"Error fetching {url}: request timed out after "
                f"{REQUEST_TIMEOUT_SECONDS}s"
            )

        error_message = str(error).strip() or error.__class__.__name__
        return f"Error fetching {url}: {error_message}"

    def fetch_title(self, url):
        # Check the cache first to avoid duplicate network calls.
        if url in self.cache:
            title, timestamp = self.cache[url]
            if time.time() - timestamp < CACHE_TTL_SECONDS:
                return title

        try:
            # Fetch the webpage
            response = requests.get(
                url, headers=self._request_headers(), timeout=REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()

            # Parse the HTML and extract the title
            soup = BeautifulSoup(response.text, "html.parser")
            title_tag = soup.find("title")

            if title_tag:
                formatted_title = title_tag.get_text(strip=True)
            else:
                formatted_title = f"Title for {url}: No title found"

            # Update the cache
            self.cache[url] = (formatted_title, time.time())
            return formatted_title
        except RequestException as e:
            self.log.error(f"Error fetching {url}: {e}")
            return self._format_request_error(url, e)

    def doPrivmsg(self, irc, msg):
        """
        Triggered when a message is sent in a channel.
        """
        channel = msg.args[0]
        if not self.registryValue("enabled", channel, irc.network):
            return
        text = msg.args[1]

        urls = URL_PATTERN.findall(text)

        if urls:
            for url in urls:
                # Add http if the URL does not include a scheme
                if not url.startswith(("http://", "https://")):
                    url = "http://" + url

                title = self.fetch_title(url)
                irc.reply(title, to=channel)


Class = URLtitle


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
