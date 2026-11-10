from datetime import UTC, datetime, timedelta

import pytest
from pytest_homeassistant.common import async_fire_time_changed

from homeassistant.core import HomeAssistant


async def test_half_millimeter_of_rain_makes_the_lawn_wet(
    hass: HomeAssistant, setup_conditions
) -> None:
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.rain_last_hour", "0.5")
    hass.states.async_set("sensor.humidity", "50")
    await setup_conditions({
            "rain_sensor": "sensor.rain_last_hour",
            "humidity_sensor": "sensor.humidity",
        },
    )
    assert hass.states.get("binary_sensor.lawn_wet").state == "on"


@pytest.mark.parametrize(
    ("rain", "humidity", "expected"),
    [
        ("0.49", "90", "off"),
        ("0", "95", "on"),
        ("unavailable", "50", "unavailable"),
    ],
)
async def test_wetting_boundaries_and_unavailable_readings(
    hass: HomeAssistant,
    setup_conditions,
    rain: str,
    humidity: str,
    expected: str,
) -> None:
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.rain_last_hour", rain)
    hass.states.async_set("sensor.humidity", humidity)
    await setup_conditions({
            "rain_sensor": "sensor.rain_last_hour",
            "humidity_sensor": "sensor.humidity",
            "drying_hours": 0,
        },
    )
    assert hass.states.get("binary_sensor.lawn_wet").state == expected


@pytest.mark.parametrize(
    ("input_name", "entity", "reading"),
    [
        ("irrigation_entity", "switch.irrigation", "on"),
        ("irrigation_entity", "valve.irrigation", "open"),
        ("mower_rain_sensor", "binary_sensor.mower_rain", "on"),
    ],
)
async def test_optional_wetting_sources(
    hass: HomeAssistant,
    setup_conditions,
    input_name: str,
    entity: str,
    reading: str,
) -> None:
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.rain_last_hour", "0")
    hass.states.async_set("sensor.humidity", "50")
    hass.states.async_set(entity, reading)
    await setup_conditions({
            "rain_sensor": "sensor.rain_last_hour",
            "humidity_sensor": "sensor.humidity",
            input_name: entity,
            "drying_hours": 0,
        },
    )
    assert hass.states.get("binary_sensor.lawn_wet").state == "on"


async def test_drying_requires_three_clear_hours_after_the_last_wetting(
    hass: HomeAssistant, setup_conditions, freezer
) -> None:
    freezer.move_to(datetime(2026, 11, 6, 12, tzinfo=UTC))
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.rain_last_hour", "0.5")
    hass.states.async_set("sensor.humidity", "50")
    await setup_conditions({
            "rain_sensor": "sensor.rain_last_hour",
            "humidity_sensor": "sensor.humidity",
        },
    )

    hass.states.async_set("sensor.rain_last_hour", "0")
    await hass.async_block_till_done()
    freezer.tick(timedelta(hours=2))
    async_fire_time_changed(hass, datetime.now(UTC))
    await hass.async_block_till_done()
    hass.states.async_set("sensor.humidity", "96")
    await hass.async_block_till_done()
    hass.states.async_set("sensor.humidity", "50")
    await hass.async_block_till_done()

    freezer.tick(timedelta(hours=2, minutes=59))
    async_fire_time_changed(hass, datetime.now(UTC))
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.lawn_wet").state == "on"

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass, datetime.now(UTC))
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.lawn_wet").state == "off"


@pytest.mark.parametrize(
    ("ground", "humidity", "expected"),
    [
        (None, "95", "on"),
        ("25", "95", "off"),
        ("18", "95", "on"),
        ("unavailable", "95", "unavailable"),
    ],
)
async def test_dew_point_uses_grass_temperature_when_configured(
    hass: HomeAssistant,
    setup_conditions,
    ground: str | None,
    humidity: str,
    expected: str,
) -> None:
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.rain_last_hour", "0")
    hass.states.async_set("sensor.humidity", humidity)
    inputs = {"drying_hours": 0}
    if ground is not None:
        hass.states.async_set("sensor.ground_temperature", ground)
        inputs["ground_temperature_sensor"] = "sensor.ground_temperature"

    await setup_conditions(inputs)

    assert hass.states.get("binary_sensor.lawn_wet").state == expected


