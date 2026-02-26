# Beazley's concurrency w/o threads with Generators

import time
from collections import deque


class Scheduler:
    def __init__(self):
        self.ready = deque()

    def call_soon(self, func):
        self.ready.append(func)

    def run(self):
        while self.ready:
            self.current = self.ready.popleft()
            try:
                next(self.current)  # Trigger next in the item
                if self.current:
                    self.ready.append(self.current)  # Only drive it once.
            except StopIteration:
                pass


def countdown(n):
    while n > 0:
        print(f"Down {n}")
        time.sleep(1)
        yield
        n -= 1


def countup(n):
    x = 0
    while x < n:
        print(f"Up {x}")
        time.sleep(1)
        yield
        x += 1


if __name__ == "__main__":
    sched = Scheduler()
    sched.call_soon(countdown(5))
    sched.call_soon(countup(5))
    sched.run()
