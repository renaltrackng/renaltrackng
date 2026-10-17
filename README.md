# RenalTrack

A Django-rendered, responsive screening and manual-review application. Individual email/password accounts, facility-private records, assigned reviewers, private photographs, consent, persistent patient history, repeat attempts, review amendments, notifications and audit history.

**Current delivery: runnable synthetic-data preview. Real-patient mode is deliberately locked pending approved clinical configuration, governance and privileged-account MFA.** No automated interpretation or clinical risk classification is implemented.

## Run locally

Use Python 3.12 or another Django 5.2-compatible Python installation.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8018
```

The workspace bootstrap also supports dependencies installed in `.runtime/`; `manage.py` loads that folder automatically. Do not expose the development server publicly.

Open http://127.0.0.1:8018. Account provisioning prints randomly generated passwords on first seed only. Demo emails: `admin@renaltrack.demo`, `staff@renaltrack.demo`, `reviewer@renaltrack.demo`, `staff2@renaltrack.demo`, `staff3@renaltrack.demo`. Rerunning the seed preserves accounts and records. Do not seed an environment with real data. For lost local demo passwords use `python manage.py changepassword <email>`.

Local defaults use persistent SQLite, console mail, debug mode and synthetic-data restrictions. The default is explicitly a demo convenience, not the requested deployed MySQL system.

## MySQL

Copy `.env.example` to `.env`, set secrets and database credentials, and use `DB_ENGINE=mysql`. For local MySQL testing retain `DJANGO_DEBUG=1` and `DEMO_MODE=1`. MySQL 8.4 can be provisioned using `compose.yaml`; Docker must be installed separately. Set MYSQL_ROOT_PASSWORD for Compose. Bindings are loopback-only. Existing SQLite data is not automatically transferred.

```powershell
docker compose up -d mysql
python manage.py migrate
python manage.py seed_demo
python manage.py test core
```

MySQL is not installed on the original build computer; MySQL integration and concurrent-worker behaviour must be checked in the target environment. ORM transactions, row locks, revisions and unique constraints are implemented; SQLite tests cannot prove MySQL concurrency behaviour.

## Checks

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test core
```

Tests cover scope isolation, private images, consent, patient IDs, persistent submissions, duplicate requests, review claims/conflicts, amendments, repeat attempts, unreadable outcomes, role restrictions, invalid uploads, activation links, account restrictions, login throttling and page rendering.

## Staging deployment

Set `DJANGO_DEBUG=0`, a strong `DJANGO_SECRET_KEY`, exact `DJANGO_ALLOWED_HOSTS`, MySQL credentials, SMTP and HTTPS configuration. Keep `DEMO_MODE=1` until the documented pilot prerequisites are approved and a reviewed implementation unlocks live mode. Configure Django's proxy settings only for a trusted reverse proxy; otherwise leave them unset. Install dependencies into an isolated environment, run migrations and `collectstatic`, serve with a production WSGI server (Waitress is included) behind HTTPS, and serve collected static assets at `/static/`. Media must never be served as public static files. Preserve private media and the database across releases.

## Account operation

Administrators create facilities and individual staff/reviewer accounts through Team & access. Assign reviewers to facilities. “Send access link” emails an expiring one-use password-setting link in staging; local debug mode displays the link only to the signed-in administrator for demonstration. Set/reset links expire after one hour. Use the Settings page for profile and password changes. Email changes, account disabling and facility assignments are administrator-managed. Login is limited by account and source address. External mail delivery requires configured SMTP and is not verified in the local preview.

## Backup and restore

Before launch, appoint an operator and agree encrypted backup destination, retention and recovery targets. Back up MySQL using a consistent transactional dump and copy `private_media/` within a coordinated write pause. Restrict access and encrypt both. Restore into a separate database and private media directory; run migrations/checks, compare record/image counts, sign in and open an authorised image, then verify a second facility cannot access it. Record the restore time and result. Keep encryption keys separate. No successful backup/restore or production deployment is claimed by this repository.

## Remaining pilot gates

- Exact purchased product instructions, clinical observation options/units and next-step wording.
- Approved minimum patient identity fields, consent and withdrawal/retention procedures.
- Privileged-account MFA implementation and verification.
- Hosting, HTTPS, SMTP, MySQL integration, load/concurrency checks and restore drill.
- Programme confirmation that the coded build is acceptable.
- Approved protocol provisioning UI/import and governance approval before live-mode unlock. Preview protocols are read-only; clinical values cannot be invented in the UI.

See `docs/RenalTrack_Implementation_Specification.md` for the product baseline. Synced `sources/` reference files are untouched.

## Repository handover

The repository excludes synced project references, local credentials, environment files, database files, private uploads, downloaded runtime dependencies and generated static output. The Bootstrap assets under `static/vendor/` are intentional runtime assets and retain their upstream licence notices. No application licence has been selected; agree ownership and licensing with the client before publishing the repository publicly.

Use a private repository while the client reviews the build. Start with `.env.example` and fresh environment-specific credentials; never upload `DEMO_ACCESS.md` or copy the local demo database into the repository. See `SECURITY.md` for release restrictions.

The local branch is prepared as `main`. A remote repository URL will be added when supplied. No remote push or public deployment is part of this initial preparation.
