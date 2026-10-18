"""Preserve historical protocol versions, observations, notes and strip metadata.

Keep this migration in the dependency chain, but never translate old strip
categories into measurements or rewrite submitted records. New product scales
belong in a new explicitly configured protocol version. If the earlier unsafe
version already ran, this migration cannot reconstruct the original values;
recovery must use an authorised backup/audit review, not another guessed mapping.
"""
from django.db import migrations

def forwards(apps, schema_editor):
    # Deliberate no-op: retaining the migration name keeps later dependencies valid.
    pass


class Migration(migrations.Migration):
    dependencies = [('core', '0002_contactmessage')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
