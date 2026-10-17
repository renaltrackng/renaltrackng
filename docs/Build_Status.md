# RenalTrack build verification

17 October 2026

## Implemented

- Custom Django user model with individual email/password accounts and administrator-managed staff/reviewer access.
- Product administration screens for facilities, staff, reviewer assignments, account disabling and expiring activation/reset links.
- Facility-scoped dashboards, patient search and patient history.
- Consent-first registration; automatic patient IDs; server-side drafts and risk-factor capture.
- Validated photo uploads, local preview/retake, private image delivery and persistent submission attempts.
- Manual review queue, 15-minute claims, revision conflicts, repeat requests, unreadable decisions and versioned amendments.
- Neutral in-app notifications and application audit events.
- Custom Bootstrap-based responsive interface with local vendor assets; login, dashboards, lists, detail, forms, error and empty states.
- MySQL configuration, migrations, local database service definition, environment example and startup/handover documentation.

## Verified locally

- Django system checks: no issues.
- Migrations: no uncommitted model changes. Static asset collection succeeded.
- Automated workflow/access tests: 24 passed; includes complete HTTP form submission through returned review.
- Browser: real administrator login and rendered dashboard checked against synthetic data.
- Mobile: navigation drawer expands, table content switches to cards and DOM width check shows no page-level horizontal overflow at the tested phone viewport. Mobile screenshot capture was unavailable in the browser tool; desktop visual review succeeded.

## Not yet verified / prerequisites

The machine does not have a MySQL server or Docker. MySQL configuration is supplied but MySQL migration, real concurrent-worker tests and restore verification remain outstanding. Local preview uses persistent SQLite. No hosted URL, SMTP delivery, production load test or backup restore is claimed.

The preview uses a synthetic protocol with no clinical readings or risk tiers. Actual product/clinical configuration, final identity fields, consent/governance, hosting, retention and programme acceptance require client inputs. Privileged-account MFA and approved clinical protocol provisioning remain to be implemented before a real-patient release. Live mode is blocked in settings until those prerequisites are addressed.

Audit history is append-only through the product; database administrators retain technical control. Backups are documented as an operator procedure, not an automatic verified service.
