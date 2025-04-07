'''
A basic URL resolution debugging command
'''
import json
from django.core.management.base import BaseCommand
from django.urls import resolve
from django.urls.exceptions import Resolver404


class Command(BaseCommand):
    help = 'Tries to resolve a URL and report on the process'

    def add_arguments(self , parser):
        parser.add_argument('URL', type=str, help="The URL to check")

    def handle(self, *args, **kwargs):
        URL = kwargs['URL']
        try:
            match = resolve(URL)

            print(f"Found a match!")
            print(f"Route: {match.route}")
            print(f"URL name: {match.url_name}")
            print(f"View name: {match.view_name}")
            print("Tried:")
            for pattern in match.tried:
                print(f"\t{pattern}")

        except Resolver404 as E:
            print(f"Failed to find match.")
            print(f"Path: {E.args[0]['path']}")
            print("Tried:")
            for pattern in E.args[0]['tried']:
                print(f"\t{pattern}")
