# RenalTrack — Implementation Specification

Prepared: 17 October 2026
Status: Account and access policies confirmed by the project owner on 17 October 2026. Engineering baseline ready for synthetic-data development; clinical and operational inputs remain pending.

## 1. Authority and scope

This document refines the six-page RenalTrack Corrected MVP Build Specification supplied by the client. It records proposed implementation decisions; it does not imply client approval of unanswered questions or approval of clinical procedures.

Confirmed developer direction: Django, MySQL, Django-rendered HTML, CSS, JavaScript, and Bootstrap; responsive, custom product design; start at login; no marketing landing page for this phase. Manual review only. Patients do not have accounts.

Purpose: support a controlled pilot by recording consent, registering patients, capturing screening submissions, enabling authorised review, returning reviewed findings, and preserving history. No AI interpretation, automatic clinical classification, diagnostic claims, or invented strip thresholds.

## 2. Decision register

| ID | Decision | Baseline / status |
|---|---|---|
| D01 | Authentication | CONFIRMED: email and password; individual accounts |
| D02 | Account provisioning | CONFIRMED: admin creates all staff and reviewers; multiple staff per facility |
| D03 | Public signup | CONFIRMED: disabled; supersedes PDF public-signup paragraph |
| D04 | Patient visibility | CONFIRMED: facility-private; cross-facility linking and transfers deferred |
| D05 | Reviewer visibility | CONFIRMED: explicit facility assignments |
| D06 | Notifications | CONFIRMED: in-app only; no SMS, WhatsApp, or email result delivery |
| D07 | Patient identity fields | Automatic patient ID required; name or approved participant identifier, matching fields and minimum required demographics need client approval |
| D08 | Clinical configuration | Exact purchased strip instructions, recorded observation options and units, permitted interpretations, and next-step wording require supplied documentation and qualified clinical approval |
| D09 | Pilot governance | Consent wording, controller contact, retention periods, hosting/data-handling arrangements, and pilot access list require client confirmation |
| D10 | Programme requirement | Founder must confirm whether this coded build satisfies the no-code programme requirement |
| D11 | Recovery | Prefer expiring account-activation/reset links; mail provider and operational recovery method must be selected before deployment |
| D12 | Hosting and delivery | Domain, hosting, private media storage, backup destination, sender email, and operating owner unresolved |

D01-D06 are confirmed implementation requirements. Clinical configuration and real-patient operation are blocked by D08/D09; synthetic-data development can proceed independently. D10 affects programme acceptance, not the feasibility of coding.

## 3. Roles and permissions

| Capability | Facility staff | Assigned reviewer | Administrator |
|---|---|---|---|
| Manage facilities, users, assignments | No | No | Yes |
| Search patients and view histories | Own facility | Assigned facilities as required for review | All facilities |
| Register patient and record consent | Own facility | No | No by default |
| Create, edit, submit screening | Own facility; drafts only | No | No by default |
| Request repeat / record review | No | Assigned facilities | Only with explicit reviewer capability |
| Amend completed review | No | Assigned facilities; reason required | Only with explicit reviewer capability |
| Inspect audit events | No | Relevant review history | Yes |
| Configure approved protocols | No | No | Yes; cannot invent clinical content |

Administrator is an application role; reserve Django superuser access for technical operations. Pilot reviewers and staff must never receive Django superuser credentials. Enforce access on every server request, including image URLs, downloads, search, counts and direct record links. Knowing an ID confers no access. No public patient lookup.

Disable accounts rather than deleting attribution. Disabling a facility stops new submissions and member access while preserving records; access by assigned reviewers/admin follows explicit policy. Retain audit identity after departures. Support one facility per staff account for MVP; reviewers can have multiple assigned facilities. Avoid multi-role accounts initially; founder may have administrator and explicit reviewer capability.

## 4. Primary journeys

### Access

Administrator creates facility and user → user receives expiring activation link → chooses password → logs in → role-specific dashboard. No shared facility password. Login uses generic error messages and rate limiting. Password recovery must avoid exposing whether an email exists. Suspension invalidates access promptly. Require MFA for administrator/reviewer accounts before real-patient launch; select implementation during technical setup.

### New patient and screening

Staff selects New screening → searches for an existing patient within their facility → records consent before collecting new identifiable details → registers new patient if required → records risk factors → records approved strip/product details → captures/uploads image → previews image and summary → submits → receives server-confirmed receipt and patient ID.

