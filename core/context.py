from django.conf import settings
from .models import Notification, ContactMessage


def shell(request):
    user = request.user
    signed_in = user.is_authenticated
    return {
        'demo_mode': settings.DEMO_MODE,
        'unread_count': Notification.objects.filter(user=user, read=False).count() if signed_in else 0,
        'unread_messages': ContactMessage.objects.filter(read=False, is_spam=False).count() if signed_in and user.role == 'admin' else 0,
    }
