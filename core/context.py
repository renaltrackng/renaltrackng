from django.conf import settings
from .models import Notification
def shell(request):
    return {'demo_mode': settings.DEMO_MODE, 'unread_count': Notification.objects.filter(user=request.user, read=False).count() if request.user.is_authenticated else 0}
