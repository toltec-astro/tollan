import re
from io import StringIO

from tollan.utils.log import logged_closing, logger, logit, timeit


class LogHelper:
    def __init__(self):
        logger.remove()
        buf = StringIO()
        logger.add(buf)
        self.logger = logger
        self.buf = buf

    def reset(self):
        self.buf.truncate(0)
        self.buf.seek(0)

    def assert_regex(self, regex):
        assert re.match(regex, self.buf.getvalue()) is not None
        self.reset()


def test_logit():
    log = LogHelper()

    with logit(logger.debug, "foo"):
        pass

    log.assert_regex(r".+test_log:test_logit:\d+ - ")

    @logit(logger.debug, "foo2")
    def some_func():
        pass

    some_func()
    log.assert_regex(r".+test_log:test_logit:\d+ - ")


def test_logged_closing():
    log = LogHelper()

    class A:
        def close(self):
            pass

    with logged_closing(logger.debug, A()):
        pass
    log.assert_regex(r".+test_log:test_logged_closing:\d+ -")


def test_timeit():
    log = LogHelper()

    with timeit("foo"):
        pass

    log.assert_regex(r".+test_log:test_timeit:\d+ - ")

    @timeit
    def some_func():
        pass

    some_func()
    log.assert_regex(r".+test_log:test_timeit:\d+ - ")
