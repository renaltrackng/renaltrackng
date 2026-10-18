import io
import warnings
from PIL import Image, ImageOps
from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.core.files.base import ContentFile
from django.utils import timezone
from .models import User, Facility, Patient, Protocol, ContactMessage

ANSWERS = [('', 'Select an answer'), ('yes', 'Yes'), ('no', 'No'), ('unknown', 'Unknown'), ('not_provided', 'Not provided')]
FACTORS = {'diabetes': 'Diabetes', 'hypertension': 'Hypertension', 'kidney_disease': 'Known kidney disease', 'family_history': 'Family history of kidney disease'}

class LoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email address', widget=forms.EmailInput(attrs={'autocomplete': 'username', 'placeholder': 'you@facility.com'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete': 'current-password', 'placeholder': 'Enter your password'}))

class StartForm(forms.Form):
    consent = forms.BooleanField(label='I have explained the consent notice and the patient has agreed to take part.')
    identity_verified = forms.BooleanField(required=False, label='I have confirmed this returning patient’s identity.')
    name = forms.CharField(max_length=120, required=False, label='Patient full name', widget=forms.TextInput(attrs={'placeholder': 'e.g. Amara Nwosu', 'autocomplete': 'off'}))
    def __init__(self, *args, patient=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.patient = patient
        if user is not None and user.role == 'admin' and not patient:
            self.fields['facility'] = forms.ModelChoiceField(
                queryset=Facility.objects.filter(active=True).order_by('name'), empty_label='Select a facility',
                label='Facility', help_text='The patient will be registered at this facility and get its patient ID prefix.')
            self.order_fields(['consent', 'facility', 'name'])
        if patient:
            self.fields.pop('name')
            self.fields['identity_verified'].required = True
        else:
            self.fields.pop('identity_verified')
            self.fields['name'].required = True

class RiskForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, label in FACTORS.items(): self.fields[key] = forms.ChoiceField(label=label, choices=ANSWERS)

class UploadForm(forms.Form):
    revision = forms.IntegerField(widget=forms.HiddenInput)
    request_key = forms.UUIDField(widget=forms.HiddenInput)
    product = forms.CharField(max_length=140, label='Test strip product', widget=forms.TextInput(attrs={'placeholder': 'Product name as printed on the pack'}))
    lot = forms.CharField(max_length=80, label='Lot / batch number', widget=forms.TextInput(attrs={'placeholder': 'e.g. UA24117'}))
    expiry = forms.DateField(label='Expiry date', widget=forms.DateInput(attrs={'type': 'date'}))
    captured_at = forms.DateTimeField(label='Photo captured at (Lagos time)', widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}))
    image = forms.ImageField(label='Strip photo', widget=forms.FileInput(attrs={'accept': 'image/jpeg,image/png', 'capture': 'environment'}))
    note = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={'rows': 3}), label='Notes (optional)')
    confirmed = forms.BooleanField(label='I have checked the photo and the details above are correct.')
    def clean_expiry(self):
        value = self.cleaned_data['expiry']
        if value < timezone.localdate(): raise forms.ValidationError('The strip expiry date has passed.')
        return value
    def clean_captured_at(self):
        value = self.cleaned_data['captured_at']
        if value > timezone.now() + timezone.timedelta(minutes=5): raise forms.ValidationError('Capture time cannot be in the future.')
        return value
    def clean_image(self):
        upload = self.cleaned_data['image']
        if upload.size > 10 * 1024 * 1024: raise forms.ValidationError('Choose an image smaller than 10 MB.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                picture = Image.open(upload)
                if picture.format not in ('JPEG', 'PNG'): raise ValueError('format')
                if picture.width * picture.height > 25_000_000: raise ValueError('dimensions')
                picture.load()
                picture = ImageOps.exif_transpose(picture).convert('RGB')
                output = io.BytesIO()
                picture.save(output, format='PNG')
            if output.tell() > 30 * 1024 * 1024: raise ValueError('decoded size')
            return ContentFile(output.getvalue(), name='screening.png')
        except Exception:
            raise forms.ValidationError('Upload a readable JPEG or PNG, up to 25 megapixels. HEIC is not supported.')

class ReviewForm(forms.Form):
    revision = forms.IntegerField(widget=forms.HiddenInput)
    decision = forms.ChoiceField(choices=[('reviewed', 'Complete review'), ('repeat', 'Request repeat'), ('unreadable', 'Unable to read')])
    observation = forms.ChoiceField(required=False)
    next_step = forms.ChoiceField(required=False)
    note = forms.CharField(max_length=2000, widget=forms.Textarea(attrs={'rows': 4}), label='Review note / reason')
    amendment_reason = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={'rows': 2}))
    def __init__(self, *args, screening, **kwargs):
        super().__init__(*args, **kwargs)
        self.screening = screening
        self.fields['observation'].choices = [('', 'Select observation')] + [(x, x) for x in screening.protocol.observation_options]
        self.fields['next_step'].choices = [('', 'Select next step')] + [(x, x) for x in screening.protocol.next_steps]
        if screening.status == 'reviewed':
            self.fields['amendment_reason'].required = True
            self.fields['decision'].choices = [('reviewed', 'Amend completed review')]
        else: self.fields.pop('amendment_reason')
    def clean(self):
        data = super().clean()
        if data.get('decision') == 'reviewed':
            if not data.get('observation'): self.add_error('observation', 'Select an observation from this protocol.')
            if not data.get('next_step'): self.add_error('next_step', 'Select a next step from this protocol.')
        return data

