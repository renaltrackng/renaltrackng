import io
import secrets
import uuid
from datetime import timedelta
from PIL import Image, ImageDraw
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from django.utils import timezone
from core.models import User, Facility, Protocol, Screening
from core.services import start_screening, submit_attempt, claim_review, save_review

class Command(BaseCommand):
    help = 'Seed synthetic demo data. Prints credentials only when accounts are newly created.'
    def handle(self, *args, **options):
        if not settings.DEMO_MODE: raise CommandError('Demo seeding is disabled outside demo mode.')
        facilities = []
        for code, name, city in [('LAF', 'Lafia Community Pharmacy', 'Lagos'), ('GRN', 'Greenfield Health Centre', 'Abuja'), ('HOP', 'Hope Community Outreach', 'Ibadan')]:
            facility, _ = Facility.objects.get_or_create(code=code, defaults={'name': name, 'city': city})
            facilities.append(facility)
        protocol, _ = Protocol.objects.get_or_create(version='demo-v1', defaults={
            'name': 'Synthetic screening workflow',
            'instructions': 'For demonstration only: use the supplied synthetic image to test capture and review. Actual product-specific procedures must be supplied and approved before clinical use.',
            'observation_options': ['Demo observation recorded — no clinical meaning'],
            'next_steps': ['Demo workflow complete — no clinical advice'],
            'consent_text': 'This is a demonstration using synthetic information. RenalTrack records screening details and a photograph for manual review by authorised personnel. Staff at this facility and assigned reviewers can access the record. This tool does not diagnose or rule out kidney disease. No real patient information should be entered into this preview.'})
        accounts = [
            ('admin@renaltrack.demo', 'Ada', 'Okafor', 'admin', None),
            ('staff@renaltrack.demo', 'Chidinma', 'Obi', 'staff', facilities[0]),
            ('reviewer@renaltrack.demo', 'Tomi', 'Adebayo', 'reviewer', None),
            ('staff2@renaltrack.demo', 'Ibrahim', 'Bello', 'staff', facilities[1]),
            ('staff3@renaltrack.demo', 'Funmi', 'Adeyemi', 'staff', facilities[2]),
        ]
        users = []
        for email, first, last, role, facility in accounts:
            user, created = User.objects.get_or_create(email=email, defaults={'username': uuid.uuid4().hex, 'first_name': first, 'last_name': last, 'role': role, 'facility': facility})
            if created:
                password = secrets.token_urlsafe(15)
                user.set_password(password)
                user.save()
                self.stdout.write(f'{email} | {password}')
            users.append(user)
        reviewer = users[2]
        reviewer.assigned_facilities.set(facilities)
        if Screening.objects.exists():
            self.stdout.write('Demo records already exist; kept unchanged.')
            return
        names = ['Demo · Amara N.', 'Demo · Emeka O.', 'Demo · Amina Y.', 'Demo · David A.', 'Demo · Zainab B.', 'Demo · Femi K.', 'Demo · Grace E.', 'Demo · Musa S.', 'Demo · Bola T.', 'Demo · Ngozi C.', 'Demo · Samuel I.', 'Demo · Fatima A.']
        for i, name in enumerate(names):
            staff = [users[1], users[3], users[4]][i % 3]
            screening = start_screening(staff, protocol, name)
            screening.risk_factors = {'diabetes': 'unknown', 'hypertension': 'not_provided', 'kidney_disease': 'no', 'family_history': 'unknown'}
            screening.save()
            image = Image.new('RGB', (1100, 600), '#eef0e5')
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((100, 100, 1000, 500), radius=30, fill='#ffffff', outline='#c9d1ba', width=2)
            draw.text((150, 150), 'RENALTRACK - SYNTHETIC DEMO IMAGE', fill='#285844', font_size=28)
            draw.text((150, 195), 'Not a patient sample. Not for clinical interpretation.', fill='#7c8d6e', font_size=20)
            draw.rounded_rectangle((190, 300, 900, 355), radius=6, fill='#e6dfbf')
            draw.rectangle((760, 300, 820, 355), fill='#beb6a2')
            data = io.BytesIO(); image.save(data, 'PNG')
            submit_attempt(staff, screening.pk, {'revision': screening.revision, 'request_key': uuid.uuid4(), 'product': 'Synthetic demo strip', 'lot': 'DEMO-001', 'expiry': timezone.localdate() + timedelta(days=120), 'captured_at': timezone.now(), 'image': ContentFile(data.getvalue(), name='demo.png'), 'note': 'Synthetic demonstration record.'})
            screening.refresh_from_db()
            if i % 4 in (1, 2):
                claim_review(reviewer, screening.pk)
                save_review(reviewer, screening.pk, {'revision': screening.revision, 'decision': 'reviewed' if i % 4 == 1 else 'repeat', 'observation': protocol.observation_options[0], 'next_step': protocol.next_steps[0], 'note': 'Synthetic review completed for demonstration.' if i % 4 == 1 else 'Demonstration repeat request. Follow the approved procedure before a fresh attempt.'})
            Screening.objects.filter(pk=screening.pk).update(submitted_at=timezone.now() - timedelta(days=i % 7, hours=i))
        self.stdout.write(self.style.SUCCESS('Synthetic demo ready. No real clinical findings were generated.'))
