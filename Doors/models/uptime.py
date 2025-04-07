import humanize, numpy as np

from django.db import models

from .conf import UPTIME_CODE
from .door import Door

from Site.logutils import log


class Uptime(models.Model):
    '''
    A reinterpretation of Events to pair Online and Offline events into an Up time record.

    Created by scanning events, matching Online with Offline on a given door and recorded here.
    '''
    date_time = models.DateTimeField('Time')
    duration = models.DurationField('Duration')

    door = models.ForeignKey(Door, related_name='uptimes', on_delete=models.PROTECT)
    online_event = models.ForeignKey('Event', related_name='went_up', on_delete=models.PROTECT)
    offline_event = models.ForeignKey('Event', related_name='went_down', on_delete=models.PROTECT)

    @property
    def timestamp(self):
        from .event import Event
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
        from .event import Event

        last_uptime = cls.last(door)

        # Get all events after it's closing event
        if last_uptime and not (rebuild or Rebuild):
            new_events = Event.objects.filter(door=door, code=UPTIME_CODE, timestamp__gt=last_uptime.online_event.timestamp).order_by("timestamp")
        # or all events (if we have no openings for this door yet)
        else:
            if Rebuild:
                cls.objects.filter(door=door).delete()
            new_events = Event.objects.filter(door=door, code=UPTIME_CODE).order_by("timestamp")

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

        # remove zero entries
        return {l:c for l,c in histogram.items() if c != 0}
