# Security and release status

RenalTrack is currently a synthetic-data preview. Do not enter real patient information, enable live clinical workflows, or expose the development server publicly.

Before a real-patient release, complete the prerequisites in `docs/Build_Status.md` and the implementation specification. These include MySQL integration and concurrency verification, privileged-account MFA, approved clinical and consent configuration, secure hosting and backup recovery checks.

Never commit credentials, `.env`, local secret keys, database files, private images, backups or identifiable patient data. `.env.example` contains placeholders only. `DEMO_ACCESS.md` and all generated local data are excluded from Git. Generate fresh accounts for each environment; do not deploy the local demo database.

Report security concerns privately to the repository owner. Do not attach patient records, credentials or private photographs to public issues. A public security contact and supported-release policy must be agreed before external release.
