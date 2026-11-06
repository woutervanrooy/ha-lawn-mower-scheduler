from datetime import UTC, datetime, timedelta

import pytest
from pytest_homeassistant.common import async_fire_time_changed

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


async def test_due_weekly_mow_starts_when_a_schedule_window_opens(
    hass: HomeAssistant, setup_scheduler, mower_starts
) -> None:
    await setup_scheduler()
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()

    assert len(mower_starts) == 1
    assert mower_starts[0].data["entity_id"] == ["lawn_mower.test_mower"]


@pytest.mark.parametrize("reason", ["mode", "interval"])
async def test_mode_or_interval_change_rechecks_an_open_window(
    hass: HomeAssistant, setup_scheduler, mower_starts, reason: str
) -> None:
    await setup_scheduler()
    if reason == "mode":
        await hass.services.async_call(
            "input_select",
            "select_option",
            {"entity_id": "input_select.lawn_mower_mode", "option": "Disabled"},
            blocking=True,
        )
    else:
        await hass.services.async_call(
            "input_datetime",
            "set_datetime",
            {
                "entity_id": "input_datetime.lawn_mower_last_completed",
                "timestamp": (datetime.now(UTC) - timedelta(days=5)).timestamp(),
            },
            blocking=True,
        )
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()
    assert not mower_starts
    if reason == "mode":
        await hass.services.async_call(
            "input_select",
            "select_option",
            {"entity_id": "input_select.lawn_mower_mode", "option": "Auto"},
            blocking=True,
        )
    else:
        hass.states.async_set("sensor.lawn_growth_index_72h", "20")
    await hass.async_block_till_done()
    assert len(mower_starts) == 1


@pytest.mark.parametrize(
    ("area", "counts"),
    [(None, True), ("90", True), ("80", False), ("unavailable", False)],
)
async def test_docking_fallback_counts_only_area_qualified_mows(
    hass: HomeAssistant, setup_scheduler, mower_starts, area: str | None, counts: bool
) -> None:
    inputs = {}
    if area is not None:
        inputs["mowed_area_sensor"] = "sensor.mowed_area"
        hass.states.async_set("sensor.mowed_area", area)
    await setup_scheduler(inputs)
    before = hass.states.get("input_datetime.lawn_mower_last_completed").state
    hass.states.async_set("lawn_mower.test_mower", "mowing")
    await hass.async_block_till_done()
    hass.states.async_set("lawn_mower.test_mower", "returning")
    await hass.async_block_till_done()
    hass.states.async_set("lawn_mower.test_mower", "docked")
    await hass.async_block_till_done()

    after = hass.states.get("input_datetime.lawn_mower_last_completed").state
    assert (after != before) is counts
    assert not mower_starts


@pytest.mark.parametrize("guard", ["binary_sensor.lawn_wet", "binary_sensor.lawn_frozen"])
async def test_weather_clearing_retries_within_the_open_window(
    hass: HomeAssistant, setup_scheduler, mower_starts, guard: str
) -> None:
    await setup_scheduler()
    hass.states.async_set(guard, "on")
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()
    assert not mower_starts

    hass.states.async_set(guard, "off")
    await hass.async_block_till_done()
    assert len(mower_starts) == 1


async def test_optional_mower_rain_delay_blocks_then_retries(
    hass: HomeAssistant, setup_scheduler, mower_starts
) -> None:
    hass.states.async_set("binary_sensor.mower_rain_delay", "on")
    await setup_scheduler(
        {"rain_delay_sensor": "binary_sensor.mower_rain_delay"}
    )
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()
    assert not mower_starts

    hass.states.async_set("binary_sensor.mower_rain_delay", "off")
    await hass.async_block_till_done()
    assert len(mower_starts) == 1


async def test_full_manual_completion_is_recorded_in_disabled_mode(
    hass: HomeAssistant, setup_scheduler, mower_starts
) -> None:
    hass.states.async_set("event.job_finished", "2000-01-01T00:00:00+00:00")
    hass.states.async_set("sensor.mowed_area", "90")
    await setup_scheduler(
        {
            "job_finished_event": "event.job_finished",
            "mowed_area_sensor": "sensor.mowed_area",
        }
    )
    await hass.services.async_call(
        "input_select",
        "select_option",
        {"entity_id": "input_select.lawn_mower_mode", "option": "Disabled"},
        blocking=True,
    )
    completed = datetime(2026, 11, 6, 12, tzinfo=UTC)
    hass.states.async_set(
        "event.job_finished",
        completed.isoformat(),
        {"event_type": "finished"},
    )
    await hass.async_block_till_done()

    assert hass.states.get(
        "input_datetime.lawn_mower_last_completed"
    ).attributes["timestamp"] == completed.timestamp()
    assert not mower_starts


