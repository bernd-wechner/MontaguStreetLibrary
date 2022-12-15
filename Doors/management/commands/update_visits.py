import tinytuya, sys

from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

from Doors.models import Door, Event, Opening, Visit, EVENT_IDS, EVENT_SOURCES, DOOR_STATES, VISIT_SEPARATION


class Command(BaseCommand):
    help = 'Updates Visits from recorded Openings'

    def add_arguments(self , parser):
        parser.add_argument('--rebuild', action='store_true', help="rebuild all Visits (i.e. don't just process new events")

    def handle(self, *args, **kwargs):
        # A visit spans all doors (while an Opening concerns only one door)
        Visit.update_from_openings(rebuild=kwargs['rebuild'])
