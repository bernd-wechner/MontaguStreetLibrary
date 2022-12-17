import os
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.migrations.recorder import MigrationRecorder

data_migration = '''from django.db import migrations

# The doors 1-4 on the Montagu Street Library have these IDs and contents (behind the doors):
doors = {'bf5e70c82cd099e751hy2l': "Non-fiction, Puzzles",
         'bfa3645b8c194e83fb5x58': "Fiction, Toys",
         'bf383540df75cc0be7637b': "Fiction, Childrens Books",
         'bf3f6fd375aee65936z1jb': "Fiction, Family, Games"}


def add_doors(apps, schema_editor):
    Door = apps.get_model('Doors', 'Door')  # A lot of Doors ;-)
    for device_id, contents in doors.items():
         door = Door(tuya_device_id=device_id, contents=contents)
         door.save()


class Migration(migrations.Migration):

    dependencies = [
        ('Doors', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_doors),
    ]
'''


class Command(BaseCommand):
    help = 'Displays current time'

    def handle(self, *args, **kwargs):
        # Prevent accidental run until I fix it to backup events before hand and only aftern  an Are you sure warning
        return

        # Forst reset the migrations, using https://pypi.org/project/django-reset-migrations/
        call_command('reset_migrations', 'Doors')

        # That creates a single migration 0001_initial.py
        # Then we add out data to the database with a second migration
        #    0002_Montagu_Street_Library_Doors.py
        # with the code in data_migration above
        script_dir = os.path.realpath(__file__)
        filename = script_dir[:script_dir.find("management")] + f"/migrations/0002_Montagu_Street_Library_Doors.py"
        with open(filename, "w") as file:
            file.write(data_migration)

        # Undo all migrations (this removes the apps tables)
        call_command('migrate', 'Doors', 'zero')

        # It fails to remove the migration records though
        # So we delete them in order to be able to reapply the
        # migrations.
        migrations = MigrationRecorder.Migration.objects.filter(app="Doors")
        for migration in migrations:
            migration.delete()

        # Then apply the newly reset migrations
        call_command('migrate', 'Doors')

        # The Doors app should now have a nice neat 2 migrations again.
