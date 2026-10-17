# Railway deployment

Deploy the GitHub `main` branch as a web service plus a separate MySQL service. Attach a volume at `/data` to the web service; photos remain private and are served by Django's permission-checked route. Do not expose the volume as public static media. Use one web replica with this volume. Database and media volumes need separately configured backups and a restore drill.

The repository supplies a Docker build, WhiteNoise static asset serving, a Waitress WSGI entry point, migrations/static collection at startup, and a database-aware `/healthz/` endpoint. Migrations run at startup after the volume is mounted. Startup refuses SQLite or missing upload storage. No sample seed runs automatically and no passwords are printed during normal deployment.

## Web service variables

Set these using Railway's variable editor; never commit actual secrets:

```text
DJANGO_DEBUG=0
DEMO_MODE=1
DJANGO_SECRET_KEY=<generate a long random secret>
DJANGO_TRUST_PROXY=1
DJANGO_MEDIA_ROOT=/data/private_media
DB_ENGINE=mysql
MYSQL_DATABASE=${{MySQL.MYSQLDATABASE}}
MYSQL_USER=${{MySQL.MYSQLUSER}}
MYSQL_PASSWORD=${{MySQL.MYSQLPASSWORD}}
MYSQL_HOST=${{MySQL.MYSQLHOST}}
MYSQL_PORT=${{MySQL.MYSQLPORT}}
```

Replace `MySQL` in references if the actual database service has another name. Use the internal database connection, not a public proxy, from the web service. Railway supplies `PORT`, `RAILWAY_PUBLIC_DOMAIN` and `RAILWAY_VOLUME_MOUNT_PATH`. The domain is automatically allowed, with the healthcheck hostname, and its HTTPS origin is trusted for CSRF. For a custom domain, add it to `DJANGO_ALLOWED_HOSTS` and its HTTPS origin to `DJANGO_CSRF_TRUSTED_ORIGINS`.

Keep HTTPS redirect enabled. Proxy trust is only for this deployment behind Railway's trusted ingress. Generate the public domain, deploy, verify `/healthz/`, login HTML, CSS, fonts and images, then verify account isolation and persistence across redeploys. MySQL timezone tables must be populated for Django's Lagos-time dashboard date aggregation; verify charts against known submission dates.

## First account and protocol

Use a Railway shell/SSH session to run Django's `createsuperuser` interactively, supplying a unique email and username, then set the application's role to `admin` through a controlled Django shell session. Do not put passwords in commands, build logs, repository files or this guide. The Django superuser flag is separate from the application's administrator role. Provision only the accounts needed; no local passwords/database are uploaded.

If a synthetic showcase is wanted, run `seed_demo` only through a controlled session and securely capture its newly generated credentials. That command prints new passwords, so do not put it in a deployment start command or shared build log. Its sample content is not evidence of an approved clinical protocol.

Configure SMTP variables separately for account invitation/password-reset email. Use an approved sender address and verify delivery. Do not use console mail in a public deployment; it can log access links.

## Release status

This deployment preserves the existing `DEMO_MODE=1` restriction and real-patient release lock. Hosting does not approve clinical instructions or remove the remaining MFA/governance prerequisites. Client-approved design and showcase choices are unchanged.