@pytest.mark.parametrize("use_event", [False, True])
async def test_manual_starts_are_recorded_even_when_scheduling_is_disabled(
    hass: HomeAssistant, setup_scheduler, mower_starts, freezer, use_event: bool
) -> None:
    started = datetime(2026, 11, 6, 12, tzinfo=UTC)
    freezer.move_to(started)
    inputs = {}
    if use_event:
        inputs["job_started_event"] = "event.job_started"
        hass.states.async_set("event.job_started", "2000-01-01T00:00:00+00:00")
    await setup_scheduler(inputs)
    await hass.services.async_call(
        "input_select",
        "select_option",
        {"entity_id": "input_select.lawn_mower_mode", "option": "Disabled"},
        blocking=True,
    )
    if use_event:
        hass.states.async_set("event.job_started", started.isoformat())
    else:
        hass.states.async_set("lawn_mower.test_mower", "mowing")
    await hass.async_block_till_done()

    assert hass.states.get(
        "input_datetime.lawn_mower_last_started"
    ).attributes["timestamp"] == started.timestamp()
    assert not mower_starts


@pytest.mark.parametrize(
    ("mode", "days_since_completion", "starts"),
    [
        ("Auto", 6, False),
        ("Auto", 7, True),
        ("Always daily", 0, False),
        ("Always daily", 1, True),
        ("Disabled", 10, False),
    ],
)
async def test_modes_and_due_calendar_intervals(
    hass: HomeAssistant,
    setup_scheduler,
    mower_starts,
    mode: str,
    days_since_completion: int,
    starts: bool,
) -> None:
    await setup_scheduler()
    await hass.services.async_call(
        "input_select",
        "select_option",
        {"entity_id": "input_select.lawn_mower_mode", "option": mode},
        blocking=True,
    )
    await hass.services.async_call(
        "input_datetime",
        "set_datetime",
        {
            "entity_id": "input_datetime.lawn_mower_last_completed",
            "timestamp": (dt_util.now() - timedelta(days=days_since_completion)).timestamp(),
        },
        blocking=True,
    )
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()
    assert bool(mower_starts) is starts


@pytest.mark.parametrize(
    ("elapsed", "starts"),
    [(timedelta(hours=3, minutes=59), False), (timedelta(hours=4), True)],
)
async def test_minimum_start_gap_is_four_actual_hours(
    hass: HomeAssistant, setup_scheduler, mower_starts, freezer, elapsed: timedelta, starts: bool
) -> None:
    current = datetime(2026, 11, 6, 12, tzinfo=UTC)
    freezer.move_to(current)
    await setup_scheduler()
    await hass.services.async_call(
        "input_datetime",
        "set_datetime",
        {
            "entity_id": "input_datetime.lawn_mower_last_started",
            "timestamp": (current - elapsed).timestamp(),
        },
        blocking=True,
    )
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()
    assert bool(mower_starts) is starts


@pytest.mark.parametrize(
    ("entity", "state"),
    [
        ("lawn_mower.test_mower", "returning"),
        ("lawn_mower.test_mower", "paused"),
        ("binary_sensor.lawn_wet", "unavailable"),
        ("binary_sensor.lawn_frozen", "unknown"),
    ],
)
async def test_not_docked_or_unknown_weather_does_not_allow_a_start(
    hass: HomeAssistant, setup_scheduler, mower_starts, entity: str, state: str
) -> None:
    await setup_scheduler()
    hass.states.async_set(entity, state)
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()
    assert not mower_starts


@pytest.mark.parametrize("cancel", ["schedule", "mode"])
async def test_canceled_window_does_not_start_after_weather_clears(
    hass: HomeAssistant, setup_scheduler, mower_starts, cancel: str
) -> None:
    await setup_scheduler()
    hass.states.async_set("binary_sensor.lawn_wet", "on")
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()
    if cancel == "schedule":
        hass.states.async_set("schedule.mowing", "off")
    else:
        await hass.services.async_call(
            "input_select",
            "select_option",
            {"entity_id": "input_select.lawn_mower_mode", "option": "Disabled"},
            blocking=True,
        )
    hass.states.async_set("binary_sensor.lawn_wet", "off")
    await hass.async_block_till_done()
    assert not mower_starts


async def test_simultaneous_rechecks_only_start_one_session(
    hass: HomeAssistant, setup_scheduler, mower_starts
) -> None:
    await setup_scheduler()
    hass.states.async_set("binary_sensor.lawn_wet", "on")
    hass.states.async_set("binary_sensor.lawn_frozen", "on")
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()

    hass.states.async_set("binary_sensor.lawn_wet", "off")
    hass.states.async_set("binary_sensor.lawn_frozen", "off")
    hass.states.async_set("sensor.lawn_growth_index_72h", "80")
    await hass.async_block_till_done()
    assert len(mower_starts) == 1


