import calendar, humanize

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.functions import TruncDate
from django.db.models import Count
from django.db import models

from isodate import parse_duration
from numbers import Number
from collections import Counter
from datetime import datetime, timedelta

from .conf import VISIT_SEPARATION
from .door import Door
from .opening import Opening


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
        from .event import Event
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
    def histogram(cls, htype="day", categories=None):
        '''
        Returns data for populating a histogram of visit counts.
        In the form of a dict with category as key and count of visits and the value.

        :param htype:
        :param categories:
        '''
        # Create buckets of timedelta:
        #    hourly buckets for a delta of one day
        #    daily buckets for delta of 7 days or one month
        #    monthly buckets for delta of 1 year
        if htype == "day":
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
        elif htype == "week":
            field = "date_time__iso_week_day"
            visit_counts = cls.objects.all().values(field).annotate(count=Count(field)).order_by(field)
            data = {calendar.day_name[d]:0 for d in range(7)}
            for count in visit_counts:
                day = calendar.day_name[count[field] - 1]
                val = count["count"]
                data[day] = val
            return data
        elif htype == "month":
            field = "date_time__day"
            visit_counts = cls.objects.all().values(field).annotate(count=Count(field)).order_by(field)
            data = {str(d):0 for d in range(1, 32)}
            for count in visit_counts:
                day = str(count[field])
                val = count["count"]
                data[day] = val
            return data
        elif htype == "year":
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
        elif htype == "durations":
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
                durations = list(cls.objects.all().order_by(field).values_list(field, flat=True))
                longest = durations[-1]
                cats = round(longest / categories)
                visit_counts = {f"{label2(categories, c)}":0 for c in range(cats + 1)}
                for d in durations:
                    # d is a single value tuple (thanks Django!)
                    c = round(d / categories)
                    visit_counts[f"{label2(categories, c)}"] += 1

                # remove empty categories
                return {l:c for l,c in visit_counts.items() if c !=0 }
            else:
                return None
        elif htype == "quiet_times":
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
                quiets = list(cls.objects.filter(prior_quiet__lte=timedelta(days=1)).order_by(field).values_list(field, flat=True))
                longest = quiets[-1]
                cats = round(longest / min(categories, timedelta(weeks=8)))
                visit_counts = {f"{label2(categories, c)}":0 for c in range(cats + 1)}
                for q in quiets:
                    # d is a single value tuple (thanks Django!)
                    c = round(q / categories)
                    visit_counts[f"{label2(categories, c)}"] += 1
                return visit_counts
            else:
                return None
        elif htype == "per_days":
            if categories is None:
                categories = 1
            if isinstance(categories, Number):
                field = "date_time"
                per_day_frequency = Counter(cls.objects.annotate(day=TruncDate('date_time')).values('day').annotate(count=Count('id')).values_list('count', flat=True))
                # Order them and return
                return dict(sorted(dict(per_day_frequency).items()))
            else:
                return None
        elif htype == "opens_per_door":
            field = "doors"
            doors = list(cls.objects.all().order_by(field).values_list(field, flat=True))
            open_counts = {f"Door {d}":0 for d in Door.ids}
            for d in doors:
                # d is a list of doors openned during the visit in order.
                # It can contain duplicates, if a door is opened more than once in a visit
                # Hence, while a visit based historgram it counts openings.
                doors_opened = set(d)
                for door in doors_opened:
                    open_counts[f"Door {door}"] += 1
            return open_counts
        elif htype == "doors_per_visit_total":
            opening_frequency = Counter([o.openings.all().count() for o in cls.objects.all()])
            return dict(sorted(dict(opening_frequency).items()))
        elif htype == "doors_per_visit_unique":
            opening_frequency = Counter([len(set(o.openings.all().values_list('door__id', flat=True))) for o in cls.objects.all()])
            return dict(sorted(dict(opening_frequency).items()))
        elif htype == "overlap_durations":
            # Duration of multidoor overlaps (five states, no doors open, one door open, two doors open, three doors open, four doors opon)
            pass
        else:
            raise ValueError(f"No historgam defined for {categories=}, {htype=}")

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

