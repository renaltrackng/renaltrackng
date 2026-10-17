"""Railway entry point: persistent uploads, migrations, static assets, WSGI."""
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
os.chdir(root)
sys.path.insert(0, str(root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'renaltrack.settings')
os.environ.setdefault('DJANGO_DEBUG', '0')

if os.getenv('DB_ENGINE') != 'mysql':
    raise RuntimeError('Railway deployment requires DB_ENGINE=mysql and database connection variables.')
mount = os.getenv('RAILWAY_VOLUME_MOUNT_PATH')
if not mount or not Path(mount).is_dir():
    raise RuntimeError('Attach a Railway volume at /data before deploying; private photos must persist.')
media = Path(os.environ.setdefault('DJANGO_MEDIA_ROOT', str(Path(mount) / 'private_media'))).resolve()
if not media.is_relative_to(Path(mount).resolve()):
    raise RuntimeError('DJANGO_MEDIA_ROOT must be inside the mounted Railway volume.')
media.mkdir(parents=True, exist_ok=True)

subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'], check=True)
subprocess.run([sys.executable, 'manage.py', 'collectstatic', '--noinput'], check=True)

from renaltrack.wsgi import application
from waitress import serve

options = {'host': '0.0.0.0', 'port': int(os.getenv('PORT', '8080')), 'threads': 4, 'max_request_body_size': 12 * 1024 * 1024}
if os.getenv('DJANGO_TRUST_PROXY') == '1':
    options.update(trusted_proxy='*', trusted_proxy_headers={'x-forwarded-proto'})
serve(application, **options)