Do not store identifying information before consent. A declined consent closes the flow without creating an identifiable patient or photo record. For returning patients, present the current consent notice and record consent for each new screening; existing access remains governed by permissions. Define retention of previous records after withdrawal with the client rather than implementing automatic deletion.

### Returning patient

Search exact patient ID or permitted identity fields → verify identity using agreed matching details → open history → New screening → obtain screening consent → complete submission. Never auto-merge records. An uncertain match requires verification; cross-facility deduplication is deferred.

### Review

Reviewer opens assigned queue → claims submission → inspects photo, capture details, risk factors and protocol version → records observation, note and approved next step OR requests repeat OR marks unreadable → saves → facility staff receives in-app notification → opens result and history.

A review can be saved only against the current record revision. Concurrent reviewers receive a conflict and must refresh. Claims expire or can be released; use a configurable initial 15-minute lease. A claim is an operational aid; the database must still prevent duplicate finalisation.

### Repeat image

Reviewer records reason → staff sees Repeat requested → staff follows the approved repeat procedure → creates a new submission attempt with new image and relevant timing/product metadata → submits → returns to Pending review. Preserve every previous attempt and reason. Do not assume an old strip can be photographed again; whether a fresh test is required comes from the approved protocol.

### Result amendment

Reviewer opens completed result → selects Amend → enters correction and reason → saves new review version → current result points to latest version → staff receives update notification. Earlier results remain in history; never silently overwrite a completed review.

## 5. State machine

| Current | Action | Next | Who |
|---|---|---|---|
| Draft | Save draft | Draft | Facility staff |
| Draft | Submit valid attempt | Pending review | Facility staff |
| Pending review | Finalise approved review | Reviewed | Assigned reviewer |
| Pending review | Request repeat with reason | Repeat requested | Assigned reviewer |
| Pending review | Close unreadable with reason | Unable to read | Assigned reviewer |
| Repeat requested | Submit replacement attempt | Pending review | Facility staff |
| Unable to read | Begin later screening | New separate Draft | Facility staff |
| Reviewed | Amend review with reason | Reviewed, new version | Assigned reviewer |

Draft is not a submission. Review claims do not change the clinical workflow status. Submitted attempts are immutable; corrections require a recorded amendment or replacement process. An unreadable finding never requires a clinical risk category. Reviewed and Unable to read are terminal for that screening except review amendments; further testing starts a new screening unless a repeat was explicitly requested.

## 6. Screens and navigation

### Shared

Login; activation; forgot/reset password; own profile/password/security; in-app notifications; access denied/not found; service error. Use generic messages where record existence must be concealed.

### Staff

Dashboard with New screening, patient search, pending, repeat requested and recently reviewed counts; patient list; patient detail/history; consent and registration; screening wizard; submission receipt; screening detail/result; repeat submission form.

Wizard steps: Consent → Patient → Risk factors → Test and photo → Check and submit. For an existing patient, show verified patient details rather than re-registering. Save server-side drafts after consent; show saved/unsaved state. Warn before leaving an unsaved step. No offline mode or background submission in MVP.

### Reviewer

Dashboard/queue with status, facility and date filters; oldest-first default; patient ID, submission time and elapsed wait; review detail with image zoom, metadata, prior attempts and permitted history; review action form; reviewed records and amendment history. No unapproved clinical priority score.

### Administrator

Operational dashboard; facilities; staff; reviewers and assignments; records overview; audit log; approved protocol versions. Admin account management must be usable in the product, not only Django admin. Avoid patient-identifying information on aggregate dashboard cards.

## 7. Data model

All records use internal non-sequential identifiers in external URLs where practical; this supplements rather than replaces authorisation. Store timestamps in UTC, present Africa/Lagos by default, and show explicit dates/times in histories.

