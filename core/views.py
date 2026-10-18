import hashlib
import uuid
from datetime import timedelta
from functools import wraps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Count, Max, Case, When, Value, IntegerField, F
from django.http import FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.views.decorators.http import require_POST
from .models import User, Facility, Patient, Protocol, Screening, Attempt, Notification, Audit, LoginThrottle
from .forms import LoginForm, StartForm, RiskForm, UploadForm, ReviewForm, FacilityForm, UserForm, ProfileForm
from .access import screenings_for, patients_for, facilities_for
from . import dashboard as dashboard_ui
from .services import start_screening, submit_attempt, claim_review, save_review, reviewer_allowed, audit

def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if request.user.role not in roles: raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator

def login_view(request):
    if request.user.is_authenticated: return redirect('dashboard')
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST':
        # Both account and source limits are persistent across worker processes.
        identifiers = ['account:' + request.POST.get('username', '').strip().lower(), 'ip:' + request.META.get('REMOTE_ADDR', '')]
        keys = [hashlib.sha256(x.encode()).hexdigest() for x in identifiers]
        now = timezone.now()
        throttles = []
        for key in keys:
            throttle, _ = LoginThrottle.objects.get_or_create(key=key, defaults={'window_start': now})
            if now - throttle.window_start > timedelta(minutes=15):
                throttle.failures, throttle.window_start = 0, now
                throttle.save()
            throttles.append(throttle)
        if any(x.failures >= 10 for x in throttles):
            form.add_error(None, 'Too many attempts. Please wait 15 minutes before trying again.')
        elif form.is_valid():
            user = form.get_user()
            if user.role == 'staff' and (not user.facility_id or not user.facility.active):
                form.add_error(None, 'Unable to sign in. Contact your administrator.')
            else:
                login(request, user)
                LoginThrottle.objects.filter(key=keys[0]).update(failures=0)
                audit(user, 'Signed in', user.pk)
                return redirect('dashboard')
        else:
            from django.db.models import F
            LoginThrottle.objects.filter(key__in=keys).update(failures=F('failures') + 1)
    return render(request, 'registration/login.html', {'form': form})

@require_POST
@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def dashboard(request):
    qs = screenings_for(request.user)
    counts = dict(qs.values('status').annotate(n=Count('id')).values_list('status', 'n'))
    total = qs.exclude(status='draft').count()
    reviewed = counts.get('reviewed', 0)
    today = timezone.localdate()
    submitted = qs.exclude(status='draft')
    if request.user.role == 'reviewer':
        attention = submitted.filter(status='pending').order_by('submitted_at')[:4]
    elif request.user.role == 'admin':
        attention = qs.filter(status__in=['pending', 'repeat', 'unreadable', 'draft']).order_by('-created_at')[:5]
    else:
        attention = qs.filter(status__in=['repeat', 'unreadable', 'draft']).order_by('-created_at')[:4]
    return render(request, 'dashboard.html', {
        'section': 'dashboard', 'counts': counts, 'total': total, 'reviewed': reviewed,
        'completion': round(reviewed / total * 100) if total else 0,
        'patients_count': patients_for(request.user).count(),
        'facilities_count': facilities_for(request.user).filter(active=True).count(),
        'recent': submitted.order_by('-submitted_at')[:6], 'today': today,
        'pending': counts.get('pending', 0), 'repeats': counts.get('repeat', 0),
        'drafts': counts.get('draft', 0), 'unreadable': counts.get('unreadable', 0),
        'greeting': dashboard_ui.greeting(), 'chart': dashboard_ui.activity_chart(submitted),
        'donut': dashboard_ui.outcome_donut(counts), 'calendar': dashboard_ui.month_calendar(submitted),
        'attention': attention,
    })

