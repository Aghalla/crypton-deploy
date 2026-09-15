from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core'

    def ready(self):
        import os
        import sys
        from django.conf import settings
        # Django autoreload creates two processes; only the reloader child
        # (RUN_MAIN=true) should start the worker to avoid duplicates.
        if 'runserver' in sys.argv and settings.WORKER_AUTOSTART:
            if os.environ.get('RUN_MAIN') != 'true':
                return
            import atexit
            import threading

            from apps.core.worker import start_worker_threads
            started = False
            lock = threading.Lock()

            def _start():
                nonlocal started
                with lock:
                    if started:
                        return
                    started = True
                stop = start_worker_threads()
                atexit.register(stop.set)

            # small delay so migrations checks finish first
            threading.Timer(3.0, _start).start()
