# -*- coding: utf-8 -*-
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
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x


def configure(advanced):
    # This will be called by supybot to configure this module.  advanced is
    # a bool that specifies whether the user identified themself as an advanced
    # user or not.  You should effect your configuration by manipulating the
    # registry as appropriate.
    from supybot.questions import expect, anything, something, yn

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

# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
