# Security Policy

## Supported releases

Security fixes are applied to the latest supported release of ADHD Progress Hub.
Upgrade to the newest release before reporting a problem that has already been
fixed upstream.

## Reporting a vulnerability

Please report security vulnerabilities privately through
[GitHub Security Advisories](https://github.com/uniskela/adhd-hub/security/advisories/new).

Do **not** open a public issue containing credentials, bearer tokens, private Hub
URLs, forge tokens, OpenClaw tokens, browser-session data, or other sensitive
deployment details.

Include enough information to reproduce the problem safely:

- affected ADHD Hub version or commit;
- deployment method (container, source, or local stdio);
- affected surface (MCP, REST, dashboard, forge sync, OpenClaw, installer, etc.);
- minimal reproduction steps;
- expected and observed behavior; and
- security impact.

## Operator guidance

- Set a long random `ADHD_HUB_AUTH_TOKEN` before binding beyond loopback.
- Prefer LAN, VPN, or Tailscale access and HTTPS for remote deployments.
- Treat forge and OpenClaw credentials as secrets and rotate them if exposed.
- Keep the Hub and its container dependencies updated.
- Review backup archives before sharing them; they can contain project metadata
  and encrypted configuration.
- Never publish real tokens, private service URLs, or user data in bug reports.

The repository runs secret scanning, CodeQL, dependency updates, tests, and
container vulnerability checks as defence in depth. These controls do not replace
safe deployment and credential handling.
