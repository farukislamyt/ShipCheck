# Security Policy

## Supported versions

Security fixes are provided for the latest released version of ShipCheck. Development versions on `main` may change without notice.

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| < 0.1.0 | No |

## Reporting a vulnerability

Please do **not** report security vulnerabilities through public GitHub issues.

Instead, use GitHub's private vulnerability reporting feature for this repository when available. Include:

- A clear description of the vulnerability.
- Steps to reproduce or a minimal proof of concept.
- The affected version or commit.
- Any relevant logs, stack traces, or configuration details.
- The potential security impact.

Please avoid including real credentials, API keys, private keys, personal data, or other sensitive information in the report.

We will acknowledge valid reports and coordinate a fix and disclosure timeline with the reporter.

## Secret-scanning note

ShipCheck is designed to identify common credential patterns before deployment. Its scanner is heuristic and should not be treated as a replacement for dedicated secret-management or secret-scanning systems.
