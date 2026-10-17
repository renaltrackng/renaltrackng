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
PROTOCOL = {
    'version': 'UA-1.0',
    'name': 'Urine albumin screening',
    'instructions': 'Collect a fresh mid-stream urine sample in a clean, dry container. Dip the strip fully for 1–2 seconds, tap off excess urine on the rim and lay the strip flat. Photograph it within the reading time printed on the pack, with the colour chart in frame.',
    'observation_options': ['Negative', 'Trace', 'Positive (1+)', 'Positive (2+)', 'Positive (3+ or higher)'],
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

PRODUCT, LOT = 'Urine albumin test strip', 'UA24117'

REVIEWED = [
    ('Trace', 'Repeat screening in 3 months', 'Clear photo, read within the time window. The albumin pad shows a faint colour change consistent with trace. Please advise the patient to return in 3 months.'),
    ('Negative', 'No further action — rescreen at the routine interval', 'Good-quality photo. No colour change on the albumin pad.'),
    ('Positive (1+)', 'Refer to a clinician for confirmatory laboratory tests (uACR and eGFR)', 'Albumin pad matches 1+ on the chart. Patient reports hypertension — please refer for uACR and eGFR.'),
]
REPEAT_NOTE = 'The photo is blurred and the colour chart is out of frame. Please repeat with a fresh strip.'

# Albumin pad colours from negative (yellow) to high (green-blue).
PAD_SCALE = ['#e9e27a', '#d6dd78', '#b6d27e', '#8fc28a', '#69ae97']


def strip_photo(level=0, seed=0):
    """Render a realistic-looking photo of a reagent strip beside its colour chart."""
    rnd = random.Random(seed)
    w, h = 1200, 800
    base = rnd.choice([(232, 228, 219), (226, 230, 228), (236, 232, 224)])
    img = Image.new('RGB', (w, h), base)
    d = ImageDraw.Draw(img)
    # Soft lighting gradient on the table surface
    for y in range(h):
        k = 1 - 0.10 * (y / h)
        d.line([(0, y), (w, y)], fill=tuple(int(c * k) for c in base))
    # Colour chart card
    card = (110, 150, 470, 650)
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((card[0] + 8, card[1] + 12, card[2] + 8, card[3] + 12), 18, fill=(40, 40, 30, 60))
    img = Image.alpha_composite(img.convert('RGBA'), layer.filter(ImageFilter.GaussianBlur(10))).convert('RGB')
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(card, 18, fill='#fbfbf8', outline='#dcdcd4', width=2)
    d.rectangle((card[0], card[1], card[2], card[1] + 54), fill='#0b6b52')
    d.text((card[0] + 22, card[1] + 16), 'ALBUMIN', fill='#ffffff', font_size=22)
    for i, colour in enumerate(PAD_SCALE):
        y = card[1] + 84 + i * 80
        d.rounded_rectangle((card[0] + 30, y, card[0] + 120, y + 56), 8, fill=colour, outline='#d0d0c6')
        d.text((card[0] + 145, y + 14), ['Negative', 'Trace', '1+', '2+', '3+'][i], fill='#3a3f3c', font_size=24)
    # Test strip (angled slightly)
    strip = Image.new('RGBA', (600, 120), (0, 0, 0, 0))
    sd = ImageDraw.Draw(strip)
    sd.rounded_rectangle((0, 20, 590, 96), 10, fill='#fdfdfb', outline='#d8d8d0', width=2)
    pads = ['#f3e9b5', '#efe7c4', PAD_SCALE[level], '#efe6c8']
    for i, colour in enumerate(pads):
        x = 290 + i * 72
        sd.rounded_rectangle((x, 30, x + 56, 86), 6, fill=colour)
    sd.rectangle((0, 20, 120, 96), fill='#eeeeea')
    strip = strip.rotate(rnd.uniform(-6, 6), resample=Image.BICUBIC, expand=True)
    sh = Image.new('RGBA', strip.size, (0, 0, 0, 0))
    sh.paste((40, 40, 30, 70), mask=strip.split()[3])
    sh = sh.filter(ImageFilter.GaussianBlur(9))
    pos = (540 + rnd.randint(-15, 15), 330 + rnd.randint(-30, 30))
    img.paste(sh, (pos[0] + 10, pos[1] + 14), sh)
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
