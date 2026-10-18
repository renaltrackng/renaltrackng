import io
import uuid
import tempfile
from datetime import timedelta
from PIL import Image
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from .models import User, Facility, Protocol, Patient, Screening, Consent, Attempt, Review, Notification, Audit
from .forms import UploadForm, ReviewForm
from .services import start_screening, submit_attempt, claim_review, save_review

class WorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Facility.objects.create(name='Facility A', code='AAA')
        cls.b = Facility.objects.create(name='Facility B', code='BBB')
        cls.staff = User.objects.create_user(username='staff', email='staff@example.com', password='Unique-demo-secret-42', role='staff', facility=cls.a)
        cls.other = User.objects.create_user(username='other', email='other@example.com', password='Unique-demo-secret-42', role='staff', facility=cls.b)
        cls.reviewer = User.objects.create_user(username='reviewer', email='reviewer@example.com', password='Unique-demo-secret-42', role='reviewer')
        cls.reviewer.assigned_facilities.add(cls.a)
        cls.admin = User.objects.create_user(username='admin', email='admin@example.com', password='Unique-demo-secret-42', role='admin')
        cls.protocol = Protocol.objects.create(name='Demo', version='test-v1', instructions='Demo only', observation_options=['Demo observation'], next_steps=['Demo next step'], consent_text='Demo consent')
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.media = override_settings(MEDIA_ROOT=self.temp.name)
        self.media.enable()
        self.addCleanup(self.media.disable)
        self.addCleanup(self.temp.cleanup)
    def image(self):
        output = io.BytesIO(); Image.new('RGB', (80, 80), '#dddddd').save(output, 'PNG')
        return SimpleUploadedFile('strip.png', output.getvalue(), content_type='image/png')
    def draft(self, user=None):
        s = start_screening(user or self.staff, self.protocol, 'Synthetic participant')
        s.risk_factors = {'diabetes': 'no', 'hypertension': 'unknown', 'kidney_disease': 'no', 'family_history': 'not_provided'}
        s.save()
        return s
    def upload_data(self, s):
        return {'revision': s.revision, 'request_key': uuid.uuid4(), 'product': 'Demo', 'lot': 'LOT', 'expiry': timezone.localdate() + timedelta(days=1), 'captured_at': timezone.now(), 'image': self.image(), 'note': ''}
    def submitted(self):
        s = self.draft(); submit_attempt(self.staff, s.pk, self.upload_data(s)); s.refresh_from_db(); return s
    def review_data(self, s):
        return {'revision': s.revision, 'decision': 'reviewed', 'observation': 'Demo observation', 'next_step': 'Demo next step', 'note': 'Demo review'}
    def test_patient_ids_and_consent(self):
        first = self.draft(); second = self.draft()
        self.assertEqual(first.patient.public_id, 'AAA-000001')
        self.assertEqual(second.patient.public_id, 'AAA-000002')
        self.assertEqual(Consent.objects.count(), 2)
    def test_repeat_visit_reuses_patient(self):
        first = self.draft(); second = start_screening(self.staff, self.protocol, patient=first.patient)
        self.assertEqual(second.patient_id, first.patient_id)
        self.assertEqual(Patient.objects.count(), 1)
    def test_declined_consent_creates_nothing(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('screening_start'), {'name': 'No consent'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Patient.objects.count(), 0)
    def test_submission_idempotent_and_persistent(self):
        s = self.draft(); data = self.upload_data(s)
        submit_attempt(self.staff, s.pk, data); submit_attempt(self.staff, s.pk, data)
        self.assertEqual(Attempt.objects.count(), 1)
        s.refresh_from_db(); self.assertEqual(s.status, 'pending')
        self.client.force_login(self.staff)
        self.client.logout(); self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('screening_detail', args=[s.pk])).status_code, 200)
        response = self.client.get(reverse('protected_image', args=[s.attempts.first().pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b''.join(response.streaming_content))
        response.close()
    def test_cross_facility_records_and_images_denied(self):
        s = self.submitted(); self.client.force_login(self.other)
        for name, pk in [('screening_detail', s.pk), ('patient_detail', s.patient_id), ('protected_image', s.attempts.first().pk)]:
            self.assertEqual(self.client.get(reverse(name, args=[pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('patients')), s.patient.public_id)
    def test_unassigned_reviewer_denied(self):
        s = self.draft(self.other); self.client.force_login(self.reviewer)
        self.assertEqual(self.client.get(reverse('screening_detail', args=[s.pk])).status_code, 404)
    def test_staff_cannot_review_or_manage(self):
        s = self.submitted(); self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse('screening_detail', args=[s.pk]), {'action': 'claim'}).status_code, 403)
        for name in ['users', 'facilities', 'audit', 'protocols']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)
    def test_review_requires_claim(self):
        s = self.submitted()
        with self.assertRaises(ValidationError): save_review(self.reviewer, s.pk, self.review_data(s))
    def test_review_and_notification(self):
        s = self.submitted(); claim_review(self.reviewer, s.pk); save_review(self.reviewer, s.pk, self.review_data(s))
        s.refresh_from_db(); self.assertEqual(s.status, 'reviewed')
        self.assertEqual(Notification.objects.filter(user=self.staff).count(), 1)
        self.assertTrue(Audit.objects.filter(action='Review saved').exists())
    def test_stale_review_rejected(self):
        s = self.submitted(); claim_review(self.reviewer, s.pk); data = self.review_data(s)
        save_review(self.reviewer, s.pk, data)
        with self.assertRaises(ValidationError): save_review(self.reviewer, s.pk, data)
        self.assertEqual(Review.objects.count(), 1)
    def test_claim_collision(self):
        s = self.submitted(); claim_review(self.reviewer, s.pk)
        self.admin.can_review = True; self.admin.save()
        with self.assertRaises(ValidationError): claim_review(self.admin, s.pk)
    def test_review_amendment_preserves_history(self):
        s = self.submitted(); claim_review(self.reviewer, s.pk); save_review(self.reviewer, s.pk, self.review_data(s)); s.refresh_from_db()
        claim_review(self.reviewer, s.pk); data = self.review_data(s)
        with self.assertRaises(ValidationError): save_review(self.reviewer, s.pk, data)
        data['amendment_reason'] = 'Corrected demo wording'
        save_review(self.reviewer, s.pk, data)
        self.assertEqual(s.reviews.count(), 2)
    def test_repeat_attempt_preserves_original(self):
        s = self.submitted(); claim_review(self.reviewer, s.pk); data = self.review_data(s); data['decision'] = 'repeat'
        save_review(self.reviewer, s.pk, data); s.refresh_from_db()
        submit_attempt(self.staff, s.pk, self.upload_data(s)); s.refresh_from_db()
        self.assertEqual(s.status, 'pending'); self.assertEqual(s.attempts.count(), 2)
        self.assertEqual(s.reviews.count(), 1)
    def test_unreadable_has_no_observation(self):
        s = self.submitted(); claim_review(self.reviewer, s.pk); data = self.review_data(s); data['decision'] = 'unreadable'
        save_review(self.reviewer, s.pk, data)
        self.assertEqual(s.reviews.first().observation, '')
    def test_corrupt_upload_rejected(self):
        s = self.draft(); data = self.upload_data(s); data['confirmed'] = True
        form = UploadForm(data, {'image': SimpleUploadedFile('bad.png', b'not an image', content_type='image/png')})
        self.assertFalse(form.is_valid()); self.assertIn('image', form.errors)
    def test_review_options_validated(self):
        s = self.submitted(); data = self.review_data(s); data['observation'] = 'Invented risk'
        self.assertFalse(ReviewForm(data, screening=s).is_valid())
    def test_disabled_facility_loses_access(self):
        self.client.force_login(self.staff); self.a.active = False; self.a.save()
        self.assertRedirects(self.client.get(reverse('dashboard')), reverse('login'))
    def test_admin_cannot_remove_own_access(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('user_edit', args=[self.admin.pk]), {'email': self.admin.email, 'role': 'staff', 'facility': self.a.pk, 'is_active': 'on'})
        self.assertContains(response, 'cannot disable or remove')
    def test_all_role_screens_render(self):
        for user in [self.staff, self.reviewer, self.admin]:
            self.client.force_login(user)
            for name in ['dashboard', 'screenings', 'patients', 'notifications', 'profile', 'password_change']:
                self.assertEqual(self.client.get(reverse(name)).status_code, 200, f'{user.role} {name}')
        for name in ['users', 'facilities', 'facility_create', 'user_create', 'protocols', 'audit']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
    def test_access_link_sets_password_once(self):
        u = User.objects.create(username='invited', email='invite@example.com', role='reviewer'); u.set_unusable_password(); u.save()
        token = default_token_generator.make_token(u)
        url = reverse('activate', kwargs={'uidb64': urlsafe_base64_encode(force_bytes(u.pk)), 'token': token})
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {'new_password1': 'Super-unique-demo-94', 'new_password2': 'Super-unique-demo-94'})
        u.refresh_from_db(); self.assertTrue(u.check_password('Super-unique-demo-94'))
        self.assertContains(self.client.get(url), 'invalid or has expired')
    def test_login_rate_limit(self):
        for _ in range(10): self.client.post(reverse('login'), {'username': self.staff.email, 'password': 'wrong'})
        response = self.client.post(reverse('login'), {'username': self.staff.email, 'password': 'Unique-demo-secret-42'})
        self.assertContains(response, 'Too many attempts')
    def test_no_public_media_route(self):
        self.assertEqual(self.client.get('/media/anything.png').status_code, 404)
    def test_complete_http_workflow(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('screening_start'), {'consent': 'on', 'name': 'Demo HTTP participant'})
        s = Screening.objects.get()
        self.assertRedirects(response, reverse('screening_risks', args=[s.pk]))
        response = self.client.post(reverse('screening_risks', args=[s.pk]), {'diabetes': 'no', 'hypertension': 'unknown', 'kidney_disease': 'no', 'family_history': 'not_provided'})
        self.assertRedirects(response, reverse('screening_upload', args=[s.pk]))
        s.refresh_from_db()
        response = self.client.post(reverse('screening_upload', args=[s.pk]), {
            'revision': s.revision, 'request_key': str(uuid.uuid4()), 'product': 'Synthetic demo', 'lot': 'LOT-2',
            'expiry': (timezone.localdate() + timedelta(days=10)).isoformat(),
            'captured_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'), 'image': self.image(), 'confirmed': 'on'})
        self.assertRedirects(response, reverse('screening_detail', args=[s.pk]))
        s.refresh_from_db(); self.assertEqual(s.status, 'pending')
        self.client.force_login(self.reviewer)
        self.client.post(reverse('screening_detail', args=[s.pk]), {'action': 'claim'})
        response = self.client.post(reverse('screening_detail', args=[s.pk]), self.review_data(s))
        self.assertRedirects(response, reverse('screening_detail', args=[s.pk]))
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse('notifications')), 'A screening review has been updated')
        response = self.client.get(reverse('screening_detail', args=[s.pk]))
        self.assertContains(response, 'Demo observation')
        self.assertContains(response, 'Demo next step')
        self.assertFalse(Notification.objects.get().read is False)
    def test_revoked_reviewer_assignment_blocks_existing_claim(self):
        s = self.submitted(); claim_review(self.reviewer, s.pk)
        self.reviewer.assigned_facilities.clear()
        with self.assertRaises(PermissionDenied): save_review(self.reviewer, s.pk, self.review_data(s))


