import humanize, calendar, numpy as np
from datetime import datetime, timedelta
from numbers import Number
from isodate import parse_duration
from collections import Counter

from django.db import models
from django.db.models import Count, Q
from django.db.models.fields import DateField
from django.db.models.functions import Trunc, TruncDate, Cast
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.functional import classproperty

from django_rich_views.model import field_render, link_target_url

from Site.logutils import log

# Translate Tuya source IDs to a useful string describing the source
# Based on https://developer.tuya.com/en/docs/cloud/0a30fc557f?id=Ka7kjybdo0jse
EVENT_SOURCES = {-1: "unknown",
                  1: "device itself",
                  2: "client instructions",
                  3: "third-party platforms",
                  4: "cloud instructions"}

# Translate Tuya event IDs to a useful string describing the type of event
# Based on https://developer.tuya.com/en/docs/cloud/0a30fc557f?id=Ka7kjybdo0jse
EVENT_IDS = {-1: "unknown",
              1: "online",
              2: "offline",
              3: "device activation",
              4: "device reset",
              5: "command issuance",
              6: "firmware upgrade",
              7: "data report",
              8: "device semaphore",
              9: "device restart",
             10: "timing information"}

# JUst list the codes we support (for reference)
CODES = ["doorcontact_state", "updown_state", "battery_state"]

# translate door states True=Open, False=Closed
# Deduced by comparing a log here with one on the web at:
#     https://eu.iot.tuya.com/cloud/device/detail/
# where Tuya make that translation for us.
# Note: This is an EVENT not a STATE
DOOR_STATES = { "true": "Open",  # Moves the state from closed to open
                "false": "Closed" }  # Moves teh state fro open to closed

# The sensor only reports three battery states (alas).
BATTERY_STATES = ["low", "middle", "high"]

# And Event Type to code map
# Tuya only provide codes for "data report" events. But we give other event
# types a code as well, as we store it in a database column anyhow, to group
# related events.
UPTIMECODE = "updown_state"

EVENT_CODES = {"online": UPTIMECODE,
               "offline": UPTIMECODE }

# Defines the gap between openings that separates visits.
# A gap this long or greater is classified a new visit.
VISIT_SEPARATION = 10  # Minutes


class Door(models.Model):
    '''
    The registry of Library door switches being tracked.
    '''
    tuya_device_id = models.CharField('Tuya Device ID', max_length=64)
    contents = models.CharField('Description of contents', max_length=256)

    # openings = OneToManyField(Opening, related_name='door') # Implicit by ForeignKey in Opening
    # events = OneToManyField(Event, related_name='door') # Implicit by ForeignKey in Event

    @classproperty
    def ids(cls):
        return sorted([door.id for door in Door.objects.all()])