| Entity | Main fields / rules |
|---|---|
| User | Unique normalised email, password hash, role/capabilities, active state, staff facility when applicable, created by/time; use a custom Django user model from the first migration |
| Facility | Unique code/prefix, name, approved contact/location details, active state |
| ReviewerAssignment | Reviewer, facility, granted by/time, revoked time; no duplicate active assignment |
| Patient | Internal ID, globally unique public patient ID, owning facility, approved identifier/name and minimum approved matching details, created by/time |
| FacilitySequence | Facility and next patient number; transactional allocation with uniqueness constraints |
| ConsentRecord | Patient/screening linkage, notice version, agreed scope, recorded by/time; agreed participant/representative process requires client wording |
| Screening | Patient, facility, submitter, status, draft fields, risk-factor snapshot, protocol version, current attempt/review, created/submitted times, revision number |
| SubmissionAttempt | Screening, attempt number, submitter/time, product/lot/expiry fields as approved, capture/reading time fields, optional staff observation if protocol requires, private image, replacement reason; immutable on submission |
| ReviewVersion | Screening/attempt, reviewer/time, decision, approved observation code/unit, optional approved risk category, next step, note, version and amendment reason |
| ReviewClaim | Screening, reviewer, expiry; acquired atomically |
| ProtocolVersion | Product identity, approved instruction text and observation options, units, allowed next steps, consent references where applicable, approving person/date and source reference; approved versions immutable |
| Notification | Recipient, neutral event text, target record, created/read times; no finding in message preview |
| AuditEvent | Actor, facility/target, action, timestamp, structured changed fields and reason; append-only through the application; avoid secrets and raw clinical data in general logs |

Use Yes / No / Unknown / Not provided for each agreed risk factor. Keep Unknown distinct from an unanswered draft field. Store risk-factor answers with each screening so later updates do not rewrite earlier context.

Patient ID format: facility code plus padded sequence, e.g. LAF-000001. Codes are configured, not hard-coded. Allocate safely inside a transaction and enforce database uniqueness. Permit gaps; never recycle IDs. Changing a facility's display name must not change existing patient IDs. Existing facility codes become immutable after first patient creation.

## 8. Validation and reliability

- Validate on the server; browser validation is an additional convenience.
- Require consent, agreed patient fields, completed risk-factor answers, approved product details and a valid image before submission.
- Accept JPEG and PNG initially; initial upload limit 10 MB, visible before selection. Check file contents by decoding, extension and size; reject corrupted/unsupported files with a useful message. Handle unsupported phone image formats explicitly.
- Re-encode accepted images to remove embedded metadata, preserve useful review detail, and retain the submitted original privately only if the agreed retention policy requires it. Verify any processing does not materially alter review colours; make this a clinical approval check.
- Do not label an image clinically readable using automated analysis. Staff preview and reviewer judgement govern the workflow.
- Use request idempotency and a transaction for final submission. Double clicks/retries must produce one attempt and one logical submission event.
- Coordinate media writes with database commits: incomplete image writes must not yield a successful submission; clean up orphaned files safely with documented maintenance.
- Persist review, status, audit event and notification together. A notification failure must never erase a saved review; external delivery is out of scope.
- Use explicit optimistic concurrency checks and database locking where required for sequence allocation, claims and final review.
- Never show Submitted, Reviewed, or Saved until the server confirms success. Preserve form input after recoverable errors and allow retry.
- Paginate lists and index facility, patient ID, status and submission time. Enforce the same facility scope on counts and list results.

## 9. Security and operational requirements

Use Django password hashing, session authentication, CSRF protection, secure HTTPS cookies, appropriate session expiry, login throttling and server-side permissions. Configure production secrets outside source control; disable debug output. Do not place patient records or photos in browser local storage, analytics services or error reports.

Images must be served through an authorisation check or short-lived authorised storage URL; no public media directory or permanent publicly accessible URL. Back up MySQL and image storage together, encrypt/restrict backup access, and test restoration before launch. Initial recovery targets proposed for approval: daily backup, recovery point no worse than 24 hours, restore within one working day. Retention duration and backup expiry remain client decisions.

Document access revocation, incident contact, deletion/retention requests, deployment rollback, log handling, backup owner and restore procedure. Verify applicable data-handling obligations with the client's responsible adviser; this document does not constitute legal approval.

## 10. Visual design brief

Create a distinct calm clinical interface: warm/light neutral surfaces, deep teal or blue primary accents, restrained secondary colours, generous spacing and consistent rounded cards. Use clear typography with differentiated heading/body weights and readable tabular numbers. Select and verify font licences during visual implementation. Bootstrap is the layout/component foundation; custom design tokens and components provide the identity.

Learn from the supplied references: persistent desktop sidebar, clear active navigation, grouped form panels, strong hierarchy and spacious review cards. Do not copy their branding, unrelated widgets, appointment features or patient wellness metrics. FreshPaddy was supplied as a reference but was inaccessible during initial research; do not claim its visual language has been verified.

Desktop: staff dashboard with actionable counts and recent records; reviewer detail with image and review panel side by side. Mobile: collapsible navigation, single-column forms, image preview, readable cards and no essential horizontal scrolling. Provide keyboard operation, visible focus, labelled inputs, text error messages and status labels that do not depend on colour. Target WCAG AA contrast. Include empty, loading, save-failure, expired-session and success states in the design.