@login_required
def screening_list(request):
    qs = screenings_for(request.user)
    status = request.GET.get('status', '')
    if request.user.role == 'reviewer': qs = qs.exclude(status='draft')
    if status: qs = qs.filter(status=status)
    query = request.GET.get('q', '').strip()
    if query: qs = qs.filter(Q(patient__public_id__icontains=query) | Q(patient__name__icontains=query))
    facility = request.GET.get('facility')
    if facility and facility.isdigit(): qs = qs.filter(facility_id=facility)
    if request.GET.get('date'):
        from django.utils.dateparse import parse_date
        try: date = parse_date(request.GET['date'])
        except ValueError: date = None
        if date: qs = qs.filter(submitted_at__date=date)
    if status == 'pending':
        qs = qs.order_by('submitted_at', 'created_at')
    elif request.user.role in ('reviewer', 'admin') and not status:
        # Review queue: anything awaiting review comes first (longest-waiting at the top), then the rest newest first.
        waiting = Case(When(status='pending', then=Value(0)), default=Value(1), output_field=IntegerField())
        oldest_first = Case(When(status='pending', then=F('submitted_at')), default=None)
        qs = qs.order_by(waiting, oldest_first.asc(nulls_last=True), F('submitted_at').desc(nulls_last=True), '-created_at')
    else:
        qs = qs.order_by('-created_at')
    return render(request, 'screenings/list.html', {'section': 'screenings', 'page': Paginator(qs, 15).get_page(request.GET.get('page')), 'statuses': Screening.Status.choices, 'facilities': facilities_for(request.user), 'query': query, 'selected_status': status})

@login_required
def patient_list(request):
    qs = patients_for(request.user)
    query = request.GET.get('q', '').strip()
    if query: qs = qs.filter(Q(public_id__icontains=query) | Q(name__icontains=query))
    return render(request, 'patients/list.html', {'section': 'patients', 'page': Paginator(qs, 15).get_page(request.GET.get('page')), 'query': query})

@login_required
def patient_detail(request, pk):
    patient = get_object_or_404(patients_for(request.user), pk=pk)
    return render(request, 'patients/detail.html', {'section': 'patients', 'patient': patient, 'screenings': screenings_for(request.user).filter(patient=patient).exclude(status='draft')})

@role_required('staff', 'admin')
def screening_start(request):
    protocol = Protocol.objects.filter(active=True, is_demo=settings.DEMO_MODE).order_by('-created_at').first()
    if not protocol:
        messages.error(request, 'No screening protocol is configured. Contact your administrator.')
        return redirect('dashboard')
    patient = None
    if request.GET.get('patient'): patient = get_object_or_404(patients_for(request.user), pk=request.GET['patient'])
    registering = request.method == 'POST' or request.GET.get('new') == '1'
    if patient is None and not registering:
        # Step 0: find the patient first; registration is offered only if they're not on record.
        query = request.GET.get('q', '').strip()
        found = patients_for(request.user).annotate(last_screened=Max('screenings__submitted_at'), screening_count=Count('screenings'))
        if query:
            found = found.filter(Q(public_id__icontains=query) | Q(name__icontains=query)).order_by('name')
        else:
            found = found.order_by('-created_at')
        return render(request, 'screenings/find_patient.html', {'section': 'screenings', 'query': query, 'results': found[:12]})
    form = StartForm(request.POST or None, patient=patient, user=request.user, initial={'name': request.GET.get('name', '')})
    if request.method == 'POST' and form.is_valid():
        screening = start_screening(request.user, protocol, form.cleaned_data.get('name'), patient, facility=form.cleaned_data.get('facility'))
        messages.success(request, 'Consent recorded. Your draft is saved.')
        return redirect('screening_risks', pk=screening.pk)
    return render(request, 'screenings/start.html', {'section': 'screenings', 'form': form, 'protocol': protocol, 'patient': patient})

@role_required('staff', 'admin')
def screening_risks(request, pk):
    screening = get_object_or_404(screenings_for(request.user), pk=pk, status='draft')
    form = RiskForm(request.POST or None, initial=screening.risk_factors)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            screening = Screening.objects.select_for_update().get(pk=screening.pk)
            if screening.status != 'draft': raise PermissionDenied
            screening.risk_factors = form.cleaned_data
            screening.revision += 1
            screening.save(update_fields=['risk_factors', 'revision'])
            audit(request.user, 'Draft risk factors saved', screening.pk)
        messages.success(request, 'Risk factors saved.')
        return redirect('screening_upload', pk=screening.pk)
    return render(request, 'screenings/risks.html', {'section': 'screenings', 'screening': screening, 'form': form})

