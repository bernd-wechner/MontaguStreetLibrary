import tinytuya, sys

from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

from Doors.models import Door, Opening


class Command(BaseCommand):
    help = 'Updates Openings from recorded Events'

    def add_arguments(self , parser):
        parser.add_argument('--rebuild', action='store_true', help="rebuild all Openings (i.e. don't just process new events")

    def handle(self, *args, **kwargs):
        for door in Door.objects.all():
            Opening.update_from_events(door, rebuild=kwargs['rebuild'])
