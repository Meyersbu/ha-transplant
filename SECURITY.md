# Security policy

Please report vulnerabilities privately via GitHub **Security → Report a vulnerability**,
not in public issues. You will get a response within 7 days.

## Security model

- The panel and every WebSocket command require a Home Assistant **administrator**.
  Read commands are admin-only too, because they expose raw configuration.
- Clients cannot send configuration or file paths. `transplant/apply` only accepts a
  server-side plan ID created by `transplant/preview`; plans expire after 15 minutes
  and can be applied once.
- Writes are limited to `automations.yaml`, `scripts.yaml`, `scenes.yaml` (atomic writes,
  same mechanism as the core editors) and storage-mode dashboards via Home Assistant's
  dashboard API. No registry, database or arbitrary file writes.
- Templates are never rendered or executed; they are only searched as text.
- The panel renders all configuration text with `textContent` (no `innerHTML`, enforced by lint).
