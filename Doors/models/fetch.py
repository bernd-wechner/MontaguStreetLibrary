import tinytuya, sys

from django.conf import settings
from django.db import models

from .door import Door
from .opening import Opening
from .visit import Visit
from .uptime import Uptime

from datetime import datetime


class DataFetch(models.Model):
    '''
    A log of all the Tuya data fetches and methods to do the fetch
    '''
    date_time = models.DateTimeField('Time')

    @classmethod
    def fetch_logs(self, verbosity=1):
        from .event import Event

        cloud = tinytuya.Cloud(apiRegion=settings.TUYA_REGION,
                               apiKey=settings.TUYA_KEY,
                               apiSecret=settings.TUYA_SECRET,
                               apiDeviceID=settings.TUYA_DEVICE_ID)

        min_tuya_timestamp = 1
        max_tuya_timestamp = sys.maxsize

        fetch = DataFetch(date_time=datetime.now())
        fetch.save()

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
                
                if verbosity > 0:
                    print(f"Door {door.id}: Fetched {len(events)} events in {fetches} fetches.")

                Event.save_logs(door, log, fetch, verbosity=verbosity)
                Opening.update_from_events(door, verbosity=verbosity)
                Uptime.update_from_events(door, verbosity=verbosity)
            else:
                print("No result in downloaded log.")
                print(f"log: {log}")

        # A visit spans all doors (while an Opening concerns only one door)
        Visit.update_from_openings(verbosity=verbosity)

        if verbosity > 0:
            print(f"Done!")
