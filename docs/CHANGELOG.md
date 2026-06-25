# Changelog

All notable changes to URLtitle are documented in this file.

## Unreleased

### Changed

- Normalised README badges.
- Set the package Python requirement to Python 3.10 or newer.
- Raised the default title extraction read limit for larger news front pages.
- Included YouTube video duration and upload date in YouTube title output when available.

## v1.1.0 - 2026-05-22

### Added

- Added channel reporting for blocked title fetches.
- Added optional expanded-link output for supported short URLs.
- Added YouTube title handling through the oEmbed API and prefixed YouTube titles with the play marker.
- Added security documentation for URL fetch behaviour.

### Changed

- Hardened URL fetch handling, including redirect checks, private-address blocking, and response-size limits.
- Handled blocked URL fetches quietly where appropriate.
- Standardised GitHub support files and `.gitignore` entries.
- Moved supporting project documentation into the `docs/` directory.
- Updated contribution terms.
- Normalised Black configuration and applied Black formatting.
- Ignored the local `Documents/` directory.

## v1.0.0 - 2026-03-25

### Added

- Added PEP 621 package metadata in `pyproject.toml`.
- Added deterministic tests and tighter URL fetch error handling.
- Added configurable user-agent support.
- Added GitHub Actions testing, linting, and CodeQL workflow support.
- Added README badges and Python source header policy documentation.

### Changed

- Updated the plugin version to `1.0.0`.
- Declared `requests` as a runtime dependency.
- Standardised CI workflows and Black lint checks.
- Updated README formatting and repository metadata.
- Ignored Supybot runtime directories, Codex files, and Python cache artefacts.

### Fixed

- Displayed clean error messages for failed URL fetches.
- Improved import error handling.
