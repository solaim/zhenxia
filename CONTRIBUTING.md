# Contributing

Use Python 3.10+ and install `pip install -e '.[dev]'`. Run `ruff check .` and `python -m pytest -q`. Platform requests must be mocked in tests. Do not submit cookies, downloaded media, runtime databases or personal paths.

All application code belongs in `zhenxia/`. Keep upstream imports exclusively in `zhenxia/adapter.py`, pin the Git dependency to a full commit, and add compatibility tests when changing the engine version. Do not vendor upstream source. The project has no sibling checkout requirement.

Database schema changes need a versioned migration and tests covering old databases, repeated startup, interrupted tasks and existing media. Media is stored on disk; SQLite stores metadata. Frontend changes should be checked on desktop and mobile. Preserve the upstream MIT license and attribution.