class FacilityForm(forms.ModelForm):
    class Meta:
        model = Facility
        fields = ['name', 'code', 'city', 'active']
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and Patient.objects.filter(facility=self.instance).exists(): self.fields['code'].disabled = True
    def clean_code(self): return self.cleaned_data['code'].upper()

class UserForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', required=False, strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'placeholder': 'At least 12 characters'}))
    password2 = forms.CharField(label='Confirm password', required=False, strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'placeholder': 'Type the password again'}))

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role', 'facility', 'assigned_facilities', 'is_active']
        widgets = {'assigned_facilities': forms.CheckboxSelectMultiple()}
        labels = {
            'facility': 'Facility',
            'assigned_facilities': 'Facilities this reviewer covers',
            'is_active': 'Account is active',
        }
        help_texts = {
            'facility': 'The facility where this staff member registers patients and submits screenings.',
            'assigned_facilities': 'The reviewer will only see screenings from the facilities ticked here.',
            'is_active': 'Untick to block sign-in without deleting the account or its records.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['facility'].empty_label = 'Select a facility'
        self.creating = self.instance.pk is None
        if self.creating:
            self.fields['first_name'].required = True
            self.fields['last_name'].required = True
            self.fields['password1'].required = True
            self.fields['password2'].required = True
        else:
            self.fields['password1'].label = 'New password'
            self.fields['password1'].help_text = 'Leave both password fields blank to keep the current password.'
            self.fields['password1'].widget.attrs['placeholder'] = 'Leave blank to keep current password'
            self.fields['password2'].label = 'Confirm new password'
            self.fields['password2'].widget.attrs['placeholder'] = ''

    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk).exists(): raise forms.ValidationError('This email is already in use.')
        return value

    def clean(self):
        data = super().clean()
        role = data.get('role')
        if role == 'staff':
            if not data.get('facility') or not data['facility'].active: self.add_error('facility', 'Choose an active facility for staff.')
            data['assigned_facilities'] = Facility.objects.none()
        else:
            data['facility'] = None
        if role == 'reviewer':
            if not data.get('assigned_facilities'): self.add_error('assigned_facilities', 'Choose at least one facility for this reviewer.')
        elif role == 'admin':
            data['assigned_facilities'] = Facility.objects.none()
        p1, p2 = data.get('password1'), data.get('password2')
        if p1 or p2:
            if p1 != p2:
                self.add_error('password2', 'The two passwords do not match.')
            else:
                candidate = self.instance if not self.creating else User(email=data.get('email', ''), first_name=data.get('first_name', ''), last_name=data.get('last_name', ''))
                try: password_validation.validate_password(p1, candidate)
                except forms.ValidationError as exc: self.add_error('password1', exc)
        return data

class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name']


class ContactForm(forms.ModelForm):
    # Honeypot: invisible to people, tempting to bots. Odd name so browsers don't autofill it.
    rt_hp_check = forms.CharField(required=False, widget=forms.TextInput(attrs={'tabindex': '-1', 'autocomplete': 'off', 'data-lpignore': 'true', 'data-1p-ignore': 'true', 'data-form-type': 'other'}))

    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'phone', 'kind', 'message']
        labels = {'name': 'Full name', 'email': 'Email address', 'phone': 'Phone / WhatsApp (optional)', 'kind': 'I am a', 'message': 'How can we help?'}
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Your full name', 'autocomplete': 'name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'you@example.com', 'autocomplete': 'email'}),
            'phone': forms.TextInput(attrs={'placeholder': '+234 …', 'autocomplete': 'tel'}),
            'message': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Tell us about your pharmacy, community or partnership idea…'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kind'].choices = [('', 'Select one')] + list(ContactMessage.Kind.choices)
        self.fields['kind'].initial = ''

    def clean_message(self):
        value = self.cleaned_data['message'].strip()
        if len(value) < 10: raise forms.ValidationError('Please write a little more so we can help.')
        return value