No decorative charts without a defined operational question and real underlying data. No fabricated production metrics.

## 11. Implementation structure

Suggested Django apps: accounts, facilities, patients, screenings, reviews, notifications, audit. Share a custom template/component system and permission-scoped query helpers. Keep state transitions and clinical review finalisation in explicit service functions using database transactions. Use MySQL in integration checks; do not rely exclusively on SQLite for concurrency behaviour.

Use maintained compatible dependencies and pin exact versions after checking the target host. Deployment plan must include web process, static files, private media, MySQL, HTTPS, outbound mail if selected, and scheduled backup/maintenance. A separate queue worker is unnecessary for the initial in-app-only notification flow unless implementation needs change.

## 12. Build sequence

1. Use confirmed account policies, settle minimum patient fields and initial design direction; initialise Django/custom user model and MySQL configuration.
2. Implement facility/account administration, authentication and scoped permissions; verify direct-link and image isolation.
3. Implement consent, patient identity allocation, history, drafts and synthetic-data screening submissions.
4. Implement review queue, claims/concurrency, review finalisation, repeat attempts, amendments and in-app notifications.
5. Complete responsive custom UI, validation/error states and protocol configuration. Keep live clinical actions disabled until approved configuration is loaded.
6. Deploy staging; run end-to-end and restore checks; obtain client review, approved clinical inputs and operational sign-off before a real-patient pilot.

## 13. Acceptance checklist

- Administrator can create a facility, activate individual staff accounts, create reviewers, assign facilities and revoke access.
- Staff in facility A cannot discover/read/edit facility B data through lists, search, dashboards, guessed URLs, requests or images. Reviewer assignments are enforced the same way.
- A consented patient receives one globally unique patient ID; simultaneous registrations cannot collide. Returning visits reuse the patient record.
- Declining consent does not persist new identifiable patient details or an image.
- Drafts and submitted records survive logout, browser closure and application restart. Images remain available to authorised users.
- Valid upload and submission succeed; corrupt, oversized and failed uploads produce useful errors without false confirmation.
- Repeated submission requests do not duplicate an attempt. A failed database/media operation does not leave a successful-looking record.
- New submissions show Pending review and no invented clinical finding.
- A reviewer can save a review only within assigned scope and using an approved protocol. Two reviewers cannot silently overwrite one another.
- Staff can see a saved review, next step, reviewer/time and patient history; neutral in-app notification links to the authorised detail.
- Repeat requests and unreadable outcomes work without a risk category; replacement attempts preserve earlier images and review actions.
- Review amendments require a reason and preserve previous versions and attribution.
- Accounts, records, review actions and significant edits have an audit trail. Deactivation preserves attribution.
- Mobile screening and desktop review work with keyboard/focus/error states checked.
- A backup restores both database records and images into a separate test environment; document recovery results.
- Deployment uses HTTPS, protected media, production configuration and agreed privileged-account MFA.
- Demonstration uses synthetic data. Real-patient operation requires approved strip/protocol/consent configuration and operational arrangements.

## 14. Handover and exclusions

Deliver a working test URL, secure credential/activation handover, short walkthrough, setup/deployment instructions, configured dependency versions, schema/migration instructions, backup/restore guide, account/permission guide, operational contacts and known limitations.

Deferred: public signup, patient portal, landing page, AI/image classification, automatic risk scoring, payments, appointments, chat, SMS/WhatsApp notifications, offline synchronisation, cross-facility identity linking, bulk exports and advanced analytics. Revisit only through an explicit scope decision.

## 15. Inputs to request from the client

1. Exact strip packaging and current manufacturer instructions for the purchased product; clinically approved observation options, units, next steps and any authorised risk mapping.
2. Minimum patient and identity-verification fields; consent wording/version; policy for consent withdrawal and retained records.
3. Facility names/codes, staff list, reviewer list and assignments; pilot owner and support contact.
4. Retention/backup expiry, approved hosting/data arrangements and responsible operational owner.
5. Logo/brand assets if available; any further client refinements to the confirmed account policies and portal-only notifications.
6. Written clarification of the programme's coded/no-code acceptance requirement.

These are review inputs, not assumptions to hide in code. Engineering can start on synthetic data using the confirmed account policies; pilot readiness remains conditional on the outstanding approvals.