class Event(models.Model):
    '''
    A low level model capturing all the events as Tuya provides them. Keyed on the Tuya timestamp which
    has millisecond resolution (int milliseconds since 01 Jan 1970) and so we make the bold assumption
    that no two events will ever bear the same timestamp (be logged to have happened at the same time
    down to the millisecond).

    Tuya documents:
    https://developer.tuya.com/en/docs/cloud/0a30fc557f?id=Ka7kjybdo0jse

    Parameter name    Type      Description
    code              String    Function Point Code
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
    door = models.ForeignKey(Door, related_name='events', on_delete=models.PROTECT)

    # openings = OneToManyField(Opening, related_name='open_event') # Implicit by ForeignKey in Opening
    # closings = OneToManyField(Opening, related_name='close_event') # Implicit by ForeignKey in Opening

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
    def save_logs(cls, door, log, verbosity=0):
        '''
        Given Tuya logs for a given door, will save the to the Events table

        :param door: a Door object
        :param log: a log as returned by tinytuya.Cloud.getdevicelog
        :param verbosity: Django manage.py argument for Verbosity level; 0=minimal output, 1=normal output, 2=verbose output, 3=very verbose output
        '''

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
                                      door=door)

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
            if self.openings:
                opening = field_render(text, link_target_url(self.openings[0], link))
            elif self.closings:
                opening = field_render(text, link_target_url(self.closings[0], link))

            return f"{self.date_time} - Door {self.door.id} has been {opening}"
        elif self.code == "updown_state":
            if self.went_up:
                uptime = field_render(self.value, link_target_url(self.went_up[0], link))
            elif self.went_down:
                uptime = field_render(self.value, link_target_url(self.went_down[0], link))

            return f"{self.date_time} - Door {self.door.id} sensor going {uptime}"
        elif self.code == "battery_state":
            return f"{self.date_time} - Door {self.door.id} battery charge is {self.value}"

    def __detail_str__(self, link=None):
        '''
        A rich rendering that can contain hyperlinks and span multiple lines and include HTM for layout.

        :param link: A django_rich_views.options.field_link_target
        '''
        # TODO: Like Rich but on a sedon line indented include the the paired event summary!


class Visit(models.Model):
    '''
    A grouping of openings into a single visit. Just a group of openings really but we store
    properties of the group regardless, so we can get anb overview of visits in a standard
    model view.
    '''
    date_time = models.DateTimeField('Time')
    duration = models.DurationField('Duration')
    prior_quiet = models.DurationField('Duration')
    # Populated after creating the object so can be null
    doors = models.JSONField(null=True, encoder=DjangoJSONEncoder)  # List of Door IDs in order opened (can contain duplicates)
    overlaps = models.JSONField(null=True, encoder=DjangoJSONEncoder)  # List of tuples conveying doors open simultaneously (overlapping openings)

    # openings = OneToManyField(Opening, related_name='visit') # Implicit by ForeignKey in Opening

    @property
    def timestamp(self):
        return Event.timestamp_from_datetime(self.date_time)

    @property
    def end_time(self):
        return self.date_time + self.duration

    @property
    def olaps(self):
        return [(olap[0], olap[1], parse_duration(olap[2])) for olap in self.overlaps]

    @classmethod
    def last(cls):
        visits = cls.objects.all().order_by("-date_time")
        return visits[0] if visits else None

    @classmethod
    def recent(cls, period=timedelta(days=7)):
        '''
        Returns the most recent visits (for a nice table of same on a web page)

        :param period: A timedelta representing the most recent visits in that time.
        '''
        from_time = datetime.now() - period
        return cls.objects.filter(date_time__gte=from_time).order_by("-date_time")

    @classmethod
    def histogram(cls, span="day", categories=None):
        '''
        Returns data for populating a histogram of visit counts.
        In the form of a dict with category as key and count of visits and the value.

        :param span:
        :param categories:
        '''
        # Create buckets of timedelta:
        #    hourly buckets for a delta of one day
        #    daily buckets for delta of 7 days or one month
        #    monthly buckets for delta of 1 year
        if span == "day":
            field = "date_time__hour"
            visit_counts = cls.objects.all().values(field).annotate(count=Count(field)).order_by(field)
            data = {f"{h}-{h+1 if h < 24 else 1}":0 for h in range(25)}
            for count in visit_counts:
                hour = count[field]
                next_hour = hour + 1 if hour < 24 else 1
                cat = f"{hour}-{next_hour}"
                val = count["count"]
                data[cat] = val
            return data
        elif span == "week":
            field = "date_time__iso_week_day"
            visit_counts = cls.objects.all().values(field).annotate(count=Count(field)).order_by(field)
            data = {calendar.day_name[d]:0 for d in range(7)}
            for count in visit_counts:
                day = calendar.day_name[count[field] - 1]
                val = count["count"]
                data[day] = val
            return data
        elif span == "month":
            field = "date_time__day"
            visit_counts = cls.objects.all().values(field).annotate(count=Count(field)).order_by(field)
            data = {str(d):0 for d in range(1, 32)}
            for count in visit_counts:
                day = str(count[field])
                val = count["count"]
                data[day] = val
            return data
        elif span == "year":
            if categories == "months":
                field = "date_time__month"
                visit_counts = cls.objects.all().values(field).annotate(count=Count(field)).order_by(field)
                data = {calendar.month_name[d]:0 for d in range(1, 13)}
                for count in visit_counts:
                    month = calendar.month_name[count[field]]
                    val = count["count"]
                    data[month] = val
                return data
            elif categories == "weeks":
                field = "date_time__week"
                visit_counts = cls.objects.all().values(field).annotate(count=Count(field)).order_by(field)
                data = {str(d):0 for d in range(1, 53)}
                for count in visit_counts:
                    week = str(count[field])
                    val = count["count"]
                    data[week] = val
                return data
        elif span == "durations":
            if categories is None:
                categories = timedelta(minutes=1)
            if isinstance(categories, timedelta):

                def label(td, i):
                    secs = round((i * td).total_seconds())
                    mins, secs = divmod(secs, 60)
                    return f"{mins}:{secs:02d}"

                def label2(td, i):
                    return f"{label(td, i)}-{label(td, i+1)}"

                field = "duration"
                durations = list(cls.objects.all().order_by(field).values_list(field))
                longest = durations[-1][0]
                cats = round(longest / categories)
                visit_counts = {f"{label2(categories, c)}":0 for c in range(cats + 1)}
                for d in durations:
                    # d is a single value tuple (thanks Django!)
                    c = round(d[0] / categories)
                    visit_counts[f"{label2(categories, c)}"] += 1
                return visit_counts
            else:
                return None
        elif span == "quiet_times":
            if categories is None:
                categories = timedelta(minutes=1)
            if isinstance(categories, timedelta):

                def label(td, i):
                    secs = round((i * td).total_seconds())
                    mins, secs = divmod(secs, 60)
                    hours, mins = divmod(mins, 60)
                    return f"{hours}:{mins:02d}"

                def label2(td, i):
                    return f"{label(td, i)}-{label(td, i+1)}"

                field = "prior_quiet"
                # Consider any over 1 day outliers and ignore them.
                # Missing data assumed to be the cause (for now)
                quiets = list(cls.objects.filter(prior_quiet__lte=timedelta(days=1)).order_by(field).values_list(field))
                longest = quiets[-1][0]
                cats = round(longest / min(categories, timedelta(weeks=8)))
                visit_counts = {f"{label2(categories, c)}":0 for c in range(cats + 1)}
                for q in quiets:
                    # d is a single value tuple (thanks Django!)
                    c = round(q[0] / categories)
                    visit_counts[f"{label2(categories, c)}"] += 1
                return visit_counts
            else:
                return None
        elif span == "per_days":
            if categories is None:
                categories = 1
            if isinstance(categories, Number):
                field = "date_time"
                per_day_frequency = Counter(cls.objects.annotate(day=TruncDate('date_time')).values('day').annotate(count=Count('id')).values_list('count', flat=True))
                # Order them and return
                return dict(sorted(dict(per_day_frequency).items()))
            else:
                return None
        elif span == "visits_per_door":
            field = "doors"
            doors = list(cls.objects.all().order_by(field).values_list(field))
            visit_counts = {f"Door {d}":0 for d in Door.ids}
            for d in doors:
                # d is a single value tuple (thanks Django!)
                doors_opened = set(d[0])
                for door in doors_opened:
                    visit_counts[f"Door {door}"] += 1
            return visit_counts
        elif span == "doors_per_visit_total":
            opening_frequency = Counter([o.openings.all().count() for o in cls.objects.all()])
            return dict(sorted(dict(opening_frequency).items()))
        elif span == "doors_per_visit_unique":
            opening_frequency = Counter([len(set(o.openings.all().values_list('door__id', flat=True))) for o in cls.objects.all()])
            return dict(sorted(dict(opening_frequency).items()))

        else:
            raise ValueError(f"No historgam defined for {categories=}, {span=}")

    @classmethod
    def update_from_openings(cls, rebuild=False, Rebuild=False, verbosity=0):
        '''
        Creates new_visits Visits as needed from newly created Openings.

        :param rebuild: Rebuild all openings (process all events)
        :param Rebuild: same as rebuild but delete all existing visits first (a hard reset)
        :param verbosity: Django manage.py argument for Verbosity level; 0=minimal output, 1=normal output, 2=verbose output, 3=very verbose output
        '''
        # Find the last visit recorded
        last_visit = cls.last()

        # Get all openings after the start of the last visit (we reasses the last visit too)
        if last_visit and not (rebuild or Rebuild):
            new_openings = Opening.objects.filter(date_time__gt=last_visit.date_time).order_by("date_time")
        # or all openings (if we have no visits for this door yet)
        else:
            if Rebuild:
                cls.objects.all().delete()
            new_openings = Opening.objects.all().order_by("date_time")

        if new_openings:
            if verbosity >= 2:
                print(f"Processing {len(new_openings)} openings.")
        else:
            if verbosity >= 2:
                print(f"No new openings to process")
            return

        # Break new_openings down into sets of openings each one a visit
        new_openings_by_visit = []
        visit_openings = []
        previous_opening = new_openings[0].previous
        end_of_previous_opening = previous_opening.date_time if previous_opening else new_openings[0].date_time
        previous_gap = previous_opening.visit.prior_quiet if previous_opening else timedelta()
        visit_threshold = timedelta(minutes=VISIT_SEPARATION)
        existing_visits = []
        new_visits = []
        first_new_opening = True
        started_mid_visit = False
        for opening in new_openings:
            gap = opening.date_time - end_of_previous_opening

            if verbosity >= 2:
                print(f"\tDoor {opening.door.id} opened at {opening.date_time} for {humanize.precisedelta(opening.duration,format='%0.1f')} after {humanize.precisedelta(gap,format='%0.1f')}")

            if gap > visit_threshold:
                if visit_openings:
                    new_openings_by_visit.append((visit_openings, previous_gap))
                    visit_openings = []
                    previous_gap = gap
            elif first_new_opening and previous_opening:
                started_mid_visit = True
            first_new_opening = False

            visit_openings.append(opening)
            end_of_previous_opening = opening.end_time

        # The last set of openings form  a visit without a gap defining them amd may cause us to
        # start next update mid visit. But we group them as a provisional visit
        if visit_openings:
            new_openings_by_visit.append((visit_openings, previous_gap))

        if verbosity >= 2:
            print(f"Identified {len(new_openings_by_visit)} visits (groups of openings, separated by at least {humanize.precisedelta(visit_threshold)}).")

        # Now create new Visits for each set of openings thus collected
        for i, (openings, prior_quiet) in enumerate(new_openings_by_visit):
            # Create a new visit with those openings
            start = previous_opening.visit.date_time if (i == 0 and started_mid_visit) else openings[0].date_time
            end = openings[-1].end_time
            duration = end - start

            try:
                # Consider the start time a pseudo key ... if a visit exists that started then it's our
                # visit surely. It was created earlier and has a prior_quiet and a duration (which may
                # be wrong because we may have an updated end time if we started mid visit above.
                visit = cls.objects.get(date_time=start)

                # Update the duration (we add this now to cater for the edge case of started_mid_visit)
                # The visit will exits and need updating.
                visit.duration = duration

                existing_visits.append(visit)

                if verbosity >= 3:
                    print(f"\tVisit already exists at {visit.date_time} for {humanize.precisedelta(visit.duration,format='%0.1f')}.")
            except cls.DoesNotExist:
                visit = cls.objects.create(prior_quiet=prior_quiet, date_time=start, duration=duration)

                new_visits.append(visit)

                if verbosity >= 3:
                    print(f"\tNew visit at {visit.date_time} for {humanize.precisedelta(visit.duration,format='%0.1f')}.")

            # Point all the openings in this visit to it
            for opening in openings:
                opening.visit = visit
                opening.save()

            # Work out the door opening overlaps
            visit_doors = []
            visit_olaps = []

            previous_spans = []  # Record or previous spans in (span_end_time, door) 2-tuples

            # Measure of overlap keyed on door pairs
            # A 2D dict such that the first index is the door newly opened while the second door is already open
            # The number of doors already open when a door is openned can thus easily be determined by the non
            # zero entries for overlap time. timedelta() is a zero duration and we initialise the 2D block
            # with  zeros so that teh accumulator can just add overlaps as detected.
            door_olap = {i: {j: timedelta() for j in Door.ids} for i in Door.ids}

            # Check each opening of the visit in temporal order for overlapping spans in time.
            for opening in openings:
                span_start = opening.date_time
                span_end = opening.end_time
                span_door = opening.door.id

                # Check for previous spans still running when this one starts
                # previous_spans is a list of (span_end_time, door) 2-tuples
                for pspan_end, pspan_door in previous_spans:
                    # For each previous span that overlaps we accumular the list of overlapping doors
                    # and the duration of total overlap
                    if span_start < pspan_end:
                        span_olap = min(pspan_end, span_end) - span_start
                        # Accumulate the overlap total and per door
                        # It is accumulated twice, once for each door in the overlap.
                        door_olap[span_door][pspan_door] += span_olap

                previous_spans.append((span_end, span_door))
                visit_doors.append(span_door)

            for door_i in Door.ids:
                olap = []
                for door_j in Door.ids:
                    if door_olap[door_i][door_j] > timedelta():
                        olap.append((door_i, door_j, door_olap[door_i][door_j]))
                if olap:
                    visit_olaps.extend(olap)

            visit.doors = visit_doors
            visit.overlaps = visit_olaps
            visit.save()

        if verbosity >= 1:
            print(f"Processed {len(new_openings)} openings, saved {len(new_visits)} new visits.")
            if len(new_visits) > 0:
                print(f"\tfrom {new_visits[0].date_time} to {new_visits[-1].date_time}")
            if len(existing_visits) > 0:
                print(f"\tfound {len(existing_visits)} visits, reprocessed.")


class Opening(models.Model):
    '''
    A reinterpretation of Events to pair Open and Close events into Openings.

    Created by scanning events, matching Opens with Closes on a given door and recorded here.
    '''
    date_time = models.DateTimeField('Time')
    duration = models.DurationField('Duration')

    door = models.ForeignKey(Door, related_name='openings', on_delete=models.PROTECT)
    visit = models.ForeignKey(Visit, related_name='openings', on_delete=models.SET_NULL, null=True)
    open_event = models.ForeignKey(Event, related_name='openings', on_delete=models.PROTECT)
    close_event = models.ForeignKey(Event, related_name='closings', on_delete=models.PROTECT)

    @property
    def timestamp(self):
        return Event.timestamp_from_datetime(self.date_time)

    @property
    def end_time(self):
        return self.date_time + self.duration

    @property
    def previous(self):
        earlier = self.__class__.objects.filter(date_time__lt=self.date_time).order_by("-date_time")
        return earlier[0] if len(earlier) > 0 else None

    @classmethod
    def last(cls, door=None):
        '''
        Returns the last Opening recorded or a given door
        :param door: An instance of Door
        '''
        if door is None:
            openings = cls.objects.all().order_by("-date_time")
        else:
            openings = cls.objects.filter(door=door).order_by("-date_time")
        return openings[0] if openings else None

    @classmethod
    def update_from_events(cls, door, rebuild=False, Rebuild=False, verbosity=0):
        '''
        Update openings from new events (or all events if rebuild requested)

        :param door: An instance of Door
        :param rebuild: Rebuild all openings (process all events)
        :param Rebuild: same as rebuild but delete all openings visits first (a hard reset)
        :param verbosity: Django manage.py argument for Verbosity level; 0=minimal output, 1=normal output, 2=verbose output, 3=very verbose output
        '''
        # Find the last opening recorded
        last_opening = cls.last(door)

        # Get all events after it's closing event
        if last_opening and not (rebuild or Rebuild):
            new_events = Event.objects.filter(door=door, code="doorcontact_state", timestamp__gt=last_opening.close_event.timestamp).order_by("timestamp")
        # or all events (if we have no openings for this door yet)
        else:
            if Rebuild:
                cls.objects.filter(door=door).delete()
            new_events = Event.objects.filter(door=door, code="doorcontact_state").order_by("timestamp")

        if verbosity >= 2:
            print(f"Processing {len(new_events)} Open/Close events for door {door.id}.")

        # Assume closed state from outset
        # When there are no prior events it's just an aribtrary assumption (that we started collecting data when the door was shut)
        # When we have prior data, the new events are based on the last observed closing, so by defintion at that point the door was closed
        is_open = False
        opened = None
        existing_openings = []
        new_openings = []
        orphan_events = []
        for event in new_events:
            if verbosity >= 2:
                print(f"\t{event.value:6} at {event.date_time}")

            if event.value == "Open":
                if not is_open:
                    opened = event
                    is_open = True
                else:
                    # If multiple Open events are in a row, the last of them is the one
                    # matching the subsequent Closed event so on every bounce we update
                    # our record of which event opened the door.
                    orphan_events.append(opened)
                    opened = event
            elif event.value == "Closed":
                if is_open:
                    open_time = event.date_time - opened.date_time
                    is_open = False

                    # We don't know which visit this belongs to yet, as Visits are updated
                    # from openings later. So visit is left empty,

                    # We can treat the open and close events as a secondary key to check if
                    # this opening is already recorded. We only need to create it if it's new
                    try:
                        opening = cls.objects.get(open_event=opened, close_event=event)
                        if opening.date_time != opened.date_time:
                            log.warning("Apparant, unexpected, change in Opening date_time")
                        if opening.duration != open_time:
                            log.warning("Apparant, unexpected, change in Opening duration")
                        if opening.door != door:
                            log.warning("Apparant, unexpected, change in Opening door")

                        existing_openings.append(opening)

                        if verbosity >= 3:
                            print(f"\t\tOpening already exists and has integrity.")

                    except cls.DoesNotExist:
                        opening = cls.objects.create(date_time=opened.date_time,
                                                     duration=open_time,
                                                     door=door,
                                                     open_event=opened,
                                                     close_event=event)
                        new_openings.append(opening)

                        if verbosity >= 3:
                            print(f"\t\tOpening saved. Door {opening.door.id} opened at {opening.date_time} for {humanize.precisedelta(opening.duration,format='%0.1f')} ")
                else:
                    # If multiple Closed events are in a row, we ignore all but the
                    # first one (which we consider having closed the opening) but
                    # recorde these ignored events.
                    orphan_events.append(event)
                    pass

        if verbosity >= 1:
            print(f"Door {door.id}: Processed {len(new_events)} events, saved {len(new_openings)} new openings for door {door.id}.")
            if len(new_openings) > 0:
                print(f"\tfrom {new_openings[0].date_time} to {new_openings[-1].date_time}")
            if len(existing_openings) > 0:
                print(f"\tand found {len(existing_openings)} openings already saved.")
            if len(orphan_events) > 0:
                print(f"\tand found {len(orphan_events)} orphaned events (unmatched opens or closes).")


class Uptime(models.Model):
    '''
    A reinterpretation of Events to pair Online and Offline events into an Up time record.

    Created by scanning events, matching Online with Offline on a given door and recorded here.
    '''
    date_time = models.DateTimeField('Time')
    duration = models.DurationField('Duration')

    door = models.ForeignKey(Door, related_name='uptimes', on_delete=models.PROTECT)
    online_event = models.ForeignKey(Event, related_name='went_up', on_delete=models.PROTECT)
    offline_event = models.ForeignKey(Event, related_name='went_down', on_delete=models.PROTECT)

    @property
    def timestamp(self):
        return Event.timestamp_from_datetime(self.date_time)

    @property
    def end_time(self):
        return self.date_time + self.duration

    @classmethod
    def last(cls, door=None):
        '''
        Returns the last Uptime recorded or a given door
        :param door: An instance of Door
        '''
        if door is None:
            uptimes = cls.objects.all().order_by("-date_time")
        else:
            uptimes = cls.objects.filter(door=door).order_by("-date_time")
        return uptimes[0] if uptimes else None

    @classmethod
    def update_from_events(cls, door, rebuild=False, Rebuild=False, verbosity=0):
        '''
        Update opensings from new events (or all events if rebuild requested)

        :param door: An instance of Door
        :param rebuild: Rebuild all uptimes (process all events)
        :param Rebuild: Same as rebuild but delete all existing uptimes first (a hard reset)
        :param verbosity: Django manage.py argument for Verbosity level; 0=minimal output, 1=normal output, 2=verbose output, 3=very verbose output
        '''
        # Find the last opening recorded
        last_uptime = cls.last(door)

        # Get all events after it's closing event
        if last_uptime and not (rebuild or Rebuild):
            new_events = Event.objects.filter(door=door, code=UPTIMECODE, timestamp__gt=last_uptime.online_event.timestamp).order_by("timestamp")
        # or all events (if we have no openings for this door yet)
        else:
            if Rebuild:
                cls.objects.filter(door=door).delete()
            new_events = Event.objects.filter(door=door, code=UPTIMECODE).order_by("timestamp")

        if verbosity >= 2:
            print(f"Processing {len(new_events)} Up/Down events for the switch on door {door.id}.")

        # Assume switch is down at outset
        # When there are no prior events it's just an aribtrary assumption but a fair one as the switches ony come up for a state transmission
        # When we have prior data, the new events are based on the last observed down event, so by defintion at that point the switch was down
        is_up = False
        up_event = None
        existing_uptimes = []
        new_uptimes = []
        for event in new_events:
            if verbosity >= 2:
                print(f"\t{event.type:7} at {event.date_time}")

            if event.type == "online":
                if not is_up:
                    up_event = event
                    is_up = True
                else:
                    # If multiple Online events are in a row, the first of them is the one
                    # we'll assume started the on-uptime, until an Offline event is reached.
                    pass
            elif event.type == "offline":
                if is_up:
                    up_duration = event.date_time - up_event.date_time
                    is_up = False

                    # We can treat the online and offline  events as a secondary key to check if
                    # this uptime is already recorded. We only need to create it if it's new
                    try:
                        uptime = cls.objects.get(online_event=up_event, offline_event=event)
                        if uptime.date_time != up_event.date_time:
                            log.warning("Apparant, unexpected, change in Uptime date_time")
                        if uptime.duration != up_duration:
                            log.warning("Apparant, unexpected, change in Uptime duration")
                        if uptime.door != door:
                            log.warning("Apparant, unexpected, change in Uptime door")

                        existing_uptimes.append(uptime)

                        if verbosity >= 3:
                            print(f"\t\tUptime already exists and has integrity.")

                    except cls.DoesNotExist:
                        uptime = cls.objects.create(date_time=up_event.date_time,
                                                    duration=up_duration,
                                                    door=door,
                                                    online_event=up_event,
                                                    offline_event=event)
                        new_uptimes.append(uptime)

                        if verbosity >= 3:
                            print(f"\t\tUptime saved. Door {uptime.door.id} switch went up at {uptime.date_time} for {humanize.precisedelta(uptime.duration,minimum_unit='microseconds',format='%0.1f')} ")

                else:
                    # If multiple Closed events are in a row, we ignore all but the
                    # first one (which we consider having closed the opening) but
                    # recorde these ignored events.
                    pass

        if verbosity >= 1:
            print(f"Door {door.id}: Processed {len(new_events)} events, saved {len(new_uptimes)} new uptimes for the switch on door {door.id}.")
            if len(new_uptimes) > 0:
                print(f"\tfrom {new_uptimes[0].date_time} to {new_uptimes[-1].date_time}")
            if len(existing_uptimes) > 0:
                print(f"\tand found {len(existing_uptimes)} openings already saved.")

    @classmethod
    def histogram(cls):
        '''
        Returns data for populating a histogram of uptimes.
        In the form of a dict with duration band as key and count of uptimes in that band and the value.
        '''
        uptimes = cls.objects.all().values_list('duration', flat=True)

        # Get the uptimes in seconds ...
        seconds = list(map(lambda d: d.total_seconds(), uptimes))

        # Ask numpy to create some bins for us
        bins = np.histogram_bin_edges(seconds, bins='auto')

        # round the bin edges as numpy doesn't have a way of asking for that
        bins = list(map(round, bins))
        # Add 1s he last bin edge as if was roduned down if it was under 0.5 and would exclude durations above the original value if rounded down.
        bins[-1] = bins[-1] + 1

        # Now ask numpy to bin the values ...
        hist = np.histogram(seconds, bins)

        # Create category labels
        labels = [f"{s}-{e}" for s, e in zip(bins[:-1], bins[1:])]

        # Now create the dict we want to return
        counts = hist[0]
        histogram = {l:c for l, c in zip(labels, counts)}

        return histogram
