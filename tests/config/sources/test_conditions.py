"""The operator recipe language uses pandas query precedence and membership."""

import pytest

from tollan.config.sources import ConfigSourceList, DictConfigSource
from tollan.utils.log import logger


@pytest.fixture
def debug_messages():
    messages = []
    sink = logger.add(
        lambda message: messages.append(str(message)), format="{message}", level="DEBUG"
    )
    try:
        yield messages
    finally:
        logger.remove(sink)


@pytest.mark.parametrize(
    ("context", "reason"),
    [
        (None, "no context provided"),
        ({"workers": 8}, "name 'missing' is not defined"),
    ],
)
def test_disabled_condition_log_includes_context_and_reason(
    context, reason, debug_messages
):
    source = DictConfigSource(
        order=7, name="settings", source={}, enable_if="missing > 0"
    )
    assert source.is_enabled_for(context) is False
    message = debug_messages[-1]
    assert "Source settings (order=7): disabled" in message
    assert "enable_if='missing > 0'" in message
    assert f"context={context!r}" in message
    assert reason in message


@pytest.mark.parametrize(("workers", "status"), [(8, "enabled"), (2, "disabled")])
def test_source_list_logs_condition_result_and_context(workers, status, debug_messages):
    source = DictConfigSource(
        order=7, name="settings", source={}, enable_if="workers >= 4"
    )
    ConfigSourceList(data=[source]).load({"workers": workers})
    message = debug_messages[-1]
    assert "Source settings (order=7, idx=0)" in message
    assert f"{status} by enable_if='workers >= 4'" in message
    assert f"context={{'workers': {workers}}}" in message


@pytest.mark.parametrize("channel", range(13))
@pytest.mark.parametrize("kind", ["survey", "target", "tuning"])
def test_recipe_condition_truth_table(channel, kind):
    context = {"channel": channel, "kind": kind}
    # Conditions an application recipe uses, plus language combinations.
    cases = [
        (None, True),
        ("channel >= 7", channel >= 7),
        (
            'channel >= 7 & kind in ["target", "tuning"]',
            channel >= 7 and kind in {"target", "tuning"},
        ),
        ('kind == "survey"', kind == "survey"),
        ('kind == "target"', kind == "target"),
        ('kind == "tuning"', kind == "tuning"),
        ('channel >= 7 | kind == "tuning"', channel >= 7 or kind == "tuning"),
        ('kind not in ["tuning"]', kind != "tuning"),
        (
            '~(channel < 7 | kind == "survey")',
            not (channel < 7 or kind == "survey"),
        ),
        ("0 <= channel < 7", 0 <= channel < 7),
        (
            'channel >= 7 and kind in ["target", "tuning"]',
            channel >= 7 and kind in {"target", "tuning"},
        ),
        ("channel >= 0 | missing > 0", False),
    ]
    for expression, expected in cases:
        source = DictConfigSource(order=0, source={}, enable_if=expression)
        assert source.is_enabled_for(context) is expected, expression


@pytest.mark.parametrize("context", [None, {}, {"kind": "tuning"}])
def test_missing_context_or_variable_disables_source(context):
    source = DictConfigSource(order=0, source={}, enable_if="channel >= 7")
    assert source.is_enabled_for(context) is False


def test_disabled_source_does_not_evaluate_invalid_condition():
    source = DictConfigSource(order=0, source={}, enabled=False, enable_if="channel >")
    assert source.is_enabled_for({"channel": 8}) is False


def test_malformed_condition_propagates_query_error():
    source = DictConfigSource(order=0, source={}, enable_if="channel >")
    with pytest.raises(SyntaxError):
        source.is_enabled_for({"channel": 8})


@pytest.mark.spec("configuration-sources-and-precedence")
def test_membership_and_precedence_control_merged_settings():
    sources = ConfigSourceList(
        data=[
            DictConfigSource(order=0, source={"snr_min": 5}),
            DictConfigSource(
                order=1,
                source={"snr_min": 3},
                enable_if='channel >= 7 & kind in ["target", "tuning"]',
            ),
        ]
    )
    assert sources.load({"channel": 8, "kind": "tuning"}) == {"snr_min": 3}
    assert sources.load({"channel": 0, "kind": "tuning"}) == {"snr_min": 5}
    assert sources.load({"channel": 8, "kind": "survey"}) == {"snr_min": 5}
