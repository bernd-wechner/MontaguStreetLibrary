import tinytuya, sys

from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

from Doors.models import Door, Event, Opening, Visit, EVENT_IDS, EVENT_SOURCES, DOOR_STATES, VISIT_SEPARATION


class Command(BaseCommand):
    help = 'Fetches the Tuya Logs and updates the database accordingly'

    def handle(self, *args, **kwargs):
        cloud = tinytuya.Cloud(apiRegion=settings.TUYA_REGION,
                               apiKey=settings.TUYA_KEY,
                               apiSecret=settings.TUYA_SECRET,
                               apiDeviceID=settings.TUYA_DEVICE_ID)

        min_tuya_timestamp = 1
        max_tuya_timestamp = sys.maxsize

        for door in Door.objects.all():
            log = cloud.getdevicelog(door.tuya_device_id, start=min_tuya_timestamp, end=max_tuya_timestamp)

            Event.save_logs(door, log)
            Opening.update_from_events(door)

        # A visit spans all doors (while an Opening concerns only one door)
        Visit.update_from_openings()

