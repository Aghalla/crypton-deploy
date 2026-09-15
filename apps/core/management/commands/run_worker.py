"""Run the background worker standalone (outside runserver)."""
from django.core.management.base import BaseCommand

from apps.core.worker import start_worker_threads


class Command(BaseCommand):
    help = 'Run the market-data / analysis / monitoring worker loops.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('worker started — press Ctrl+C to stop'))
        stop = start_worker_threads()
        try:
            while True:
                stop.wait(3600)
        except KeyboardInterrupt:
            stop.set()
            self.stdout.write('worker stopped')
