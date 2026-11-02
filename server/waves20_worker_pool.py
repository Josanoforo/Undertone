"""Bounded dispatch workers for the Wave 20 delivery scheduler.

PRIMARY starts this only after configuring the real authority and bridge. The
pool never retries an operation: dispatch and unknown-effect handling remain
with Scheduler and JobBridge.
"""
import threading


class WorkerPool:
    def __init__(self, scheduler, *, workers, idle_seconds=0.1):
        if (not callable(getattr(scheduler, 'dispatch_one', None)) or
                type(workers) is not int or not 1 <= workers <= scheduler.concurrency or
                isinstance(idle_seconds, bool) or not isinstance(idle_seconds, (int, float)) or
                not 0.01 <= idle_seconds <= 10):
            raise ValueError('invalid worker pool configuration')
        self.scheduler = scheduler
        self.workers = workers
        self.idle_seconds = idle_seconds
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._threads = []
        self._started = False

    def start(self):
        with self._lock:
            if self._started:
                raise RuntimeError('worker pool already started')
            self._started = True
            self._threads = [threading.Thread(target=self._run, name='w20-delivery-%d' % i,
                                              daemon=True) for i in range(self.workers)]
            for thread in self._threads:
                thread.start()
        return self

    def _run(self):
        while not self._stop.is_set():
            try:
                worked = self.scheduler.dispatch_one()
            except Exception:
                # A failed dispatcher must not spin. Effect ambiguity is owned
                # by the scheduler/bridge; this loop does not resubmit work.
                worked = False
            if not worked:
                self._stop.wait(self.idle_seconds)

    def stop(self, timeout=0):
        """Stop new dispatch; report whether in-flight calls have returned."""
        import time
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 <= timeout <= 60:
            raise ValueError('invalid timeout')
        self._stop.set()
        deadline = time.monotonic() + timeout
        with self._lock:
            threads = list(self._threads)
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
        return all(not thread.is_alive() for thread in threads)
