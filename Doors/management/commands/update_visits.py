from django.core.management.base import BaseCommand

from Doors.models import Visit


class Command(BaseCommand):
    help = 'Updates Visits from recorded Openings'

    def add_arguments(self , parser):
        parser.add_argument('-r', '--rebuild', action='store_true', help="rebuild all Visits (i.e. don't just process new events")
        parser.add_argument('-R', '--Rebuild', action='store_true', help="Same as -r but delete all existing visits first.")

    def handle(self, *args, **kwargs):
        # A visit spans all doors (while an Opening concerns only one door)
        Visit.update_from_openings(rebuild=kwargs['rebuild'], Rebuild=kwargs['Rebuild'], verbosity=kwargs['verbosity'])