@role_required('staff', 'admin')
def screening_upload(request, pk):
    screening = get_object_or_404(screenings_for(request.user), pk=pk)
    if request.method != 'POST' and screening.status not in ('draft', 'repeat'): return redirect('screening_detail', pk=pk)
    if not screening.risk_factors: return redirect('screening_risks', pk=pk)
    form = UploadForm(request.POST or None, request.FILES or None, initial={'revision': screening.revision, 'request_key': uuid.uuid4(), 'captured_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M')})
    if request.method == 'POST' and form.is_valid():
        try:
            submit_attempt(request.user, pk, form.cleaned_data)
            messages.success(request, 'Screening submitted. You will be notified as soon as the review is complete.')
            return redirect('screening_detail', pk=pk)
        except ValidationError as exc: form.add_error(None, exc)
        except OSError: form.add_error(None, 'The image could not be saved. Select the file again and retry.')
    return render(request, 'screenings/upload.html', {'section': 'screenings', 'screening': screening, 'form': form})

@login_required
def screening_detail(request, pk):
    screening = get_object_or_404(screenings_for(request.user), pk=pk)
    if request.user.role == 'reviewer' and screening.status == 'draft': raise PermissionDenied
    can_review = reviewer_allowed(request.user, screening) and screening.status in ('pending', 'reviewed')
    review_form = ReviewForm(screening=screening, initial={'revision': screening.revision}) if can_review else None
    if request.method == 'POST':
        if not can_review: raise PermissionDenied
        if request.POST.get('action') in ('claim', 'release'):
            try:
                claim_review(request.user, pk, release=request.POST['action'] == 'release')
                messages.success(request, 'Review claim updated.')
            except ValidationError as exc: messages.error(request, '; '.join(exc.messages))
            return redirect('screening_detail', pk=pk)
        review_form = ReviewForm(request.POST, screening=screening)
        if review_form.is_valid():
            try:
                save_review(request.user, pk, review_form.cleaned_data)
                messages.success(request, 'Review saved. The submitting facility can now see the update.')
                return redirect('screening_detail', pk=pk)
            except ValidationError as exc: review_form.add_error(None, exc)
    Notification.objects.filter(user=request.user, screening=screening, read=False).update(read=True)
    factors = [(k.replace('_', ' ').title(), v.replace('_', ' ').title()) for k, v in screening.risk_factors.items()]
    return render(request, 'screenings/detail.html', {'section': 'screenings', 'screening': screening, 'attempts': screening.attempts.all(), 'reviews': screening.reviews.select_related('reviewer'), 'latest_review': screening.latest_review, 'review_form': review_form, 'factors': factors, 'claim_active': screening.claim_expires and screening.claim_expires > timezone.now()})

@login_required
def protected_image(request, pk):
    attempt = get_object_or_404(Attempt.objects.select_related('screening'), pk=pk, screening__in=screenings_for(request.user))
    if request.user.role == 'reviewer' and attempt.screening.status == 'draft': raise PermissionDenied
    try: response = FileResponse(attempt.image.open('rb'), content_type='image/png')
    except FileNotFoundError:
        from django.http import Http404
        raise Http404
    response['Cache-Control'] = 'no-store, private'
    return response

@login_required
def notifications(request):
    qs = Notification.objects.filter(user=request.user, screening__in=screenings_for(request.user))
    return render(request, 'notifications.html', {'section': 'notifications', 'page': Paginator(qs, 20).get_page(request.GET.get('page'))})

@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Profile updated.')
        return redirect('profile')
    return render(request, 'generic_form.html', {'section': 'settings', 'title': 'Your profile', 'subtitle': 'Keep your account details up to date.', 'form': form, 'button': 'Save changes'})

@login_required
def password_change(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, 'Password changed.')
        return redirect('profile')
    return render(request, 'generic_form.html', {'section': 'settings', 'title': 'Change password', 'subtitle': 'Use a unique password with at least 12 characters.', 'form': form, 'button': 'Update password'})

@role_required('admin')
def facilities(request):
    return render(request, 'management/facilities.html', {'section': 'facilities', 'facilities': Facility.objects.annotate(staff_count=Count('staff', filter=Q(staff__is_active=True), distinct=True), patient_count=Count('patient', distinct=True))})

