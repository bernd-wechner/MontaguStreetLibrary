# Generated by Django 4.1.4 on 2022-12-17 12:53

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Doors', '0003_alter_opening_visit_uptime'),
    ]

    operations = [
        migrations.AddField(
            model_name='uptime',
            name='door',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.PROTECT, related_name='uptimes', to='Doors.door'),
            preserve_default=False,
        ),
    ]