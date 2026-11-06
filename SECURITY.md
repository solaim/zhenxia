# Security

Zhenxia is a single-user local application. Compose binds to 127.0.0.1 and does not supply authentication, user isolation or a multi-worker database scheduler. Do not expose the port publicly or deploy multiple replicas against the same data directory.

Cookie credentials are stored locally with owner-only permissions and are never returned by the settings API. Treat the whole data directory as private. Task URLs and database content may contain personal information. Do not publish runtime data.

Media APIs validate stored paths, exclude hidden files and symlinks, and reject cross-origin browser mutations. Files removed in the UI move to local trash and are not securely erased. Local filesystem access is trusted. Back up SQLite with the application stopped, or use SQLite's backup API.

Use private vulnerability reporting on the repository hosting provider, when enabled, to report security issues. Do not include credentials in public issues.

Multi-platform downloads accept only explicit platform URL patterns, not arbitrary URLs or generic extraction. This is a local trusted-user application, not a general SSRF isolation boundary: platform extractors follow provider/CDN URLs and redirects. Do not expose this API to untrusted users. Credentials for each platform use separate Netscape cookie files. Worker errors are mapped to safe messages and do not return signed URLs, cookies, or proxy credentials. Workers have network and filesystem access and are not an OS security sandbox.
