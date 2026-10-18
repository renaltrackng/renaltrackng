from django.core.management.base import BaseCommand
from core.models import Screening, Notification
from core.services import reviewers_for


class Command(BaseCommand):
    help = 'Create "awaiting review" notifications for pending screenings that have none (one-off backfill).'

    def handle(self, *args, **options):
        created = 0
        for s in Screening.objects.filter(status='pending').select_related('facility', 'submitted_by'):
            text = 'Repeat attempt awaiting review' if s.attempts.count() > 1 else 'New screening awaiting review'
            for user in reviewers_for(s.facility):
                if user.pk == s.submitted_by_id:
                    continue
                if not Notification.objects.filter(user=user, screening=s, text=text).exists():
                    Notification.objects.create(user=user, screening=s, text=text)
                    created += 1
        self.stdout.write(self.style.SUCCESS(f'{created} notification(s) created.'))
