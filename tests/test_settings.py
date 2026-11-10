from datetime import UTC, datetime, timedelta

import pytest

from homeassistant.core import HomeAssistant


@pytest.mark.parametrize(
    ("settings", "readings", "expected"),
    [
        ({"optimum_temperature": 30}, {"sensor.air": "30"}, "100.0"),
        ({"temperature_width": 11}, {"sensor.air": "9"}, "60.7"),
        (
            {"light_saturation": 2, "irradiation_sensor": "sensor.light"},
            {"sensor.light": "2"},
            "100.0",
        ),
        (
            {
                "dry_soil_percent": 10,
                "moist_soil_percent": 20,
                "soil_moisture_sensor": "sensor.soil",
            },
            {"sensor.soil": "15"},
            "65.0",
        ),
        (
            {"drought_deficit": 40, "bucket_sensor": "sensor.bucket", "bucket_attribute": ""},
            {"sensor.bucket": "-10"},
            "75.0",
        ),
        (
            {"minimum_moisture_factor": 0.1, "soil_moisture_sensor": "sensor.soil"},
            {"sensor.soil": "15"},
            "10.0",
        ),
    ],
)
async def test_growth_settings_change_the_published_index(
    hass: HomeAssistant, setup_conditions, settings: dict, readings: dict, expected: str
) -> None:
    hass.states.async_set("sensor.air", "20")
    for entity, reading in readings.items():
        hass.states.async_set(entity, reading)
    await setup_conditions({"temperature_sensor": "sensor.air", **settings},
    )
    assert hass.states.get("sensor.lawn_growth_index").state == expected


@pytest.mark.parametrize(
    ("settings", "rain", "humidity", "expected"),
    [
        ({"rain_threshold": 1}, "0.5", "50", "off"),
        ({"dew_point_margin": 2}, "0", "90", "on"),
    ],
)
async def test_wetting_thresholds_are_editable(
    hass: HomeAssistant,
    setup_conditions,
    settings: dict,
    rain: str,
    humidity: str,
    expected: str,
) -> None:
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.rain", rain)
    hass.states.async_set("sensor.humidity", humidity)
    await setup_conditions({
            "rain_sensor": "sensor.rain",
            "humidity_sensor": "sensor.humidity",
            "drying_hours": 0,
            **settings,
        },
    )
    assert hass.states.get("binary_sensor.lawn_wet").state == expected


async def test_air_frost_threshold_is_editable(
    hass: HomeAssistant, setup_conditions
) -> None:
    hass.states.async_set("sensor.air", "10")
    await setup_conditions({"temperature_sensor": "sensor.air", "air_frost_temperature": 1, "thaw_hours": 0},
    )
    hass.states.async_set("sensor.air", "2")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.lawn_frozen").state == "off"


async def test_air_thaw_threshold_is_editable(
    hass: HomeAssistant, setup_conditions
) -> None:
    hass.states.async_set("sensor.air", "3")
    await setup_conditions({"temperature_sensor": "sensor.air", "air_thaw_temperature": 7, "thaw_hours": 0},
    )
    hass.states.async_set("sensor.air", "6")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.lawn_frozen").state == "on"


async def test_custom_completion_types_and_area_threshold_are_used(
    hass: HomeAssistant, setup_scheduler, mower_starts
) -> None:
    hass.states.async_set("event.job_finished", "2000-01-01T00:00:00+00:00")
    hass.states.async_set("sensor.area", "100")
    await setup_scheduler(
        {
            "job_finished_event": "event.job_finished",
            "finished_event_types": ["done"],
            "mowed_area_sensor": "sensor.area",
            "full_mow_area": 150,
        }
    )
    before = hass.states.get("input_datetime.lawn_mower_last_completed").state
    hass.states.async_set(
        "event.job_finished", datetime.now(UTC).isoformat(), {"event_type": "done"}
    )
    await hass.async_block_till_done()
    assert hass.states.get("input_datetime.lawn_mower_last_completed").state == before

    hass.states.async_set("sensor.area", "150")
    hass.states.async_set(
        "event.job_finished",
        (datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
        {"event_type": "done"},
    )
    await hass.async_block_till_done()
    assert hass.states.get("input_datetime.lawn_mower_last_completed").state != before


async def test_start_gap_setting_can_be_lowered(
    hass: HomeAssistant, setup_scheduler, mower_starts
) -> None:
    await setup_scheduler({"min_hours_between_starts": 1})
    await hass.services.async_call(
        "input_datetime",
        "set_datetime",
        {
            "entity_id": "input_datetime.lawn_mower_last_started",
            "timestamp": (datetime.now(UTC) - timedelta(hours=2)).timestamp(),
        },
        blocking=True,
    )
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()
    assert len(mower_starts) == 1


async def test_daily_interval_counts_local_nights_not_24_hour_periods(
    hass: HomeAssistant, setup_scheduler, mower_starts, freezer
) -> None:
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    freezer.move_to(datetime(2026, 11, 6, 0, 30, tzinfo=UTC))
    await setup_scheduler()
    await hass.services.async_call(
        "input_select",
        "select_option",
        {"entity_id": "input_select.lawn_mower_mode", "option": "Always daily"},
        blocking=True,
    )
    for entity, value in (
        ("input_datetime.lawn_mower_last_started", datetime(2026, 11, 5, 18, 30, tzinfo=UTC)),
        ("input_datetime.lawn_mower_last_completed", datetime(2026, 11, 5, 22, 55, tzinfo=UTC)),
    ):
        await hass.services.async_call(
            "input_datetime",
            "set_datetime",
            {"entity_id": entity, "timestamp": value.timestamp()},
            blocking=True,
        )
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()
    assert len(mower_starts) == 1
