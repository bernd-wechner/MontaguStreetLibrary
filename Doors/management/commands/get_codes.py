import tinytuya, sys

from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

from Doors.models import Door, Event, Opening, Visit, EVENT_IDS, EVENT_SOURCES, DOOR_STATES, VISIT_SEPARATION


class Command(BaseCommand):
    help = 'Gets the Device Code Maps'

    def handle(self, *args, **kwargs):
        cloud = tinytuya.Cloud(apiRegion=settings.TUYA_REGION,
                               apiKey=settings.TUYA_KEY,
                               apiSecret=settings.TUYA_SECRET,
                               apiDeviceID=settings.TUYA_DEVICE_ID)

        for door in Door.objects.all():
            dps = cloud.getdps(door.tuya_device_id)

            headers = ["Door", "DataPoint ID", "Code", "Type", "Values"]
            widths = ["5", "10", "20", "15", "45"]
            header = "\t".join([f"{v:{w}}" for v, w in zip(headers, widths)])
            print(header)
            for status in dps['result']['status']:
                values = (door.id, status['dp_id'], status['code'], status['type'], status['values'])
                row = "\t".join([f"{v:{w}}" for v, w in zip(values, widths)])
                print(row)

