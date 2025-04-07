import humanize

from django_rich_views.model import field_render, link_target_url, RichMixIn

from django.utils.functional import classproperty, cached_property
from django.urls import reverse
from django.apps import apps
from django.db.models import Count
from django.db import models

from datetime import datetime

from .conf import EVENT_IDS, EVENT_CODES, DOOR_STATES, BATTERY_STATES


class Event(models.Model, RichMixIn):
    '''
    A low level model capturing all the events as Tuya provides them. Keyed on the Tuya timestamp which
    has millisecond resolution (int milliseconds since 01 Jan 1970) and so we make the bold assumption
    that no two events will ever bear the same timestamp (be logged to have happened at the same time
    down to the millisecond).

    Tuya documents:
    https://developer.tuya.com/en/docs/cloud/0a30fc557f?id=Ka7kjybdo0jse

    Parameter name    Type      Description
    code              String    Function point code
    value             Object    Function point value
    event_time        Long      Time stamp when the event occurred
    event_from        String    The source of the event  trigger, (1 device itself, 2 client instructions, 3 third-party  platforms, 4 cloud instructions, -1 unknown)
    event_id          Short     Type of event, (1 online, 2  offline, 3 device activation, 4 device reset, 5 command issuance, 6  firmware upgrade, 7 data point report, 8 device semaphore, 9 device  restart, 10 Timing information)
    row               String    Paid version parameter, which is the current row key
    status            String    The data is valid and has not been deleted. The default value is '1'
    '''
    timestamp = models.BigIntegerField('Tuya TimeStamp', primary_key=True)
    source = models.CharField('Tuya event source', max_length=64)
    code = models.CharField('Tuya event code', max_length=64)
    type = models.CharField('Tuya event type', max_length=64)
    value = models.CharField('Tuya event value', max_length=64)
    door = models.ForeignKey('Door', related_name='events', on_delete=models.PROTECT)
    data_fetch = models.ForeignKey('DataFetch', related_name='events', null=True, on_delete=models.PROTECT)

    # openings = OneToManyField(Opening, related_name='open_event') # Implicit by ForeignKey in Opening
    # closings = OneToManyField(Opening, related_name='close_event') # Implicit by ForeignKey in Opening
    # went_up = OneToManyField(Event, related_name='online_event') # Implicit by ForeignKey in Event
    # went_down = OneToManyField(Event, related_name='offline_event') # Implicit by ForeignKey in Event

    @property
    def date_time(self):
        return Event.datetime_from_timestamp(self.timestamp)

    @property
    def ignored(self):
        '''
        It can happen that events don't form enat Open/Closed pairs. Superfluous events are ignored.
        That is, they ar enot ever mentioned in an opening or closing.
        '''
        # TODO: test
        return (len(self.openings.all()) + len(self.closings.all())) == 0

    @classproperty
    def Ignored(cls):
        # TODO: test
        return cls.objects.filter(openings=None, closings=None)

    @classmethod
    def first(cls, code=None, door=None):
        '''
        Return the first event recorded for this door (or all doors)

        :param door: And instance of Door
        :param code: An Event code
        '''
        result = cls.objects.all()
        if result:
            if not door is None:
                result = result.filter(door=door)
            if not code is None:
                result = result.filter(code=code)
            result = result.order_by("timestamp")[0]

        return result

    @classmethod
    def last(cls, code=None, door=None):
        '''
        Return the last event recorded for this door (or all doors)

        On the very first run there are no events for the door so we catch the exception on trying to
        return the fist and return None.

        :param door: And instance of Door
        :param code: An Event code
        '''
        result = cls.objects.all()
        if result:
            if not door is None:
                result = result.filter(door=door)
            if not code is None:
                result = result.filter(code=code)
            result = result.order_by("-timestamp")[0]

        return result

    @classmethod
    def datetime_from_timestamp(cls, tuya_timestamp):
        # A Tuya timestamp is 1000 times a standard Python timestamp (milliseconds vs seconds)
        return datetime.fromtimestamp(tuya_timestamp / 1000)

    @classmethod
    def timestamp_from_datetime(cls, date_time):
        # A Tuya timestamp is 1000 times a standard Python timestamp (milliseconds vs seconds)
        return datetime.timestamp(date_time) * 1000

    @classmethod
    def days_from_timestamp_diff(cls, tuya_timestamp_diff):
        return tuya_timestamp_diff / 1000 / 60 / 60 / 24

    @classmethod
    def source_from_int(cls, source_int):
        return EVENT_IDS.get(source_int if isinstance(source_int, int) else int(source_int), "unknown")

    @classmethod
    def type_from_int(cls, type_int):
        return EVENT_IDS.get(type_int if isinstance(type_int, int) else int(type_int), "unknown")

    @classmethod
    def door_state_from_contact_state(cls, contact_state=None):
        return DOOR_STATES[contact_state] if contact_state in DOOR_STATES else contact_state

    @classmethod
    def save_logs(cls, door, log, fetch=None, verbosity=0):
        '''
        Given Tuya logs for a given door, will save the to the Events table

        :param door: a Door object
        :param log: a log as returned by tinytuya.Cloud.getdevicelog
        :param fetch: a DataFetch object that logs this fetch (created if not provided)
        :param verbosity: Django manage.py argument for Verbosity level; 0=minimal output, 1=normal output, 2=verbose output, 3=very verbose output
        '''
        if fetch is None:
            APP = __package__.split('.')[0]
            DataFetch = apps.get_model(APP, "DataFetch")
            fetch = DataFetch(date_time=datetime.now())
            fetch.save()

        added = 0
        code_counts = {}
        events = log['result']['logs']

        if verbosity >= 2:
            if events:
                time_start = cls.datetime_from_timestamp(int(events[0]['event_time']))
                time_end = cls.datetime_from_timestamp(int(events[-1]['event_time']))
                print(f"Downloaded {len(events)} events between {time_start} and {time_end}, spanning {humanize.precisedelta(time_end-time_start)}.")
            else:
                print(f"Downloaded NO events.")

        for i, event in enumerate(events):
            event_type = cls.type_from_int(event.get("event_id", None))
            event_code = event.get('code', None)
            event_value = event.get("value", None)
            event_timestamp = int(event['event_time'])
            event_date_time = cls.door_state_from_contact_state(event_timestamp)
            event_from = cls.source_from_int(int(event.get("event_from", None)))
            event_value = cls.door_state_from_contact_state(event.get("value", ""))

            # Where Tuya do not provide codes, we store an informative one for our use.
            if not event_code:
                if event_type in EVENT_CODES:
                    event_code = EVENT_CODES[event_type]

            if not event_code in code_counts:
                code_counts[event_code] = 0
            code_counts[event_code] += 1

            if verbosity >= 2:
                print(f"\t{i} of {len(events)}, {event_date_time}: {event_code}={event_value}")

            if event_code in ("doorcontact_state", "battery_state") or event_type in ("online", "offline"):
                try:
                    if not Event.objects.filter(timestamp=event_timestamp, door=door).exists():
                        event = Event(timestamp=event_timestamp,
                                      source=event_from,
                                      code=event_code,
                                      type=event_type,
                                      value=event_value,
                                      door=door,
                                      data_fetch=fetch)

                        event.save()

                        if verbosity >= 3:
                            print(f"\t\tSaved")

                        assert event.date_time == cls.datetime_from_timestamp(event_date_time), "Oops, timestamp issue"

                        added += 1
                    else:
                        if verbosity >= 3:
                            print(f"\t\tAlready in database.")
                except Exception as E:
                    if verbosity >= 3:
                        print(f"\t\tEvent creation failed with: {E}.")

        if verbosity >= 1:
            print(f"Door {door.id}: Fetched {len(events)} events, saved {added} events, {len(events)-added} events were already in the database.")
            for code in code_counts:
                print(f"\t{code_counts[code]} events with code '{code}' were downloaded.")

    @classproperty
    def orphans(cls):
        return cls.objects.filter(openings__isnull=True, closings__isnull=True, code='doorcontact_state')

    @classmethod
    def invalid_orphans(cls):
        invalid_orphans = []  # Suggest something went wrong when generating openings
        for o in cls.orphans:
            n = o.neighbours
            # The first and last event don't have neighbours at all and are valid orphans
            # if orphans they be. And every other orphan has neighbours and these must be
            # of the same value (open or close) to be a valid orphas, because if they
            # differ that is precisely when they were found unmatched and orphaned.
            valid = n[0] and n[1] and n[0].value == n[1].value
            if not valid:
                invalid_orphans.append(o)
        return invalid_orphans

    @classproperty
    def histogram(cls):
        # A basic count of all the events by code
        code_counts = cls.objects.values('code').annotate(count=Count('code'))
        event_counts = {c['code']: c['count'] for c in code_counts}
        # And an extra entry for doorcontact_state events that have no associated opening (are orphaned)
        event_counts['doorcontact_state_orphans'] = cls.orphans.count()
        return event_counts

    @classmethod
    def battery_graph(cls, door=None):
        '''
        Returns a time series of battery states, for a given door or all doors

        For one door it is a dict keyed on time, with a numeric battery state (3, 2, 1)
        and for all doors it's a list of such dicts.

        :param door: An instance of Door
        '''
        APP = __package__.split('.')[0]
        Door = apps.get_model(APP, "Door")
        if door is None:
            doors = Door.objects.all()
        else:
            doors = [door]

        graphs = []
        for door in doors:
            graph = dict()
            events = cls.objects.filter(door=door, code="battery_state").order_by("timestamp")
            zero = events.first().timestamp
            for event in events:
                time_value = cls.days_from_timestamp_diff(event.timestamp - zero)
                graph[time_value] = 1 + BATTERY_STATES.index(event.value)
            graphs.append(graph)

        return graphs[0] if len(graphs) == 1 else graphs

    @property
    def neighbours(self):
        before = Event.objects.filter(door=self.door, code='doorcontact_state', timestamp__lt=self.timestamp).order_by("-timestamp")
        after = Event.objects.filter(door=self.door, code='doorcontact_state', timestamp__gt=self.timestamp).order_by("timestamp")

        Before = before[0] if before else None
        After = after[0] if after else None

        return (Before, After)

    #########################################################################################
    # Django Rich Views supports nuanced rendering of the object

    def __str__(self):
        '''
        A basic default render. Should be on one line (contain no newlines, plain text.
        '''
        # Most codes have a value, uypdeown_state does not and records the value in type. Tuya!? Bizarre encoding.
        if self.code == 'doorcontact_state':
            value = f"Door {self.door.id} is {'opened' if self.value == 'Open' else 'closed'}"
        elif self.code == 'battery_state':
            value = f"Battery charge on door {self.door.id} is {self.value}"
        elif self.code == 'updown_state':
            value = f"Sensor on door {self.door.id} goes {self.type}"
        else:
            value = "ERROR: Unsupported event"

        return f"{self.date_time} - {value}"

    def __verbose_str__(self):
        '''
        A more verbose rendering but still on one line (contain no newlines), plain text.
        '''
        # TODO: Replicate __str__abobe and add the Opening ID with link, being None if no opening
        # Concider for Nones also makring whether it's a  valid or invalid orphan.
        return f"{self.date_time} - {self.code} - {self.type if self.code == 'updown_state' else self.value}"

    def __rich_str__(self, link=None):
        '''
        A rich rendering which, should still be on one line (no newlines) but can contain hyperlinks

        :param link: A django_rich_views.options.field_link_target
        '''
        if self.code == "doorcontact_state":
            text = 'opened' if self.value == 'Open' else 'closed'
            if self.openings.count() > 0:
                opening = field_render(text, link_target_url(self.openings.all()[0], link))
            elif self.closings.count() > 0:
                opening = field_render(text, link_target_url(self.closings.all()[0], link))
            else:
                opening = "unknown"

            return f"{self.date_time} - Door {self.door.id} has been {opening}"
        elif self.code == "updown_state":
            if self.went_up.count() > 0:
                uptime = field_render(self.type, link_target_url(self.went_up.all()[0], link))
            elif self.went_down.count() > 0:
                uptime = field_render(self.type, link_target_url(self.went_down.all()[0], link))
            else:
                uptime = "unknown"

            return f"{self.date_time} - Door {self.door.id} sensor going {uptime}"
        elif self.code == "battery_state":
            return f"{self.date_time} - Door {self.door.id} battery charge is {self.value}"

    def __detail_str__(self, link=None):
        '''
        A rich rendering that can contain hyperlinks and span multiple lines and include HTM for layout.

        :param link: A django_rich_views.options.field_link_target
        '''
        pass
        # TODO: Like Rich but on a sedon line indented include the the paired event summary!

