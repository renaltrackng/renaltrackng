import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings

class Facility(models.Model):
    name = models.CharField(max_length=160)
    code = models.SlugField(max_length=12, unique=True)
    city = models.CharField(max_length=100, blank=True)
    active = models.BooleanField(default=True)
    next_patient = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Administrator'
        STAFF = 'staff', 'Facility staff'
        REVIEWER = 'reviewer', 'Reviewer'
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.STAFF)
    facility = models.ForeignKey(Facility, null=True, blank=True, on_delete=models.PROTECT, related_name='staff')
    assigned_facilities = models.ManyToManyField(Facility, blank=True, related_name='reviewers')
    can_review = models.BooleanField(default=False)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)
    @property
    def display_name(self): return self.get_full_name() or self.email
    @property
    def initials(self): return ''.join(x[0] for x in self.display_name.split()[:2]).upper()
    @property
    def is_reviewer(self): return self.role in (self.Role.REVIEWER, self.Role.ADMIN)
    @property
    def can_screen(self): return self.role in (self.Role.STAFF, self.Role.ADMIN)

class Patient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    public_id = models.CharField(max_length=30, unique=True)
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT)
    name = models.CharField(max_length=120, help_text='Demo name or approved participant identifier')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']
    def __str__(self): return f'{self.public_id} · {self.name}'

class Protocol(models.Model):
    name = models.CharField(max_length=150)
    version = models.CharField(max_length=30, unique=True)
    instructions = models.TextField()
    observation_options = models.JSONField(default=list)
    next_steps = models.JSONField(default=list)
    consent_text = models.TextField()
    is_demo = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f'{self.name} · {self.version}'

class Screening(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PENDING = 'pending', 'Pending review'
        REPEAT = 'repeat', 'Repeat requested'
        UNREADABLE = 'unreadable', 'Unable to read'
        REVIEWED = 'reviewed', 'Reviewed'
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='screenings')
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    protocol = models.ForeignKey(Protocol, on_delete=models.PROTECT)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT, db_index=True)
    risk_factors = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    claimed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='claims')
    claim_expires = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['facility', 'status', 'submitted_at'])]
    @property
    def latest_review(self): return self.reviews.order_by('-version').first()

class Consent(models.Model):
    screening = models.OneToOneField(Screening, on_delete=models.PROTECT)
    notice_version = models.CharField(max_length=30)
    notice_text = models.TextField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

def image_path(instance, filename):
    return f'screenings/{instance.screening_id}/{uuid.uuid4().hex}.png'

class Attempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    screening = models.ForeignKey(Screening, on_delete=models.PROTECT, related_name='attempts')
    number = models.PositiveIntegerField()
    image = models.ImageField(upload_to=image_path)
    product = models.CharField(max_length=140)
    lot = models.CharField(max_length=80)
    expiry = models.DateField()
    captured_at = models.DateTimeField()
    note = models.CharField(max_length=500, blank=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    submitted_at = models.DateTimeField(auto_now_add=True)
    request_key = models.UUIDField(unique=True)
    class Meta:
        ordering = ['-number']
        constraints = [models.UniqueConstraint(fields=['screening', 'number'], name='unique_attempt_number')]

class Review(models.Model):
    screening = models.ForeignKey(Screening, on_delete=models.PROTECT, related_name='reviews')
    attempt = models.ForeignKey(Attempt, on_delete=models.PROTECT)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    decision = models.CharField(max_length=15, choices=[('reviewed', 'Complete review'), ('repeat', 'Request repeat'), ('unreadable', 'Unable to read')])
    observation = models.CharField(max_length=180, blank=True)
    next_step = models.CharField(max_length=250, blank=True)
    note = models.TextField()
    amendment_reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-version']
        constraints = [models.UniqueConstraint(fields=['screening', 'version'], name='unique_review_version')]

class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    screening = models.ForeignKey(Screening, on_delete=models.PROTECT)
    text = models.CharField(max_length=160, default='A screening review has been updated.')
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']

class Audit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=100)
    target = models.CharField(max_length=100)
    detail = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']

class LoginThrottle(models.Model):
    key = models.CharField(max_length=64, unique=True)
    failures = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField()


class ContactMessage(models.Model):
    class Kind(models.TextChoices):
        PHARMACY = 'pharmacy', 'Pharmacist / pharmacy'
        CHW = 'chw', 'Community Health Worker'
        ORGANISATION = 'organisation', 'Healthcare organisation'
        PARTNER = 'partner', 'Partner or investor'
        INDIVIDUAL = 'individual', 'Individual / patient'
        OTHER = 'other', 'Other'
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    kind = models.CharField('I am a', max_length=20, choices=Kind.choices, default=Kind.OTHER)
    message = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)
    read = models.BooleanField(default=False)
    is_spam = models.BooleanField(default=False)
    ip_hash = models.CharField(max_length=64, blank=True)
    class Meta: ordering = ['-created_at']
    def __str__(self): return f'{self.name} <{self.email}>'
