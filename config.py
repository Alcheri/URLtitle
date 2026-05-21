###
# Copyright (c) 2016 - 2026, Barry Suridge
# All rights reserved.
#
#
###

import supybot.conf as conf
import supybot.registry as registry

try:
    from supybot.i18n import PluginInternationalization

    _ = PluginInternationalization("URLtitle")
except ImportError:

    def _(text):
        return text


def configure(advanced):
    # This will be called by supybot to configure this module.  advanced is
    # a bool that specifies whether the user identified themself as an advanced
    # user or not.  You should effect your configuration by manipulating the
    # registry as appropriate.
    conf.registerPlugin("URLtitle", True)


URLtitle = conf.registerPlugin("URLtitle")

# This is where your configuration variables (if any) should go.  For example:
# conf.registerGlobalValue(URLtitle, 'someConfigVariableName',
#     registry.Boolean(False, _("""Help for someConfigVariableName.""")))

conf.registerChannelValue(
    URLtitle,
    "enabled",
    registry.Boolean(False, _("""Should plugin work in this channel?""")),
)

conf.registerGlobalValue(
    URLtitle,
    "userAgent",
    registry.String(
        "Limnoria-URLtitle/1.0 (+https://github.com/Alcheri/URLtitle)",
        _("""User-Agent header sent when fetching URLs."""),
    ),
)

conf.registerChannelValue(
    URLtitle,
    "showExpandedShortUrl",
    registry.Boolean(
        False,
        _("""Show expanded URL when a supported short link is resolved?"""),
    ),
)

conf.registerChannelValue(
    URLtitle,
    "maxUrlsPerMessage",
    registry.PositiveInteger(
        2,
        _("""Maximum number of URLs URLtitle will fetch from one message."""),
    ),
)

conf.registerChannelValue(
    URLtitle,
    "cooldownSeconds",
    registry.NonNegativeInteger(
        5,
        _(
            """Per-user URLtitle fetch cooldown for this channel, in seconds."""
        ),
    ),
)

conf.registerGlobalValue(
    URLtitle,
    "maxResponseBytes",
    registry.PositiveInteger(
        262144,
        _("""Maximum HTTP response size to read when extracting titles."""),
    ),
)

# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
