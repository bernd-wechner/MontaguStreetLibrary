from datetime import datetime, timedelta

from django.db import models
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.gis.db.models.lookups import OverlapsAboveLookup
from django.utils.functional import classproperty

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
EVENT_IDS = {1: "online",
             2: "offline",
             3: "device activation",
             4: "device reset",
             5: "command issuance",
             6: "firmware upgrade",
             7: "data report",
             8: "device semaphore",
             9: "device restart",
             10: "timing information"}

# translate door states True=Open, False=Closed
# Deduced by comparing a log here with one on the web at:
#     https://eu.iot.tuya.com/cloud/device/detail/
# where Tuya make that translation for us.
DOOR_STATES = { "true": "Open",
                "false": "Closed" }

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
    def datetime_from_timestamp(cls, tuya_timestamp):
        # A Tuya timestamp is 1000 times a standard Python timestamp
        return datetime.fromtimestamp(tuya_timestamp / 1000)

    @classmethod
    def timestamp_from_datetime(cls, date_time):
        # A Tuya timestamp is 1000 times a standard Python timestamp
        return datetime.timestamp(date_time) * 1000

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
    def save_logs(cls, door, log):
        '''
        Given Tuya logs for a given door, will save the to the Events table

        :param door: a Door object
        :param log: a log as returned by tinytuya.Cloud.getdevicelog
        '''

        for event in log['result']['logs']:
            event_code = event.get('code', None)

            if event_code == "doorcontact_state":
                try:
                    event_timestamp = int(event['event_time'])
                    event_date_time = cls.door_state_from_contact_state(event_timestamp)

                    if not Event.objects.filter(timestamp=event_timestamp, door=door).exists():
                        event_from = cls.source_from_int(int(event.get("event_from", None)))
                        event_type = cls.type_from_int(event.get("event_id", None))
                        event_value = cls.door_state_from_contact_state(event.get("value", None))

                        event = Event(timestamp=event_timestamp,
                                      source=event_from,
                                      code=event_code,
                                      type=event_type,
                                      value=event_value,
                                      door=door)

                        event.save()

                        assert event.date_time == cls.datetime_from_timestamp(event_date_time), "Oops, timestamp issue"
                except Exception as E:
                    pass


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

    @classmethod
    def last(cls):
        visits = cls.objects.all().order_by("-date_time")
        return visits[0] if visits else None

    @classmethod
    def update_from_openings(cls, rebuild=False):
        '''
        Creates new Visits as needed from newly created Openings.

        :param door: A Door instance
        '''
        # Find the last visit recorded
        last_visit = cls.last()

        # Get all openings after the start of the last visit (we reasses the last visit too)
        if last_visit and not rebuild:
            new_openings = Opening.objects.filter(date_time__gt=last_visit.date_time).order_by("date_time")
        # or all openings (if we have no visits for this door yet)
        else:
            new_openings = Opening.objects.all().order_by("date_time")

        # Break new_openings down into sets of openings each one a visit
        new_openings_by_visit = []
        visit_openings = []
        end_of_previous_opening = datetime.min
        visit_threshold = timedelta(minutes=VISIT_SEPARATION)
        for opening in new_openings:
            gap = opening.date_time - end_of_previous_opening

            if gap > visit_threshold:
                if visit_openings:
                    new_openings_by_visit.append(visit_openings)
                    visit_openings = []

            visit_openings.append(opening)
            end_of_previous_opening = opening.end_time

        if visit_openings:
            new_openings_by_visit.append(visit_openings)

        # Now create new Visits for each set of openings thus collected
        for openings in new_openings_by_visit:
            # Create a new visit with those openings
            start = openings[0].date_time
            end = openings[-1].end_time
            duration = end - start

            # Consider these a useful secondary key, and check that we haven't already
            # created this visit. If we have, use it and then proceed to updating the
            # doors and overlaps.
            try:
                visit = cls.objects.get(date_time=start,
                                        duration=duration,
                                        prior_quiet=gap)
            except cls.DoesNotExist:
                visit = cls.objects.create(date_time=start,
                                           duration=duration,
                                           prior_quiet=gap)

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
                    visit_olaps.append(olap)

            if visit.id == 19: breakpoint()

            visit.doors = visit_doors
            visit.overlaps = visit_olaps
            visit.save()


class Opening(models.Model):
    '''
    A reinterpretation of Events to pair Open and Close events into Openings.

    Created by scanning events, matching Opens with Closes on a given door and recorded here.
    '''
    date_time = models.DateTimeField('Time')
    duration = models.DurationField('Duration')

    door = models.ForeignKey(Door, related_name='openings', on_delete=models.PROTECT)
    visit = models.ForeignKey(Visit, related_name='openings', on_delete=models.PROTECT, null=True)
    open_event = models.ForeignKey(Event, related_name='openings', on_delete=models.PROTECT)
    close_event = models.ForeignKey(Event, related_name='closings', on_delete=models.PROTECT)

    @property
    def timestamp(self):
        return Event.timestamp_from_datetime(self.date_time)

    @property
    def end_time(self):
        return self.date_time + self.duration

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
    def update_from_events(cls, door, rebuild=False):
        # Find the last opening recorded
        last_opening = cls.last(door)

        # Get all events after it's closing event
        if last_opening and not rebuild:
            new_events = Event.objects.filter(door=door, timestamp__gt=last_opening.close_event.timestamp).order_by("timestamp")
        # or all events (if we have no openings for this door yet)
        else:
            new_events = Event.objects.filter(door=door).order_by("timestamp")

        # Assume closed state from outset
        # When there are no prior events it's just an aribtrary assumption (that we started collecting data when the door was shut)
        # When we have prior data, the new events are based on the last observed closing, so by defintion at that point the door was closed
        is_open = False
        opened = None
        for event in new_events:
            if event.value == "Open":
                if not is_open:
                    opened = event
                    is_open = True
                else:
                    # If multiple Open events are in a row, the last of them is the one
                    # matching the subsequent Closed event so on every bounce we update
                    # our record of which event opened the door.
                    opened = event
            elif event.value == "Closed":
                if is_open:
                    open_time = event.date_time - opened.date_time
                    is_open = False

                    # We don't know which visit this belongs to yet, as Visits are updated
                    # from openings later. So visit is left empty,

                    # We can treat the open and close events as a secondary key to check if
                    # this opening is already recorded. We only need to create it if it's new.
                    try:
                        opening = cls.objects.get(open_event=opened, close_event=event)
                        if opening.date_time != opened.date_time:
                            log.warning("Aparant, unexpected, change in Opening date_time")
                        if opening.duration != open_time:
                            log.warning("Aparant, unexpected, change in Opening duration")
                        if opening.door != door:
                            log.warning("Aparant, unexpected, change in Opening door")
                    except cls.DoesNotExist:
                        cls.objects.create(date_time=opened.date_time,
                                           duration=open_time,
                                           door=door,
                                           open_event=opened,
                                           close_event=event)
                else:
                    # If multiple Closed events are in a row, we ignore all but the
                    # first one (which we consider having closed the opening) but
                    # recorde these ignored events.
                    pass

