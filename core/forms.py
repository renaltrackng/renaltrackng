import io
import warnings
from PIL import Image, ImageOps
from django import forms
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.core.files.base import ContentFile
from django.utils import timezone
from .models import User, Facility, Patient, Protocol

ANSWERS = [('', 'Select an answer'), ('yes', 'Yes'), ('no', 'No'), ('unknown', 'Unknown'), ('not_provided', 'Not provided')]
FACTORS = {'diabetes': 'Diabetes', 'hypertension': 'Hypertension', 'kidney_disease': 'Known kidney disease', 'family_history': 'Family history of kidney disease'}

class LoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email address', widget=forms.EmailInput(attrs={'autocomplete': 'username', 'placeholder': 'you@facility.com'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete': 'current-password', 'placeholder': 'Enter your password'}))

class StartForm(forms.Form):
    consent = forms.BooleanField(label='I have explained this demo notice and recorded the participant’s agreement.')
    identity_verified = forms.BooleanField(required=False, label='I have verified this returning participant’s identity.')
    name = forms.CharField(max_length=120, required=False, label='Demo participant name or identifier')
    def __init__(self, *args, patient=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.patient = patient
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
    product = forms.CharField(max_length=140, initial='Demo strip — not for clinical use')
    lot = forms.CharField(max_length=80, label='Lot / batch number')
    expiry = forms.DateField(label='Expiry date', widget=forms.DateInput(attrs={'type': 'date'}))
    captured_at = forms.DateTimeField(label='Photo captured at (Lagos time)', widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}))
    image = forms.ImageField(label='Strip photograph', widget=forms.FileInput(attrs={'accept': 'image/jpeg,image/png', 'capture': 'environment'}))
    note = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={'rows': 3}), label='Capture / repeat notes')
    confirmed = forms.BooleanField(label='I checked the image and the information above before submitting.')
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
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role', 'facility', 'assigned_facilities', 'can_review', 'is_active']
        widgets = {'assigned_facilities': forms.CheckboxSelectMultiple()}
    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk).exists(): raise forms.ValidationError('This email is already in use.')
        return value
    def clean(self):
        data = super().clean()
        if data.get('role') == 'staff':
            if not data.get('facility') or not data['facility'].active: self.add_error('facility', 'Choose an active facility for staff.')
            if data.get('assigned_facilities'): self.add_error('assigned_facilities', 'Staff cannot have reviewer assignments.')
        elif data.get('role'): data['facility'] = None
        if data.get('role') != 'admin': data['can_review'] = False
        return data

class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name']
