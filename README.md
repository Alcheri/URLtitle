<!-- A simple plugin that detects URLs in a channel and returns the page title. -->

<h1 align="center">URLtitle</h1>

<!-- README_HEADER:start -->
[![Tests][tests-badge]][tests-link]
[![Lint][lint-badge]][lint-link]
[![CodeQL][codeql-badge]][codeql-link]
![Python][python-badge]
![Black][black-badge]
![Limnoria][limnoria-badge]
<!-- README_HEADER:end -->

# Description

A simple plugin that detects URLs in a channel and returns the page title.
Shortened URLs from Minily, Bitly, and TinyURL are resolved automatically.

## Install

Go into your Limnoria plugin dir, usually ~/runbot/plugins and run:

```plaintext
git clone https://github.com/Alcheri/URLtitle.git
```

To install additional requirements, run from /plugins/URLtitle:

```plaintext
pip install --upgrade -r requirements.txt
```

Next, load the plugin:

```plaintext
/msg bot load URLtitle
```

## Configuring

* **config channel #channel plugins.URLtitle.enabled True or False (On or Off)**

    Should plugin work in this channel?

* **supybot.plugins.URLtitle.userAgent**

  User-Agent header sent when fetching URLs. Default is a plugin-specific
  Limnoria URLtitle identifier.

* **config channel #channel plugins.URLtitle.showExpandedShortUrl True or False (On or Off)**

  If enabled and a supported short URL (Minily, Bitly, TinyURL) is resolved,
  URLtitle appends the expanded destination URL in the reply.

<br/><br/>
<p align="center">Copyright © 2016 - 2026, Barry Suridge</p>

## Python Source Header Policy

- In Python 3 files, do not add `# -*- coding: utf-8 -*-` unless a non-default source encoding is required.
- Use `#!/usr/bin/env python3` only for executable scripts, not import-only modules.

<!-- Badge reference definitions -->
[tests-badge]: https://github.com/Alcheri/URLtitle/actions/workflows/tests.yml/badge.svg
[tests-link]: https://github.com/Alcheri/URLtitle/actions/workflows/tests.yml

[lint-badge]: https://github.com/Alcheri/URLtitle/actions/workflows/lint.yml/badge.svg
[lint-link]: https://github.com/Alcheri/URLtitle/actions/workflows/lint.yml

[codeql-badge]: https://github.com/Alcheri/URLtitle/actions/workflows/codeql.yml/badge.svg
[codeql-link]: https://github.com/Alcheri/URLtitle/security/code-scanning

[python-badge]: https://img.shields.io/badge/python-3.9%2B-blue.svg
[black-badge]: https://img.shields.io/badge/code%20style-black-000000.svg
[limnoria-badge]: https://img.shields.io/badge/limnoria-compatible-brightgreen.svg
