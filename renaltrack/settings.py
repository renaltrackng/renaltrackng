import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
# A small local .env reader; process environment always wins.
if (BASE_DIR / '.env').exists():
    for line in (BASE_DIR / '.env').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
DEBUG = os.getenv('DJANGO_DEBUG', '1') == '1'
DEMO_MODE = os.getenv('DEMO_MODE', '1') == '1'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('DJANGO_SECRET_KEY is required in production.')
    from django.core.management.utils import get_random_secret_key
    secret_file = BASE_DIR / 'local-secret.key'
    if not secret_file.exists():
        secret_file.write_text(get_random_secret_key())
    SECRET_KEY = secret_file.read_text()
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
railway_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', '').strip()
if railway_domain:
    ALLOWED_HOSTS += [railway_domain, 'healthcheck.railway.app']
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()]
if railway_domain:
    CSRF_TRUSTED_ORIGINS.append(f'https://{railway_domain}')
if os.getenv('DJANGO_TRUST_PROXY', '0') == '1':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'core']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'core.middleware.AccessMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'renaltrack.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages', 'core.context.shell']}}]
WSGI_APPLICATION = 'renaltrack.wsgi.application'
if os.getenv('DB_ENGINE', 'sqlite') == 'mysql':
    import pymysql
    pymysql.install_as_MySQLdb()
    DATABASES = {'default': {'ENGINE': 'django.db.backends.mysql', 'NAME': os.getenv('MYSQL_DATABASE', 'renaltrack'), 'USER': os.getenv('MYSQL_USER', 'renaltrack'), 'PASSWORD': os.getenv('MYSQL_PASSWORD', ''), 'HOST': os.getenv('MYSQL_HOST', '127.0.0.1'), 'PORT': os.getenv('MYSQL_PORT', '3306'), 'OPTIONS': {'charset': 'utf8mb4', 'init_command': "SET sql_mode='STRICT_TRANS_TABLES'"}}}
else:
    if not DEMO_MODE:
        raise ImproperlyConfigured('Live mode requires MySQL.')
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'demo.sqlite3', 'OPTIONS': {'timeout': 20}}}
AUTH_USER_MODEL = 'core.User'
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}, {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}}, {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}, {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'en-gb'
TIME_ZONE = 'Africa/Lagos'
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'}}
MEDIA_ROOT = Path(os.getenv('DJANGO_MEDIA_ROOT', str(BASE_DIR / 'private_media')))
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
SESSION_COOKIE_AGE = 1800
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG and os.getenv('DJANGO_SECURE_SSL_REDIRECT', '1') == '1'
SECURE_REDIRECT_EXEMPT = [r'^healthz/$']
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'RenalTrack <noreply@localhost>')
PASSWORD_RESET_TIMEOUT = 3600
# Real-patient enablement requires a separately reviewed production readiness change.
if not DEMO_MODE:
    raise ImproperlyConfigured('Real-patient mode is locked pending clinical, governance and MFA approval. Use synthetic data only.')