async def test_dew_point_ignores_zero_humidity(
    hass: HomeAssistant, setup_conditions
) -> None:
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.rain_last_hour", "0")
    hass.states.async_set("sensor.humidity", "0")
    await setup_conditions({"drying_hours": 0})

    assert hass.states.get("binary_sensor.lawn_wet").state == "off"


async def test_legacy_dew_humidity_input_is_ignored(
    hass: HomeAssistant, setup_conditions
) -> None:
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.rain_last_hour", "0")
    hass.states.async_set("sensor.humidity", "95")
    await setup_conditions({"dew_humidity": 50, "dew_point_margin": 0, "drying_hours": 0})

    assert hass.states.get("binary_sensor.lawn_wet").state == "off"


@pytest.mark.parametrize(
    ("air", "ground"),
    [("3", None), ("10", "1")],
)
async def test_either_temperature_source_can_indicate_frozen_lawn(
    hass: HomeAssistant, setup_conditions, air: str, ground: str | None
) -> None:
    hass.states.async_set("sensor.air_temperature", air)
    inputs = {"temperature_sensor": "sensor.air_temperature"}
    if ground is not None:
        hass.states.async_set("sensor.ground_temperature", ground)
        inputs["ground_temperature_sensor"] = "sensor.ground_temperature"
    await setup_conditions(inputs)
    assert hass.states.get("binary_sensor.lawn_frozen").state == "on"


@pytest.mark.parametrize("with_ground", [False, True])
async def test_frost_hysteresis_and_two_hour_thaw_delay(
    hass: HomeAssistant, setup_conditions, freezer, with_ground: bool
) -> None:
    freezer.move_to(datetime(2026, 11, 6, 12, tzinfo=UTC))
    hass.states.async_set("sensor.air_temperature", "3")
    inputs = {"temperature_sensor": "sensor.air_temperature"}
    if with_ground:
        hass.states.async_set("sensor.ground_temperature", "1")
        inputs["ground_temperature_sensor"] = "sensor.ground_temperature"
    await setup_conditions(inputs)

    hass.states.async_set("sensor.air_temperature", "4")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.lawn_frozen").state == "on"

    hass.states.async_set("sensor.air_temperature", "5")
    if with_ground:
        hass.states.async_set("sensor.ground_temperature", "2")
    await hass.async_block_till_done()
    if with_ground:
        freezer.tick(timedelta(hours=3))
        async_fire_time_changed(hass, datetime.now(UTC))
        await hass.async_block_till_done()
        assert hass.states.get("binary_sensor.lawn_frozen").state == "on"
        hass.states.async_set("sensor.ground_temperature", "3")
        await hass.async_block_till_done()

    freezer.tick(timedelta(hours=1, minutes=59))
    async_fire_time_changed(hass, datetime.now(UTC))
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.lawn_frozen").state == "on"

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass, datetime.now(UTC))
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.lawn_frozen").state == "off"

    hass.states.async_set("sensor.air_temperature", "4")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.lawn_frozen").state == "off"
    hass.states.async_set("sensor.air_temperature", "3")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.lawn_frozen").state == "on"


async def test_configured_ground_sensor_unavailable_is_not_a_thaw(
    hass: HomeAssistant, setup_conditions
) -> None:
    hass.states.async_set("sensor.air_temperature", "10")
    hass.states.async_set("sensor.ground_temperature", "unavailable")
    await setup_conditions({
            "temperature_sensor": "sensor.air_temperature",
            "ground_temperature_sensor": "sensor.ground_temperature",
            "thaw_hours": 0,
        },
    )
    assert hass.states.get("binary_sensor.lawn_frozen").state == "unavailable"
