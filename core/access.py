from .models import Patient, Screening, Facility

def facilities_for(user):
    if user.role == 'admin': return Facility.objects.all()
    if user.role == 'reviewer': return user.assigned_facilities.all()
    return Facility.objects.filter(pk=user.facility_id, active=True)

def screenings_for(user):
    return Screening.objects.filter(facility__in=facilities_for(user)).select_related('patient', 'facility', 'submitted_by', 'protocol')

def patients_for(user):
    return Patient.objects.filter(facility__in=facilities_for(user)).select_related('facility')
