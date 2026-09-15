from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core'

    def ready(self):
        import os
        import sys
        from django.conf import settings
        if 'runserver' in sys.argv and settings.WORKER_AUTOSTART:
            # Standard Django autoreload: only the child process (RUN_MAIN=true)
            # should start workers.  But when --noreload is used there is only
            # one process and RUN_MAIN is never set — allow it in that case.
            noreload = '--noreload' in sys.argv
            run_main = os.environ.get('RUN_MAIN') == 'true'
            if not noreload and not run_main:
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
