import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.db import connection, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse


class DeploymentRegressionTests(TestCase):
    def test_healthcheck_is_public_and_uncached(self):
        response = self.client.get(reverse('healthcheck'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertEqual(response['Cache-Control'], 'no-store')

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_healthcheck_accepts_plain_http_probe(self):
        self.assertEqual(self.client.get(reverse('healthcheck')).status_code, 200)

    def test_healthcheck_hides_database_errors(self):
        with patch('django.db.connection.cursor', side_effect=DatabaseError('private connection details')):
            response = self.client.get(reverse('healthcheck'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable'})

    def test_railway_settings_keep_private_media_and_static_serving(self):
        environment = {
            'DJANGO_DEBUG': '0', 'DEMO_MODE': '1', 'DB_ENGINE': 'sqlite',
            'DJANGO_SECRET_KEY': 'configuration-test-only-not-a-deployed-secret',
            'DJANGO_ALLOWED_HOSTS': 'custom.example.com',
            'RAILWAY_PUBLIC_DOMAIN': 'test.up.railway.app',
            'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://custom.example.com',
            'DJANGO_MEDIA_ROOT': '/data/private_media', 'DJANGO_TRUST_PROXY': '1',
        }
        with patch.dict(os.environ, environment):
            config = runpy.run_path(str(settings.BASE_DIR / 'renaltrack/settings.py'))
        self.assertIn('test.up.railway.app', config['ALLOWED_HOSTS'])
        self.assertIn('healthcheck.railway.app', config['ALLOWED_HOSTS'])
        self.assertIn('custom.example.com', config['ALLOWED_HOSTS'])
        self.assertIn('https://test.up.railway.app', config['CSRF_TRUSTED_ORIGINS'])
        self.assertIn('https://custom.example.com', config['CSRF_TRUSTED_ORIGINS'])
        self.assertEqual(config['MEDIA_ROOT'], Path('/data/private_media'))
        self.assertEqual(config['SECURE_PROXY_SSL_HEADER'], ('HTTP_X_FORWARDED_PROTO', 'https'))
        self.assertTrue(config['SECURE_SSL_REDIRECT'])
        self.assertEqual(config['MIDDLEWARE'][1], 'whitenoise.middleware.WhiteNoiseMiddleware')
        self.assertEqual(config['STORAGES']['staticfiles']['BACKEND'], 'whitenoise.storage.CompressedStaticFilesStorage')


class HistoricalScreeningMigrationTests(TransactionTestCase):
    """Apply the upgrade to real historical model rows in an isolated test DB."""
    def test_upgrade_preserves_existing_protocol_reviews_and_attempts(self):
        executor = MigrationExecutor(connection)
        previous = [('core', '0002_contactmessage')]
        latest = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate(previous)
            apps = executor.loader.project_state(previous).apps
            User = apps.get_model('core', 'User')
            Facility = apps.get_model('core', 'Facility')
            Patient = apps.get_model('core', 'Patient')
            Protocol = apps.get_model('core', 'Protocol')
            Screening = apps.get_model('core', 'Screening')
            Attempt = apps.get_model('core', 'Attempt')
            Review = apps.get_model('core', 'Review')
            from django.utils import timezone
            import uuid
            facility = Facility.objects.create(name='Migration test', code='HIS')
            user = User.objects.create(username='history', email='history@example.com', role='admin')
            patient = Patient.objects.create(public_id='HIS-000001', name='Synthetic history', facility=facility, created_by=user)
            protocol = Protocol.objects.create(name='Urine albumin screening', version='UA-1.0',
                observation_options=['Negative', 'Trace', 'Positive (1+)', 'Positive (2+)', 'Positive (3+ or higher)'],
                next_steps=['Historical next step'], instructions='Original recorded instructions', consent_text='Original consent')
            screening = Screening.objects.create(patient=patient, facility=facility, protocol=protocol, submitted_by=user, status='reviewed')
            attempt = Attempt.objects.create(screening=screening, number=1, product='Urine albumin test strip', lot='UA24117',
                expiry=timezone.localdate(), captured_at=timezone.now(), submitted_by=user, request_key=uuid.uuid4(), image='screenings/historical.png')
            note = 'Good-quality photo. No colour change on the albumin pad.'
            for index, observation in enumerate(['Negative', 'Trace', 'Positive (1+)', 'Positive (2+)', 'Positive (3+ or higher)'], 1):
                Review.objects.create(screening=screening, attempt=attempt, reviewer=user, version=index,
                    decision='reviewed', observation=observation, note=note, next_step='Historical next step')
            before = {name: list(apps.get_model('core', name).objects.order_by('pk').values()) for name in ['Protocol', 'Attempt', 'Review']}
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            upgraded_apps = executor.loader.project_state(latest).apps
            for name, rows in before.items():
                self.assertEqual(list(upgraded_apps.get_model('core', name).objects.order_by('pk').values()), rows, name)
        finally:
            # Other tests must always see the latest schema, even if an assertion fails.
            MigrationExecutor(connection).migrate(latest)
