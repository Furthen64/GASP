import threading

class IdGenerator:
    def __init__(self):
        self._lock = threading.Lock()
        self._current = 0

    def next_id(self):
        with self._lock:
            self._current += 1
            return self._current

    def reset(self, start=0):
        with self._lock:
            self._current = start

CREATURE_ID_GEN = IdGenerator()
