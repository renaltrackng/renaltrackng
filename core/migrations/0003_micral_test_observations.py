"""Correct the urine albumin observation options to the Micral-Test colour chart
(Neg., 20 mg/L, 50 mg/L, 100 mg/L) and convert existing records."""
from django.db import migrations

OLD = ['Negative', 'Trace', 'Positive (1+)', 'Positive (2+)', 'Positive (3+ or higher)']
NEW = ['Negative (Neg.)', '20 mg/L', '50 mg/L', '100 mg/L']
MAP = {'Negative': 'Negative (Neg.)', 'Trace': '20 mg/L', 'Positive (1+)': '50 mg/L',
       'Positive (2+)': '100 mg/L', 'Positive (3+ or higher)': '100 mg/L'}
INSTRUCTIONS = ('Collect a fresh urine sample in a clean, dry container. Dip the Micral-Test strip so the urine level '
                'sits between the two black bars and hold it there for about 5 seconds. Remove the strip, lay it flat, '
                'and after 1 minute compare the test pad with the colour chart on the vial. Photograph the strip beside '
                'the chart while the colour is still within the reading time.')
SAMPLE_NOTES = {
    'Clear photo, read within the time window. The albumin pad shows a faint colour change consistent with trace. Please advise the patient to return in 3 months.':
        'Clear photo, read at 1 minute. The test pad matches the 20 mg/L block on the chart. Please advise the patient to return in 3 months for a repeat screening.',
    'Good-quality photo. No colour change on the albumin pad.':
        'Good-quality photo. The test pad matches the negative block — no colour change.',
    'Albumin pad matches 1+ on the chart. Patient reports hypertension — please refer for uACR and eGFR.':
        'Test pad matches 50 mg/L on the chart. Patient reports hypertension — please refer for uACR and eGFR.',
}


def forwards(apps, schema_editor):
    Protocol = apps.get_model('core', 'Protocol')
    Review = apps.get_model('core', 'Review')
    Attempt = apps.get_model('core', 'Attempt')
    for p in Protocol.objects.all():
        if list(p.observation_options) == OLD:
            p.observation_options = NEW
            p.instructions = INSTRUCTIONS
            if p.name == 'Urine albumin screening':
                p.name = 'Urine albumin screening (Micral-Test)'
            p.save()
    for r in Review.objects.filter(observation__in=list(MAP)):
        r.observation = MAP[r.observation]
        r.note = SAMPLE_NOTES.get(r.note, r.note)
        r.save(update_fields=['observation', 'note'])
    Attempt.objects.filter(product='Urine albumin test strip', lot='UA24117').update(product='Micral-Test (urine albumin) strip', lot='MT24117')


class Migration(migrations.Migration):
    dependencies = [('core', '0002_contactmessage')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
