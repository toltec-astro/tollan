"""A scripted scheduler for testing job records and supervision."""

import threading

from tollan.execution import SubmissionReceipt


class RecordingScheduler:
    """A scheduler that records its calls and replays configured results.

    ``statuses`` are returned in order, repeating the last one; an exception in
    the list is raised instead.
    """

    def __init__(self, *, found=(), statuses=(), error=None):
        self.submitted = []
        self.canceled = []
        self.found = list(found)
        self.statuses = list(statuses)
        self.error = error
        self.lock = threading.Lock()

    def submit(self, record):
        """Record the submission and return a receipt."""
        with self.lock:
            self.submitted.append(record.key)
            count = len(self.submitted)
        if self.error is not None:
            raise self.error
        return SubmissionReceipt(native_id=str(100 + count))

    def get_status(self, record, receipt):
        """Return the next scripted status."""
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        if isinstance(status, Exception):
            raise status
        return status

    def find(self, record, since):
        """Return the configured receipts."""
        return self.found

    def cancel(self, record, receipt):
        """Record the cancellation."""
        self.canceled.append(receipt.native_id)
