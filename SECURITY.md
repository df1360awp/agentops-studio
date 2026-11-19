# Security Policy

AgentOps Studio is a single-operator, local-first portfolio project, **not a production SaaS**.

- Default bind: `127.0.0.1`; do not publicly expose the unauthenticated API. Docker Compose enables `AGENTOPS_LOCAL_CONTAINER=1` ONLY for its localhost-bound port; never combine that flag with a public port/reverse proxy.
- For any reverse-proxy deployment set `AGENTOPS_API_TOKEN` to a high-entropy secret and enable HTTPS.
- API-key mode is still *not* a substitute for SSO, tenant isolation, role-scoped access or enterprise auditing.
- Never commit `.env`, SQLite databases, private datasets, access tokens, or customer records.
- Endpoints can read, import, and delete records. Keep the server private, back up the SQLite volume and limit file access.
- LLM calls are optional. If enabled, operators are responsible for privacy and data-transfer approvals.
- No integration automatically changes ad budgets, sends marketing messages, signs contracts, or makes payments.
- When reporting a vulnerability, open a private report instead of publishing sensitive exploit details.
