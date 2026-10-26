# Cognitrace product readiness

## Product promise

Cognitrace helps people work through decisions and challenges by talking them
out, then surfacing a small set of reasoning statements tied to exact quotes.
The product should present patterns as prompts to consider, never as diagnoses
or objective personality claims.

## Working product path

1. A user starts a reflection and chats with the authenticated FastAPI service.
2. The draft remains in the browser tab until the user completes it.
3. The app submits the user's own notes to the existing session endpoint.
4. Gemini proposes structured reasoning; the backend checks each evidence
   quote against the submitted source before saving it.
5. The user can revisit the saved reflection and their session history.

Mock mode is available for demos. It is visibly labeled and uses browser-local
sample data. Real mode uses Supabase Auth and keeps the access token in memory.

## Release gates before charging users or storing sensitive reflections

- **Choose and verify durable production storage.** SQLite is the runtime
  default. A hosted deployment must use a persistent disk or explicitly enable
  the Supabase adapter and apply its migration. Test the selected setup across
  a restart and backup/restore before relying on it.
- **Add owner-only deletion and a retention policy.** The current real API has
  no delete or retention route. The UI discloses this; do not market real-mode
  session history as deletable until the API and RLS policy support it.
- **Complete a real auth-to-storage integration run.** Current automated
  coverage is offline/mocked. Verify sign-in, chat, extraction, owner isolation,
  history, key rotation, and failure handling against a disposable local
  Supabase project before enabling real mode for customers.
- **Set limits for model cost and abuse.** Chat input is capped by the current
  route schema; transcript submission has no explicit product-level size or
  rate limit. Define budgets and abuse controls before public launch.
- **Validate the reasoning quality with representative, consented data.** The
  included hand-authored evaluation set is a regression aid, not evidence of
  clinical, behavioral, or business outcomes.
- **Decide support, billing, and customer data terms.** The repository has no
  payment flow or customer support operations. Those need deliberate product
  and legal review before a paid launch.

## Local quality checks

Run from the repository root:

```sh
python -m pytest -q
python -m ai.evaluation.evaluate
```

Run from `frontend/`:

```sh
npm ci
npm test
npm run build
```

The GitHub Actions workflow runs these same offline checks without Gemini or
Supabase credentials.
