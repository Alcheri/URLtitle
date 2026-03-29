<h1 align="center">URLtitle</h1>

<!-- README_HEADER:start -->
<p align="center">
  <a href="https://github.com/Alcheri/URLtitle/actions/workflows/tests.yml">
    <img src="https://github.com/Alcheri/URLtitle/actions/workflows/tests.yml/badge.svg" alt="Tests">
  </a>
  <a href="https://github.com/Alcheri/URLtitle/actions/workflows/lint.yml">
    <img src="https://github.com/Alcheri/URLtitle/actions/workflows/lint.yml/badge.svg" alt="Lint">
  </a>
  <a href="https://github.com/Alcheri/URLtitle/security/code-scanning">
    <img src="https://github.com/Alcheri/URLtitle/actions/workflows/codeql.yml/badge.svg" alt="CodeQL">
  </a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black">
  <img src="https://img.shields.io/badge/limnoria-compatible-brightgreen.svg" alt="Limnoria">
  <img src="https://img.shields.io/badge/License-BSD_3--Clause-blue.svg" alt="License">
</p>
<!-- README_HEADER:end -->


# Description

A simple plugin that detects URLs in a channel and returns the page title.

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

<br/><br/>
<p align="center">Copyright © MMXXIV, Barry Suridge</p>
