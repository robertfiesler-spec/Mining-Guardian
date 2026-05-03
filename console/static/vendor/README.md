# console/static/vendor/

Locally vendored third-party assets for the Mining Guardian console.
The console is a local-first appliance daemon (loopback-bound on the
customer Mac Mini) and **must not depend on a public CDN at runtime** —
the customer site has no public ingress, no inbound internet
requirement, and the operator may run with internet egress
restricted. Every asset the browser needs has to ship inside the
repo / `.pkg` payload.

## htmx-1.9.12.min.js

- **Source:** <https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js>
- **Upstream:** <https://github.com/bigskysoftware/htmx> (v1.9.12)
- **License:** Zero-Clause BSD (0BSD) — see
  <https://github.com/bigskysoftware/htmx/blob/v1.9.12/LICENSE>.
  0BSD imposes no redistribution requirements; no NOTICE update needed.
- **Size:** 48,101 bytes
- **SHA-256:** `449317ade7881e949510db614991e195c3a099c4c791c24dacec55f9f4a2a452`

The console templates load this file from `/static/vendor/htmx-1.9.12.min.js`.
There is no script-src to a CDN. To bump the version, replace the file,
update the filename + SHA-256 in this README, update the `<script>` tag
in `console/templates/_base.html`, and re-run the console test suite.
