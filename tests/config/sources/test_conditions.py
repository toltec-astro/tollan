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


@pytest.mark.parametrize("roach", range(13))
@pytest.mark.parametrize("file_suffix", ["vnasweep", "targsweep", "tune"])
def test_recipe_condition_truth_table(roach, file_suffix):
    context = {"roach": roach, "file_suffix": file_suffix}
    # Includes the conditions in taco_recipes/scripts/kids/
    # tolteca_config.d/10_kids_override.yaml, plus language combinations.
    cases = [
        (None, True),
        ("roach >= 7", roach >= 7),
        (
            'roach >= 7 & file_suffix in ["targsweep", "tune"]',
            roach >= 7 and file_suffix in {"targsweep", "tune"},
        ),
        ('file_suffix == "vnasweep"', file_suffix == "vnasweep"),
        ('file_suffix == "targsweep"', file_suffix == "targsweep"),
        ('file_suffix == "tune"', file_suffix == "tune"),
        ('roach >= 7 | file_suffix == "tune"', roach >= 7 or file_suffix == "tune"),
        ('file_suffix not in ["tune"]', file_suffix != "tune"),
        (
            '~(roach < 7 | file_suffix == "vnasweep")',
            not (roach < 7 or file_suffix == "vnasweep"),
        ),
        ("0 <= roach < 7", 0 <= roach < 7),
        (
            'roach >= 7 and file_suffix in ["targsweep", "tune"]',
            roach >= 7 and file_suffix in {"targsweep", "tune"},
        ),
        ("roach >= 0 | missing > 0", False),
    ]
    for expression, expected in cases:
        source = DictConfigSource(order=0, source={}, enable_if=expression)
        assert source.is_enabled_for(context) is expected, expression


@pytest.mark.parametrize("context", [None, {}, {"file_suffix": "tune"}])
def test_missing_context_or_variable_disables_source(context):
    source = DictConfigSource(order=0, source={}, enable_if="roach >= 7")
    assert source.is_enabled_for(context) is False


def test_disabled_source_does_not_evaluate_invalid_condition():
    source = DictConfigSource(order=0, source={}, enabled=False, enable_if="roach >")
    assert source.is_enabled_for({"roach": 8}) is False


def test_malformed_condition_propagates_query_error():
    source = DictConfigSource(order=0, source={}, enable_if="roach >")
    with pytest.raises(SyntaxError):
        source.is_enabled_for({"roach": 8})


def test_membership_and_precedence_control_merged_settings():
    sources = ConfigSourceList(
        data=[
            DictConfigSource(order=0, source={"snr_min": 5}),
            DictConfigSource(
                order=1,
                source={"snr_min": 3},
                enable_if='roach >= 7 & file_suffix in ["targsweep", "tune"]',
            ),
        ]
    )
    assert sources.load({"roach": 8, "file_suffix": "tune"}) == {"snr_min": 3}
    assert sources.load({"roach": 0, "file_suffix": "tune"}) == {"snr_min": 5}
    assert sources.load({"roach": 8, "file_suffix": "vnasweep"}) == {"snr_min": 5}
