# Verification record (2026-11-20)

Scope: independent local open-source AgentOps Studio, not a HISONG-operated or connected system.

## Automated verification

- Windows local test suite: **24 passed, 1 dependency deprecation warning**.
- `node --check web/app.js`: passed.
- `python -m compileall -q app tests`: passed.
- `git diff --check`: passed.
- Dual-model unit coverage includes:
  - separate complex and fast model IDs;
  - explicit consent required before AI workflow data leaves the device;
  - VOC raw comment text excluded from the LLM context;
  - AI analysis reports and token usage persisted in SQLite;
  - both model routes invoked by the connection-test endpoint (HTTP mocked in unit tests).

## External service and GUI status

- The primary Qwen model had been verified previously on the user's Windows device.
- A fresh real API test of both model IDs was attempted during this release, but the Remote Desktop connection stopped responding before a result was returned. Therefore, **the fast model's live API connection is not yet verified in this record**.
- Browser GUI verification of the new dual-model form and AI report display remains pending.
- No real Shopify, Meta or TikTok credentials were used; no external marketing APIs were modified.

## Scope limits

The LLM adds interpretation and recommendations after deterministic workflow calculations; it does not replace the metric engine or autonomously execute external actions. The current project remains a single-operator local application, not a production multi-tenant SaaS. CI passing is not evidence of commercial effectiveness.
