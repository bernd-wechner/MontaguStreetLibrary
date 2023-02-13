'''
Fetch logs from the Tuya IoT

    https://developer.tuya.com/en/docs/iot/membership-service?id=K9m8k45jwvg9j

Pricing is cryptic. At top they say:

    Trial Edition (1 month)
    Note: Only for individual developers or use in the debugging phase, and commercial use is prohibited
        50 devices
        Trial resource pack: about 26 thousand API calls
        When developers exceed the limit, Tuya will stop the service.

Suggesting the trial last 1 month, and that there's a fixed limit of about 26000 API calls.

Later under "Basic resource pack" they say:

    Trial
    3.71 USD/million API calls (for Plan 1 which applies us in Australia)
    About 26 thousand API calls

And on another page:

    https://eu.iot.tuya.com/cloud/products/detail?abilityId=1442730014117204014&id=p1668767995023hmaagk&abilityAuth=0&tab=1

They write:

    Resource Pack Name                   Usage/Resource Pack Quota    Quota Refresh    Effective Date         Expiration Date        Status
    Cloud Develop Base Resource Trial    0.002176 / 0.2 USD           Monthly          2022-11-18 21:42:25    2022-12-18 21:42:25    In service

Which at 3.71 USD/million API calls translates to 53,908 API calls per month or 1739 API calls/day.

So shoudl ve very safe for a daily download of, well as many as 1700 door sensors ;-).

My Devices are here:

    https://eu.iot.tuya.com/cloud/basic?id=p1668767995023hmaagk&toptab=related&deviceTab=all
'''
import tinytuya, sys

from django.conf import settings
from django.core.management.base import BaseCommand

from Doors.models import Door, Event, Opening, Visit, Uptime


class Command(BaseCommand):
    help = 'Fetches the Tuya Logs and updates the database accordingly'

    def handle(self, *args, **kwargs):
        cloud = tinytuya.Cloud(apiRegion=settings.TUYA_REGION,
                               apiKey=settings.TUYA_KEY,
                               apiSecret=settings.TUYA_SECRET,
                               apiDeviceID=settings.TUYA_DEVICE_ID)

        min_tuya_timestamp = 1
        max_tuya_timestamp = sys.maxsize
        verbosity = kwargs['verbosity']

        for door in Door.objects.all():
            last = Event.last(door=door)
            start = last.timestamp - 1  if last else  min_tuya_timestamp
            log = cloud.getdevicelog(door.tuya_device_id, start=start, end=max_tuya_timestamp)

            # Just some sniffers while debugging
            if 'result' in log:
                row_key = log['result'].get('current_row_key', None)
                has_next = log['result'].get('has_next', False)
                next_row_key = log['result'].get('next_row_key', None)
                fetches = log.get('fetches', 1)
                events = log['result'].get('logs', [])
            else:
                print("No result in downloaded log.")
                print(f"log: {log}")

            if verbosity > 0:
                print(f"Door {door.id}: Fetched {len(events)} events in {fetches} fetches.")

            Event.save_logs(door, log, verbosity=verbosity)
            Opening.update_from_events(door, verbosity=verbosity)
            Uptime.update_from_events(door, verbosity=verbosity)

        # A visit spans all doors (while an Opening concerns only one door)
        Visit.update_from_openings(verbosity=verbosity)

        if verbosity > 0:
            print(f"Done!")

