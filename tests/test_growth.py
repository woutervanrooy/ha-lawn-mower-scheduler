import pytest
from pytest_homeassistant.common import async_mock_service

from homeassistant.core import HomeAssistant


async def test_optimal_temperature_without_optional_sensors_has_full_growth(
    hass: HomeAssistant, setup_conditions
) -> None:
    hass.states.async_set("sensor.air_temperature", "20")

    await setup_conditions({"temperature_sensor": "sensor.air_temperature"},
    )

    assert hass.states.get("sensor.lawn_growth_index").state == "100.0"


async def test_half_daily_light_halves_growth(
    hass: HomeAssistant, setup_conditions
) -> None:
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.irradiation_24h", "2")

    await setup_conditions({
            "temperature_sensor": "sensor.air_temperature",
            "irradiation_sensor": "sensor.irradiation_24h",
        },
    )

    assert hass.states.get("sensor.lawn_growth_index").state == "50.0"


@pytest.mark.parametrize(
    ("temperature", "expected"),
    [("9", "13.5"), ("31", "13.5"), ("unavailable", "unavailable")],
)
async def test_temperature_curve_and_unavailable_air(
    hass: HomeAssistant, setup_conditions, temperature: str, expected: str
) -> None:
    hass.states.async_set("sensor.air_temperature", temperature)
    await setup_conditions({"temperature_sensor": "sensor.air_temperature"},
    )
    assert hass.states.get("sensor.lawn_growth_index").state == expected


@pytest.mark.parametrize(
    ("input_name", "reading", "expected"),
    [
        ("irradiation_sensor", "0", "0.0"),
        ("irradiation_sensor", "8", "100.0"),
        ("irradiation_sensor", "unavailable", "100.0"),
        ("soil_moisture_sensor", "10", "30.0"),
        ("soil_moisture_sensor", "22.5", "65.0"),
        ("soil_moisture_sensor", "40", "100.0"),
        ("soil_moisture_sensor", "unavailable", "100.0"),
        ("bucket_sensor", "-20", "30.0"),
        ("bucket_sensor", "5", "100.0"),
        ("bucket_sensor", "unavailable", "100.0"),
    ],
)
async def test_individual_optional_growth_inputs(
    hass: HomeAssistant,
    setup_conditions,
    input_name: str,
    reading: str,
    expected: str,
) -> None:
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.optional_reading", reading)
    await setup_conditions({
            "temperature_sensor": "sensor.air_temperature",
            input_name: "sensor.optional_reading",
        },
    )
    assert hass.states.get("sensor.lawn_growth_index").state == expected


async def test_growth_uses_bucket_state_and_updates_when_it_changes(
    hass: HomeAssistant, setup_conditions
) -> None:
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.bucket", "0", {"bucket": 0})
    await setup_conditions({
            "temperature_sensor": "sensor.air_temperature",
            "bucket_sensor": "sensor.bucket",
        },
    )
    assert hass.states.get("sensor.lawn_growth_index").state == "100.0"

    hass.states.async_set("sensor.bucket", "-10", {"bucket": 0})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.lawn_growth_index").state == "50.0"

    hass.states.async_set("sensor.bucket", "-10", {"bucket": -20})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.lawn_growth_index").state == "50.0"


async def test_invalid_soil_calibration_is_reported(
    hass: HomeAssistant, setup_conditions
) -> None:
    notifications = async_mock_service(hass, "persistent_notification", "create")
    hass.states.async_set("sensor.air_temperature", "20")
    await setup_conditions({
            "temperature_sensor": "sensor.air_temperature",
            "dry_soil_percent": 30,
            "moist_soil_percent": 15,
        },
    )
    assert hass.states.get("sensor.lawn_growth_index").state == "unavailable"
    assert [call.data for call in notifications] == [
        {
            "notification_id": "lawn_mower_scheduler_growth_settings",
            "title": "Lawn mower conditions settings",
            "message": "Dry soil percentage must be below moist soil percentage.",
        }
    ]


async def test_drier_of_soil_moisture_and_bucket_limits_growth(
    hass: HomeAssistant, setup_conditions
) -> None:
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.soil_moisture", "22.5")
    hass.states.async_set("sensor.irrigation_bucket", "-10")

    await setup_conditions({
            "temperature_sensor": "sensor.air_temperature",
            "soil_moisture_sensor": "sensor.soil_moisture",
            "bucket_sensor": "sensor.irrigation_bucket",
        },
    )

    assert hass.states.get("sensor.lawn_growth_index").state == "50.0"
