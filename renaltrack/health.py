"""Deployment health endpoint, kept separate from application workflow views."""
from django.db import connection, DatabaseError
from django.http import JsonResponse


def healthcheck(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except DatabaseError:
        response = JsonResponse({'status': 'unavailable'}, status=503)
    else:
        response = JsonResponse({'status': 'ok'})
    response['Cache-Control'] = 'no-store'
    return response
