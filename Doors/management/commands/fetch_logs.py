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

So should be very safe for a daily download of, well as many as 1700 door sensors ;-).

My Devices are here:

    https://eu.iot.tuya.com/cloud/basic?id=p1668767995023hmaagk&toptab=related&deviceTab=all
'''
from django.core.management.base import BaseCommand

from Doors.models import DataFetch


class Command(BaseCommand):
    help = 'Fetches the Tuya Logs and updates the database accordingly'

    def handle(self, *args, **kwargs):
        DataFetch.fetch_logs(verbosity=kwargs['verbosity'])
