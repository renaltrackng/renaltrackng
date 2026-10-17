from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from .models import Facility, Patient, Screening, Consent, Attempt, Review, Notification, Audit, User

def audit(user, action, target, detail=''):
    Audit.objects.create(actor=user, action=action, target=str(target), detail=detail)

@transaction.atomic
def start_screening(user, protocol, name=None, patient=None):
    if user.role != 'staff' or not user.facility_id: raise PermissionDenied
    facility = Facility.objects.select_for_update().get(pk=user.facility_id, active=True)
    if patient is not None and patient.facility_id != facility.pk: raise PermissionDenied
    if patient is None:
        patient = Patient.objects.create(public_id=f'{facility.code}-{facility.next_patient:06d}', name=name, facility=facility, created_by=user)
        facility.next_patient += 1
        facility.save(update_fields=['next_patient'])
        audit(user, 'Patient registered', patient.pk)
    screening = Screening.objects.create(patient=patient, facility=facility, protocol=protocol, submitted_by=user)
    Consent.objects.create(screening=screening, notice_version=protocol.version, notice_text=protocol.consent_text, recorded_by=user)
    audit(user, 'Consent recorded; screening created', screening.pk)
    return screening

def submit_attempt(user, screening_id, data):
    saved_image = None
    try:
        with transaction.atomic():
            screening = Screening.objects.select_for_update().select_related('facility').get(pk=screening_id)
            if user.role != 'staff' or user.facility_id != screening.facility_id or not screening.facility.active: raise PermissionDenied
            existing = Attempt.objects.filter(request_key=data['request_key']).first()
            if existing:
                if existing.screening_id != screening.pk: raise ValidationError('This submission token has already been used.')
                return screening
            if screening.revision != data['revision'] or screening.status not in ('draft', 'repeat'): raise ValidationError('This screening changed. Refresh before submitting again.')
            if len(screening.risk_factors) != 4 or not hasattr(screening, 'consent'): raise ValidationError('Complete consent and risk factors first.')
            attempt = Attempt(screening=screening, number=screening.attempts.count() + 1, product=data['product'], lot=data['lot'], expiry=data['expiry'], captured_at=data['captured_at'], note=data.get('note', ''), submitted_by=user, request_key=data['request_key'])
            attempt.image.save('screening.png', data['image'], save=False)
            saved_image = (attempt.image.storage, attempt.image.name)
            attempt.save()
            screening.status = 'pending'
            screening.submitted_at = timezone.now()
            screening.revision += 1
            screening.claimed_by = None
            screening.claim_expires = None
            screening.save()
            audit(user, 'Screening submitted', screening.pk, f'Attempt {attempt.number}')
            return screening
    except Exception:
        if saved_image:
            saved_image[0].delete(saved_image[1])
        raise

def reviewer_allowed(user, screening):
    return user.is_reviewer and (user.role == 'admin' or user.assigned_facilities.filter(pk=screening.facility_id).exists())

@transaction.atomic
def claim_review(user, screening_id, release=False):
    screening = Screening.objects.select_for_update().get(pk=screening_id)
    if not reviewer_allowed(user, screening): raise PermissionDenied
    if screening.status not in ('pending', 'reviewed'): raise ValidationError('This screening is not available for review.')
    if screening.claimed_by_id and screening.claimed_by_id != user.pk and screening.claim_expires and screening.claim_expires > timezone.now(): raise ValidationError('Another reviewer is working on this screening. Try again after the claim expires.')
    screening.claimed_by = None if release else user
    screening.claim_expires = None if release else timezone.now() + timedelta(minutes=15)
    screening.save(update_fields=['claimed_by', 'claim_expires'])
    audit(user, 'Review released' if release else 'Review claimed', screening.pk)
    return screening

@transaction.atomic
def save_review(user, screening_id, data):
    screening = Screening.objects.select_for_update().select_related('protocol').get(pk=screening_id)
    if not reviewer_allowed(user, screening): raise PermissionDenied
    if screening.revision != data['revision'] or screening.status not in ('pending', 'reviewed'): raise ValidationError('This record changed. Refresh to see the latest version.')
    if screening.claimed_by_id != user.pk or not screening.claim_expires or screening.claim_expires <= timezone.now(): raise ValidationError('Claim this screening before saving. Your previous claim may have expired.')
    if screening.status == 'reviewed' and (not data.get('amendment_reason') or data['decision'] != 'reviewed'): raise ValidationError('Completed reviews require an amendment reason.')
    if data['decision'] == 'reviewed' and (data.get('observation') not in screening.protocol.observation_options or data.get('next_step') not in screening.protocol.next_steps): raise ValidationError('Choose the configured observation and next step.')
    Review.objects.create(screening=screening, attempt=screening.attempts.first(), reviewer=user, version=screening.reviews.count() + 1, decision=data['decision'], observation=data.get('observation', '') if data['decision'] == 'reviewed' else '', next_step=data.get('next_step', '') if data['decision'] == 'reviewed' else '', note=data['note'], amendment_reason=data.get('amendment_reason', ''))
    screening.status = data['decision']
    screening.revision += 1
    screening.claimed_by = None
    screening.claim_expires = None
    screening.save()
    Notification.objects.bulk_create([Notification(user=u, screening=screening) for u in User.objects.filter(facility=screening.facility, role='staff', is_active=True)])
    audit(user, 'Review amended' if data.get('amendment_reason') else 'Review saved', screening.pk, f'Version {screening.reviews.count()}; {data["decision"]}')
    return screening
