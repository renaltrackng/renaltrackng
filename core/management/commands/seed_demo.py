import io
import random
import secrets
import uuid
from datetime import timedelta
from PIL import Image, ImageDraw, ImageFilter
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from django.utils import timezone
from core.models import User, Facility, Protocol, Screening
from core.services import start_screening, submit_attempt, claim_review, save_review

# Showcase content. Observation options and next steps must be confirmed by the
# programme's clinical lead before use with real patients.
MICRAL_OPTIONS = ['Negative (Neg.)', '20 mg/L', '50 mg/L', '100 mg/L']

PROTOCOL = {
    'version': 'UA-1.0',
    'name': 'Urine albumin screening (Micral-Test)',
    'instructions': 'Collect a fresh urine sample in a clean, dry container. Dip the Micral-Test strip so the urine level sits between the two black bars and hold it there for about 5 seconds. Remove the strip, lay it flat, and after 1 minute compare the test pad with the colour chart on the vial. Photograph the strip beside the chart while the colour is still within the reading time.',
    'observation_options': MICRAL_OPTIONS,
    'next_steps': [
        'No further action — rescreen at the routine interval',
        'Repeat screening in 3 months',
        'Refer to a clinician for confirmatory laboratory tests (uACR and eGFR)',
        'Refer for clinical assessment within one week',
    ],
    'consent_text': 'RenalTrack records your screening details and a photo of your test strip so that a qualified reviewer can assess it. Only staff at this facility and assigned reviewers can see your record. Screening does not diagnose or rule out kidney disease — your result will be explained to you together with the recommended next step. You can decline or withdraw at any time without affecting your care.',
}

PATIENTS = ['Amara Nwosu', 'Emeka Okonkwo', 'Amina Yusuf', 'David Adeleke', 'Zainab Bello', 'Femi Kolawole',
            'Grace Edet', 'Musa Sani', 'Bola Ogunleye', 'Ngozi Chukwu', 'Samuel Ibe', 'Fatima Abubakar']

PRODUCT, LOT = 'Micral-Test (urine albumin) strip', 'MT24117'

REVIEWED = [
    ('20 mg/L', 'Repeat screening in 3 months', 'Clear photo, read at 1 minute. The test pad matches the 20 mg/L block on the chart. Please advise the patient to return in 3 months for a repeat screening.'),
    ('Negative (Neg.)', 'No further action — rescreen at the routine interval', 'Good-quality photo. The test pad matches the negative block — no colour change.'),
    ('50 mg/L', 'Refer to a clinician for confirmatory laboratory tests (uACR and eGFR)', 'Test pad matches 50 mg/L on the chart. Patient reports hypertension — please refer for uACR and eGFR.'),
]
REPEAT_NOTE = 'The photo is blurred and the colour chart is out of frame. Please repeat with a fresh strip.'

# Micral-Test colour scale: Neg., 20, 50, 100 mg/L (cream to deep rose).
PAD_SCALE = ['#f4efe3', '#f2d6cb', '#e9a9a3', '#d4545c']
PAD_LABELS = ['Neg.', '20', '50', '100']


def strip_photo(level=0, seed=0):
    """Render a realistic-looking photo of a Micral-style strip lying across its colour chart."""
    rnd = random.Random(seed)
    w, h = 1200, 800
    base = rnd.choice([(236, 238, 237), (232, 235, 236), (238, 236, 233)])
    img = Image.new('RGB', (w, h), base)
    d = ImageDraw.Draw(img)
    for y in range(h):
        k = 1 - 0.08 * (y / h)
        d.line([(0, y), (w, y)], fill=tuple(int(c * k) for c in base))
    # Vial label with the colour chart
    card = (120, 180, 1080, 470)
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((card[0] + 6, card[1] + 14, card[2] + 6, card[3] + 14), 26, fill=(40, 40, 40, 55))
    img = Image.alpha_composite(img.convert('RGBA'), layer.filter(ImageFilter.GaussianBlur(12))).convert('RGB')
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(card, 26, fill='#fbfbfa', outline='#dcdedd', width=2)
    d.text((card[0] + 34, card[1] + 30), '1 min.', fill='#262a2c', font_size=30)
    d.text((card[2] - 128, card[1] + 34), 'mg/L', fill='#3b4043', font_size=22)
    for i, colour in enumerate(PAD_SCALE):
        x = card[0] + 270 + i * 150
        d.text((x + 8, card[1] + 34), PAD_LABELS[i] if i == 0 else f'ca. {PAD_LABELS[i]}', fill='#3b4043', font_size=22)
        d.rectangle((x, card[1] + 78, x + 92, card[1] + 158), fill=colour, outline='#d9d4cc')
        for k in range(0, 72, 12):  # hatched reference squares under each block
            d.line([(x + k, card[1] + 172), (x + k + 20, card[1] + 230)], fill='#c9cccb', width=2)
        d.rectangle((x, card[1] + 172, x + 92, card[1] + 230), outline='#c9cccb')
    d.text((card[2] - 128, card[1] + 106), 'Albumin', fill='#3b4043', font_size=22)
    d.rectangle((card[0] + 34, card[1] + 250, card[2] - 34, card[1] + 262), fill='#e3e2c4')
    # Test strip laid across the vial label
    strip = Image.new('RGBA', (90, 760), (0, 0, 0, 0))
    sd = ImageDraw.Draw(strip)
    sd.rectangle((20, 0, 70, 740), fill='#fdfdfc', outline='#d6d8d7', width=2)
    sd.rectangle((20, 120, 70, 196), fill=PAD_SCALE[level])        # reagent pad
    sd.rectangle((22, 560, 68, 568), fill='#1d1f20')                # immersion bars
    sd.rectangle((22, 600, 68, 608), fill='#1d1f20')
    strip = strip.rotate(rnd.uniform(-9, -4), resample=Image.BICUBIC, expand=True)
    sh = Image.new('RGBA', strip.size, (0, 0, 0, 0)); sh.paste((30, 30, 30, 70), mask=strip.split()[3])
    sh = sh.filter(ImageFilter.GaussianBlur(8))
    pos = (150 + rnd.randint(-15, 15), 20 + rnd.randint(-10, 10))
    img.paste(sh, (pos[0] + 12, pos[1] + 14), sh)
    img.paste(strip, pos, strip)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    out = io.BytesIO(); img.save(out, 'PNG')
    return out.getvalue()


