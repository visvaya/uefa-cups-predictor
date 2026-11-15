# Security Policy

## Supported versions

Only the latest commit on `main` is supported. There are no releases or backports.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub:
[Report a vulnerability](https://github.com/visvaya/uefa-cups-predictor/security/advisories/new)
(Security tab, "Report a vulnerability"). Do not open a public issue.

Include the affected file or command, steps to reproduce and the impact you expect.
You can expect an initial reply within 7 days.

## Scope

This is a local command-line tool: it has no web interface, server or user accounts.
Relevant reports include, for example:

- code execution or path traversal through crafted input files or scraped HTML,
- unsafe handling of data fetched from third-party sites,
- secrets or personal data committed to the repository,
- weaknesses in the CI workflows or dependency supply chain.

Vulnerabilities in the third-party websites the scraper reads are out of scope;
report them to the site owners.