@role_required('admin')
def facility_edit(request, pk=None):
    facility = get_object_or_404(Facility, pk=pk) if pk else None
    form = FacilityForm(request.POST or None, instance=facility)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        audit(request.user, 'Facility updated' if facility else 'Facility created', obj.pk)
        messages.success(request, 'Facility saved.')
        return redirect('facilities')
    return render(request, 'generic_form.html', {'section': 'facilities', 'title': 'Edit facility' if facility else 'Add facility', 'subtitle': 'Facility codes become permanent after the first patient is registered.', 'form': form, 'button': 'Save facility'})

@role_required('admin')
def users(request):
    return render(request, 'management/users.html', {'section': 'users', 'users': User.objects.filter(is_active=True).select_related('facility').order_by('role', 'first_name')})

@role_required('admin')
def user_edit(request, pk=None):
    obj = get_object_or_404(User, pk=pk) if pk else None
    form = UserForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        if obj and obj.pk == request.user.pk and (not form.cleaned_data['is_active'] or form.cleaned_data['role'] != 'admin'):
            form.add_error(None, 'You cannot disable or remove your own administrator access.')
        else:
            with transaction.atomic():
                user = form.save(commit=False)
                if obj is None:
                    user.username = uuid.uuid4().hex
                password = form.cleaned_data.get('password1')
                if password:
                    user.set_password(password)
                user.save()
                form.save_m2m()
                audit(request.user, 'Account updated' if obj else 'Account created', user.pk)
                if password and obj is not None:
                    audit(request.user, 'Password set by administrator', user.pk)
            if obj is None:
                messages.success(request, f'Account created for {user.display_name}. They can now sign in with {user.email} and the password you set.')
            else:
                messages.success(request, 'Account updated.' + (' The new password is active now.' if password else ''))
            return redirect('users')
    return render(request, 'generic_form.html', {'section': 'users', 'title': 'Edit account' if obj else 'Add team member', 'subtitle': 'Each person gets their own login. Choose a role to see the settings that apply to it.', 'form': form, 'button': 'Create account' if obj is None else 'Save changes', 'role_form': True})

@require_POST
@role_required('admin')
def user_invite(request, pk):
    user = get_object_or_404(User, pk=pk, is_active=True)
    token = default_token_generator.make_token(user)
    path = reverse('activate', kwargs={'uidb64': urlsafe_base64_encode(force_bytes(user.pk)), 'token': token})
    url = request.build_absolute_uri(path)
    if settings.DEBUG:
        # Without outbound mail (debug), hand the link to the signed-in administrator.
        # Never put access tokens in logs or audit events.
        request.session['demo_invite'] = {'url': url, 'email': user.email}
    else:
        try: user.email_user('Your RenalTrack account', f'Set your password using this link within one hour:\n{url}\nIf you did not expect this invitation, contact your administrator.')
        except Exception:
            messages.error(request, 'The access email could not be sent. Check mail configuration and try again.')
            return redirect('users')
    audit(request.user, 'Access link issued', user.pk)
    messages.success(request, f'Access link ready for {user.display_name}. Share it with them securely.' if settings.DEBUG else f'Access email sent to {user.email}.')
    return redirect('users')

def activate(request, uidb64, token):
    from django.contrib.auth.forms import SetPasswordForm
    try: user = User.objects.get(pk=urlsafe_base64_decode(uidb64).decode(), is_active=True)
    except (ValueError, TypeError, OverflowError, User.DoesNotExist): user = None
    valid = user and default_token_generator.check_token(user, token)
    form = SetPasswordForm(user, request.POST or None) if valid else None
    if form and request.method == 'POST' and form.is_valid():
        form.save()
        audit(user, 'Password set through access link', user.pk)
        messages.success(request, 'Password set. You can now sign in.')
        return redirect('login')
    return render(request, 'registration/activate.html', {'form': form, 'valid': valid})

@role_required('admin')
def audit_log(request):
    return render(request, 'management/audit.html', {'section': 'audit', 'page': Paginator(Audit.objects.select_related('actor'), 30).get_page(request.GET.get('page'))})

@role_required('admin')
def protocols(request):
    return render(request, 'management/protocols.html', {'section': 'protocols', 'protocols': Protocol.objects.order_by('-created_at')})