@pytest.mark.parametrize(
    ("area", "event_type", "counts"),
    [
        ("90", "finished", True),
        ("89.9", "finished", False),
        ("unavailable", "finished", False),
        ("90", "finished_with_warnings", True),
        ("90", "manually_stopped", False),
        (None, "finished", True),
    ],
)
async def test_completion_events_require_success_and_a_valid_configured_area(
    hass: HomeAssistant,
    setup_scheduler,
    mower_starts,
    area: str | None,
    event_type: str,
    counts: bool,
) -> None:
    hass.states.async_set("event.job_finished", "2000-01-01T00:00:00+00:00")
    inputs = {"job_finished_event": "event.job_finished"}
    if area is not None:
        hass.states.async_set("sensor.mowed_area", area)
        inputs["mowed_area_sensor"] = "sensor.mowed_area"
    await setup_scheduler(inputs)
    before = hass.states.get("input_datetime.lawn_mower_last_completed").state
    hass.states.async_set(
        "event.job_finished",
        datetime.now(UTC).isoformat(),
        {"event_type": event_type},
    )
    await hass.async_block_till_done()
    after = hass.states.get("input_datetime.lawn_mower_last_completed").state
    assert (after != before) is counts
    assert not mower_starts


async def test_consecutive_success_events_with_the_same_type_are_recorded(
    hass: HomeAssistant, setup_scheduler, mower_starts
) -> None:
    hass.states.async_set("event.job_finished", "2000-01-01T00:00:00+00:00")
    await setup_scheduler({"job_finished_event": "event.job_finished"})
    for completed in (
        datetime(2026, 11, 6, 12, tzinfo=UTC),
        datetime(2026, 11, 7, 12, tzinfo=UTC),
    ):
        hass.states.async_set(
            "event.job_finished", completed.isoformat(), {"event_type": "finished"}
        )
        await hass.async_block_till_done()
        assert hass.states.get(
            "input_datetime.lawn_mower_last_completed"
        ).attributes["timestamp"] == completed.timestamp()


async def test_manual_completion_during_weather_wait_makes_the_lawn_not_due(
    hass: HomeAssistant, setup_scheduler, mower_starts
) -> None:
    hass.states.async_set("event.job_finished", "2000-01-01T00:00:00+00:00")
    hass.states.async_set("sensor.mowed_area", "100")
    await setup_scheduler(
        {"job_finished_event": "event.job_finished", "mowed_area_sensor": "sensor.mowed_area"}
    )
    hass.states.async_set("binary_sensor.lawn_wet", "on")
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()
    hass.states.async_set(
        "event.job_finished",
        datetime.now(UTC).isoformat(),
        {"event_type": "finished"},
    )
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.lawn_wet", "off")
    await hass.async_block_till_done()
    assert not mower_starts


async def test_selected_events_disable_both_state_transition_fallbacks(
    hass: HomeAssistant, setup_scheduler, mower_starts
) -> None:
    await setup_scheduler(
        {
            "job_started_event": "event.job_started",
            "job_finished_event": "event.job_finished",
        }
    )
    before = {
        entity: hass.states.get(entity).state
        for entity in (
            "input_datetime.lawn_mower_last_started",
            "input_datetime.lawn_mower_last_completed",
        )
    }
    for state in ("mowing", "returning", "docked"):
        hass.states.async_set("lawn_mower.test_mower", state)
        await hass.async_block_till_done()
    assert {entity: hass.states.get(entity).state for entity in before} == before


@pytest.mark.parametrize(
    "helper",
    ["input_datetime.lawn_mower_last_started", "input_datetime.lawn_mower_last_completed"],
)
async def test_unavailable_required_history_is_not_treated_as_never_mowed(
    hass: HomeAssistant, setup_scheduler, mower_starts, helper: str
) -> None:
    await setup_scheduler()
    hass.states.async_set(helper, "unavailable")
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()
    assert not mower_starts


@pytest.mark.parametrize(("mode", "interval"), [("Auto", 7), ("Always daily", 1)])
async def test_continuously_open_schedule_still_mows_on_the_next_due_day(
    hass: HomeAssistant,
    setup_scheduler,
    mower_starts,
    freezer,
    mode: str,
    interval: int,
) -> None:
    await hass.config.async_set_time_zone("UTC")
    started = datetime(2026, 11, 6, 12, tzinfo=UTC)
    freezer.move_to(started)
    await setup_scheduler()
    await hass.services.async_call(
        "input_select",
        "select_option",
        {"entity_id": "input_select.lawn_mower_mode", "option": mode},
        blocking=True,
    )
    hass.states.async_set("sensor.lawn_growth_index_72h", "0")
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()
    assert len(mower_starts) == 1
    for state in ("mowing", "returning", "docked"):
        hass.states.async_set("lawn_mower.test_mower", state)
        await hass.async_block_till_done()

    freezer.move_to((started + timedelta(days=interval)).replace(hour=0))
    async_fire_time_changed(hass, datetime.now(UTC))
    await hass.async_block_till_done()
    assert len(mower_starts) == 2