class AdminCreatesAccountWithPasswordTests(TestCase):
    def setUp(self):
        self.facility = Facility.objects.create(name='North', code='NTH')
        self.admin = User.objects.create_user(username='adm', email='adm@example.com', password='Unique-demo-secret-42', role='admin')
        self.client.force_login(self.admin)

    def test_admin_sets_password_and_user_can_sign_in(self):
        response = self.client.post(reverse('user_create'), {'first_name': 'Kemi', 'last_name': 'Ade', 'email': 'kemi@example.com', 'role': 'staff', 'facility': self.facility.pk, 'is_active': 'on', 'password1': 'Green-river-lantern-7', 'password2': 'Green-river-lantern-7'})
        self.assertRedirects(response, reverse('users'))
        self.assertTrue(User.objects.get(email='kemi@example.com').check_password('Green-river-lantern-7'))

    def test_password_required_and_must_match(self):
        response = self.client.post(reverse('user_create'), {'first_name': 'A', 'last_name': 'B', 'email': 'x@example.com', 'role': 'reviewer', 'assigned_facilities': [self.facility.pk], 'is_active': 'on', 'password1': 'Green-river-lantern-7', 'password2': 'Different-pass-99'})
        self.assertContains(response, 'do not match')
        self.assertFalse(User.objects.filter(email='x@example.com').exists())

    def test_edit_without_password_keeps_existing(self):
        u = User.objects.create_user(username='r', email='r@example.com', password='Original-pass-1234', role='reviewer')
        u.assigned_facilities.add(self.facility)
        self.client.post(reverse('user_edit', args=[u.pk]), {'first_name': 'R', 'last_name': 'V', 'email': 'r@example.com', 'role': 'reviewer', 'assigned_facilities': [self.facility.pk], 'is_active': 'on', 'password1': '', 'password2': ''})
        u.refresh_from_db(); self.assertTrue(u.check_password('Original-pass-1234'))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AdminCanDoEverythingTests(TestCase):
    def setUp(self):
        self.facility = Facility.objects.create(name='North', code='NTH')
        self.admin = User.objects.create_user(username='adm2', email='adm2@example.com', password='Unique-demo-secret-42', role='admin')
        self.protocol = Protocol.objects.create(name='P', version='t-1', instructions='i', observation_options=['Obs'], next_steps=['Next'], consent_text='c', is_demo=True)

    def test_admin_registers_patient_submits_and_reviews(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('screening_start'), {'consent': 'on', 'facility': self.facility.pk, 'name': 'Admin Patient'})
        s = Screening.objects.get(patient__name='Admin Patient')
        self.assertRedirects(response, reverse('screening_risks', args=[s.pk]))
        self.assertTrue(s.patient.public_id.startswith('NTH-'))
        s.risk_factors = {'diabetes': 'no', 'hypertension': 'no', 'kidney_disease': 'no', 'family_history': 'no'}; s.save()
        buf = io.BytesIO(); Image.new('RGB', (40, 40), 'white').save(buf, 'PNG')
        submit_attempt(self.admin, s.pk, {'revision': s.revision, 'request_key': uuid.uuid4(), 'product': 'P', 'lot': 'L', 'expiry': timezone.localdate() + timedelta(days=5), 'captured_at': timezone.now(), 'image': SimpleUploadedFile('a.png', buf.getvalue()), 'note': ''})
        s.refresh_from_db(); self.assertEqual(s.status, 'pending')
        claim_review(self.admin, s.pk)
        save_review(self.admin, s.pk, {'revision': s.revision, 'decision': 'reviewed', 'observation': 'Obs', 'next_step': 'Next', 'note': 'ok'})
        s.refresh_from_db(); self.assertEqual(s.status, 'reviewed')

    def test_admin_must_choose_facility_for_new_patient(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('screening_start'), {'consent': 'on', 'name': 'No Facility'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Screening.objects.exists())


class FindPatientFirstTests(TestCase):
    def setUp(self):
        self.facility = Facility.objects.create(name='North', code='NTH')
        self.staff = User.objects.create_user(username='s9', email='s9@example.com', password='Unique-demo-secret-42', role='staff', facility=self.facility)
        Protocol.objects.create(name='P', version='t-9', instructions='i', observation_options=['O'], next_steps=['N'], consent_text='c', is_demo=True)
        self.patient = Patient.objects.create(public_id='NTH-000001', name='Amara Nwosu', facility=self.facility, created_by=self.staff)
        self.client.force_login(self.staff)

    def test_new_screening_opens_search_not_registration(self):
        response = self.client.get(reverse('screening_start'))
        self.assertTemplateUsed(response, 'screenings/find_patient.html')
        self.assertContains(response, 'Amara Nwosu')

    def test_search_finds_and_misses(self):
        self.assertContains(self.client.get(reverse('screening_start'), {'q': 'NTH-000001'}), 'Amara Nwosu')
        response = self.client.get(reverse('screening_start'), {'q': 'Nobody'})
        self.assertContains(response, 'No patient matches')
        self.assertContains(response, 'new=1')

    def test_register_form_only_when_asked(self):
        response = self.client.get(reverse('screening_start'), {'new': '1', 'name': 'Zara'})
        self.assertTemplateUsed(response, 'screenings/start.html')
        self.assertContains(response, 'value="Zara"')
