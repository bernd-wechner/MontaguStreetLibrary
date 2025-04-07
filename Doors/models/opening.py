import humanize

from datetime import timedelta

from django.db import models

from Site.logutils import log


class Opening(models.Model):
    '''
    A reinterpretation of Events to pair Open and Close events into Openings.

    Created by scanning events, matching Opens with Closes on a given door and recorded here.
    '''
    date_time = models.DateTimeField('Time')
    duration = models.DurationField('Duration')

    door = models.ForeignKey('Door', related_name='openings', on_delete=models.PROTECT)
    visit = models.ForeignKey('Visit', related_name='openings', on_delete=models.SET_NULL, null=True)
    open_event = models.ForeignKey('Event', related_name='openings', on_delete=models.PROTECT)
    close_event = models.ForeignKey('Event', related_name='closings', on_delete=models.PROTECT)

    @property
    def timestamp(self):
        from .event import Event
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
    def histogram(cls, htype="durations", categories=None):
        '''
        Returns data for populating a histogram of opening counts.
        In the form of a dict with category as key and count of openings and the value.

        :param htype:
        '''
        if htype == "durations":
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

                # remove empty categories
                return {l:c for l,c in visit_counts.items() if c !=0 }
            else:
                return None

    @classmethod
    def update_from_events(cls, door, rebuild=False, Rebuild=False, verbosity=0):
        '''
        Update openings from new events (or all events if rebuild requested)

        :param door: An instance of Door
        :param rebuild: Rebuild all openings (process all events)
        :param Rebuild: same as rebuild but delete all openings visits first (a hard reset)
        :param verbosity: Django manage.py argument for Verbosity level; 0=minimal output, 1=normal output, 2=verbose output, 3=very verbose output
        '''
        from .event import Event

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

