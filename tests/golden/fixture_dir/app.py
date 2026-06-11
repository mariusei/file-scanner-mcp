"""Liten, stabil fixture for golden-test av scan_directory-formatet."""


class TaskQueue:
    """Holds pending tasks in priority order."""

    def __init__(self, capacity: int = 10):
        self.capacity = capacity
        self.items = []

    def push(self, task: str, priority: int) -> bool:
        """Add a task; reject when full."""
        if len(self.items) >= self.capacity:
            return False
        self.items.append((priority, task))
        self.items.sort(reverse=True)
        return True

    def pop(self) -> str:
        """Remove and return the highest-priority task."""
        return self.items.pop(0)[1]


def drain(queue: TaskQueue) -> list[str]:
    """Pop every task until the queue is empty."""
    drained = []
    while queue.items:
        drained.append(queue.pop())
    return drained
