# Dograh SaaS Plan

## What already exists

Dograh is not a blank single-tenant app. The repository already contains:

- `OrganizationModel` and a many-to-many `organization_users` table
- `organization_id` on workflows, runs, campaigns, telephony, credentials, files, and API keys
- Organization-scoped API keys with hashing and prefixes
- `OrganizationUsageCycleModel` and workflow-run usage hooks
- Quota checks in `api/services/quota_service.py`
- A billing ledger UI in `ui/src/app/billing`
- Superadmin and impersonation routes
- Local email/password auth and optional Stack Auth
- `DEPLOYMENT_MODE=oss` vs. hosted behavior

The important limitation: the existing hosted billing is tied to **Dograh's MPS service** (`services.dograh.com`) and Dograh credits. That is Dograh's commercial backend, not something to resell as your own.

## Recommended first SaaS model: BYOK subscription

Start with **Bring Your Own Keys**:

- Customer connects their own LLM, TTS, STT, and telephony provider keys.
- You charge a flat monthly subscription for the platform.
- You do not resell model or telephony usage, so there is no usage-margin risk.
- You still meter calls and agents to enforce plan limits.

This is the fastest route to a sellable product and avoids becoming a telecom/model reseller on day one.

Later, add a managed-credits tier with included minutes and per-minute overage.

## Recommended architecture

### Tenancy

Keep the existing shared database and `organization_id` model for the MVP.

Add:

- `organization_members` with `role` (`owner`, `admin`, `member`) and invitation status
- Optional PostgreSQL Row-Level Security as a second isolation layer
- Per-organization object-storage prefixes
- Per-organization concurrency, agent, and monthly-call limits
- Audit log for membership, billing, API key, and impersonation events

### Authentication

Use **Firebase Authentication** for Google sign-in and phone/SMS OTP:

- Firebase JS SDK runs in the browser and handles Google popup sign-in and phone verification.
- The API verifies the Firebase ID token with `google.oauth2.id_token.verify_firebase_token`.
- Dograh still issues its own JWT/httpOnly-cookie session, so existing authorization and tenant checks are unchanged.
- Google accounts link to an existing local account with the same verified email.
- Phone-only accounts get a new organization.
- Set `FIREBASE_PROJECT_ID`, `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_APP_ID`, and `FIREBASE_MESSAGING_SENDER_ID`.
- Add every deployment origin to Firebase Authentication → Settings → Authorized domains.
- Firebase phone auth uses reCAPTCHA and may require the Blaze plan for SMS delivery.

Keep local email/password auth for development and as a fallback. Stack Auth remains optional for deployments that already use it.

### Billing

Use **Flutterwave** (not Stripe and not Dograh MPS) with **multi-currency pricing**.

Decisions locked so far:

- Billing provider: Flutterwave
- Markets: all Flutterwave-supported currencies
- Base prices authored in USD, converted to local currency
- FX source: public daily rates plus a **10% buffer**
- Billing intervals: **monthly and annual** (annual is discounted)
- BYOK stays mandatory; no resale of model or telephony usage

Add tables:

- `plans` — name, USD base price, limits, features (code-owned catalog)
- `organization_subscriptions` — organization, plan, Flutterwave customer/subscription/plan IDs, currency, interval, amount, status, period
- `entitlements` — resolved limits per organization
- `billing_events` — idempotent webhook processing
- `usage_counters` — calls, minutes, agents, storage; monthly aggregation

Flutterwave responsibilities:

- Payment plans for recurring billing
- Standard Checkout for the first charge and card enrollment
- Webhooks for `charge.completed` and `subscription.cancelled`
- Transaction verification before activating a subscription
- No hosted customer portal — cancellation is handled in-app through the Flutterwave cancel-subscription API

Because a Flutterwave payment plan is amount- and currency-specific, the API creates one plan per organization/currency/interval and reuses it while the quote is unchanged.

Enforce limits in the API, not only the UI.

### Onboarding

1. Marketing page and pricing
2. Sign up with Google/email
3. Create organization
4. Choose plan and complete Flutterwave Checkout
5. Connect provider keys (BYOK) or skip to explore
6. Create first voice agent
7. Optional: connect telephony provider and phone number

### Telephony

For the MVP, require each customer to bring their own Twilio/Telnyx/Vonage credentials. This avoids:

- Master-carrier compliance obligations
- Number inventory and monthly fees
- International regulatory complexity
- Abuse and fraud exposure

Later, offer managed numbers through a carrier sub-account model.

### Deployment

MVP:

- One region
- Docker Compose on a hardened VPS
- Caddy or Cloudflare in front for TLS and WAF
- Managed PostgreSQL with automated backups
- Managed Redis
- S3-compatible object storage
- Sentry for errors, PostHog for product analytics
- Daily database backups with tested restores

Do not start with Kubernetes. Move to Kubernetes only after sustained load or enterprise demand.

## Phased implementation

### Phase 0 — product decisions

- Brand/domain
- Pricing and plan limits
- BYOK vs. managed credits
- Target market and support policy
- Flutterwave, Firebase, cloud, and email accounts

### Phase 1 — tenant and auth hardening

- Roles and invitations
- Firebase Google + phone/SMS sign-in
- Email verification/password reset
- Organization switcher
- Audit logging
- Remove any cross-tenant query paths
- Tenant-isolation tests

### Phase 2 — subscriptions and entitlements

- Plans and subscriptions tables
- Flutterwave Checkout and cancellation flow
- Webhook handling with idempotency
- Entitlement middleware
- Billing settings page
- Trial and grace-period behavior

### Phase 3 — onboarding and BYOK

- Public signup flow
- Provider-key setup wizard
- Connection validation
- First-agent onboarding
- Tenant-aware error messages

### Phase 4 — usage limits and admin

- Monthly call/agent/storage counters
- Soft and hard limits
- Superadmin tenant list
- Suspend/reactivate organization
- Usage dashboards and CSV export
- Impersonation with audit trail

### Phase 5 — production readiness

- Managed database/Redis/object storage
- Backups and restore test
- Rate limits and abuse controls
- Sentry/PostHog/uptime monitoring
- Security headers, WAF, secret management
- Load test with concurrent calls
- Incident runbook

### Phase 6 — commercial launch

- Pricing page and checkout
- Terms, privacy, DPA, AUP
- Call-recording consent and retention policy
- Support and status page
- Beta cohort and feedback loop

## Key risks

- **Telephony compliance** — consent, recording disclosure, DNC, and regional rules
- **Abuse** — voice agents can be used for spam or fraud; require verification and rate limits
- **Data protection** — call recordings and transcripts are sensitive; define retention and deletion
- **Cost leakage** — BYOK avoids model resale, but platform compute and storage still cost money
- **Tenant isolation** — every query and object path must be organization-scoped

## Recommended first release

- BYOK only
- Three plans: Starter, Growth, Scale
- 14-day trial
- Shared infrastructure, one region
- Google + phone/SMS auth via Firebase, with email/password fallback
- Flutterwave subscriptions in local currencies
- Customer-owned telephony
- Hard limits on agents, concurrency, and monthly calls
- No managed model credits yet

