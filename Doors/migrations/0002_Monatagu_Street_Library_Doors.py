from django.db import migrations

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
