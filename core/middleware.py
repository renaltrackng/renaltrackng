from django.contrib.auth import logout
from django.shortcuts import redirect

class AccessMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        if request.user.is_authenticated and request.user.role == 'staff':
            if not request.user.facility_id or not request.user.facility.active:
                logout(request)
                return redirect('login')
        response = self.get_response(request)
        if request.user.is_authenticated:
            response['Cache-Control'] = 'no-store, private'
        response['Referrer-Policy'] = 'same-origin'
        return response