class Command(BaseCommand):
    help = 'Seed showcase data (sample facilities, accounts and screenings). Prints credentials only when accounts are newly created.'

    def handle(self, *args, **options):
        if not settings.DEMO_MODE: raise CommandError('Sample data can only be loaded in showcase mode (DEMO_MODE=1).')
        facilities = []
        for code, name, city in [('LAF', 'Lafia Community Pharmacy', 'Lagos'), ('GRN', 'Greenfield Health Centre', 'Abuja'), ('HOP', 'Hope Community Outreach', 'Ibadan')]:
            facility, _ = Facility.objects.get_or_create(code=code, defaults={'name': name, 'city': city})
            facilities.append(facility)
        protocol, _ = Protocol.objects.get_or_create(version=PROTOCOL['version'], defaults={k: v for k, v in PROTOCOL.items() if k != 'version'})
        accounts = [
            ('admin@renaltrack.demo', 'Ummi', 'Olaoye', 'admin', None),
            ('staff@renaltrack.demo', 'Chidinma', 'Obi', 'staff', facilities[0]),
            ('reviewer@renaltrack.demo', 'Reviewer', 'Account', 'reviewer', None),
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
            self.stdout.write('Screenings already exist; kept unchanged.')
            return
        for i, name in enumerate(PATIENTS):
            staff = [users[1], users[3], users[4]][i % 3]
            screening = start_screening(staff, protocol, name)
            screening.risk_factors = [
                {'diabetes': 'no', 'hypertension': 'yes', 'kidney_disease': 'no', 'family_history': 'unknown'},
                {'diabetes': 'yes', 'hypertension': 'yes', 'kidney_disease': 'no', 'family_history': 'no'},
                {'diabetes': 'unknown', 'hypertension': 'no', 'kidney_disease': 'no', 'family_history': 'yes'},
            ][i % 3]
            screening.save()
            level = [1, 0, 2, 0][i % 4]
            submit_attempt(staff, screening.pk, {'revision': screening.revision, 'request_key': uuid.uuid4(), 'product': PRODUCT, 'lot': LOT, 'expiry': timezone.localdate() + timedelta(days=240), 'captured_at': timezone.now(), 'image': ContentFile(strip_photo(level, i), name='strip.png'), 'note': '' if i % 3 else 'First-morning sample.'})
            screening.refresh_from_db()
            if i % 4 in (1, 2):
                claim_review(reviewer, screening.pk)
                if i % 4 == 1:
                    observation, next_step, note = REVIEWED[(i // 4) % len(REVIEWED)]
                    save_review(reviewer, screening.pk, {'revision': screening.revision, 'decision': 'reviewed', 'observation': observation, 'next_step': next_step, 'note': note})
                else:
                    save_review(reviewer, screening.pk, {'revision': screening.revision, 'decision': 'repeat', 'observation': '', 'next_step': '', 'note': REPEAT_NOTE})
            Screening.objects.filter(pk=screening.pk).update(submitted_at=timezone.now() - timedelta(days=i % 7, hours=i))
        self.stdout.write(self.style.SUCCESS('Sample data ready.'))
