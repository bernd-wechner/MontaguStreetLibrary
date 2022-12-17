from django.core.management.base import BaseCommand

from Doors.models import Door, Uptime


class Command(BaseCommand):
    help = 'Updates Openings from recorded Events'

    def add_arguments(self , parser):
        parser.add_argument('-r', '--rebuild', action='store_true', help="rebuild all uptimes (i.e. don't just process new events)")
        parser.add_argument('-R', '--Rebuild', action='store_true', help="Same as -r but delete all existing uptimes first.")

    def handle(self, *args, **kwargs):
        for door in Door.objects.all():
            Uptime.update_from_events(door, rebuild=kwargs['rebuild'], Rebuild=kwargs['Rebuild'], verbosity=kwargs['verbosity'])
