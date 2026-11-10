from datetime import UTC, datetime, timedelta

from pytest_homeassistant.common import (
    async_capture_events,
    async_fire_time_changed,
    async_mock_service,
    mock_restore_cache_with_extra_data,
)

from homeassistant.core import HomeAssistant, State


async def _tick(hass: HomeAssistant, freezer, delta: timedelta) -> None:
    freezer.tick(delta)
    async_fire_time_changed(hass, datetime.now(UTC))
    await hass.async_block_till_done()


async def test_pending_drying_deadline_survives_a_restart(
    hass: HomeAssistant, setup_conditions, freezer
) -> None:
    freezer.move_to(datetime(2026, 11, 6, 12, tzinfo=UTC))
    dry_at = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("binary_sensor.lawn_wet", "on", {"wetting": False, "dry_at": dry_at}),
                {"auto_off_time": None},
            )
        ],
    )
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.rain_last_hour", "0")
    hass.states.async_set("sensor.humidity", "50")
    await setup_conditions({})

    wet = hass.states.get("binary_sensor.lawn_wet")
    assert wet.state == "on"
    assert wet.attributes["dry_at"] == dry_at

    await _tick(hass, freezer, timedelta(minutes=61))
    assert hass.states.get("binary_sensor.lawn_wet").state == "off"


async def test_unchanged_growth_is_not_published_again(
    hass: HomeAssistant, setup_conditions
) -> None:
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.rain_last_hour", "0")
    hass.states.async_set("sensor.humidity", "50")
    await setup_conditions({})
    assert hass.states.get("sensor.lawn_growth_index").state == "100.0"

    growth_events = async_capture_events(hass, "lawn_mower_scheduler_growth")
    hass.states.async_set("sensor.humidity", "55")
    await hass.async_block_till_done()
    assert growth_events == []

    hass.states.async_set("sensor.air_temperature", "9")
    await hass.async_block_till_done()
    assert len(growth_events) == 1
    assert hass.states.get("sensor.lawn_growth_index").state == "13.5"


async def test_non_wetting_changes_do_not_extend_the_drying_delay(
    hass: HomeAssistant, setup_conditions, freezer
) -> None:
    freezer.move_to(datetime(2026, 11, 6, 12, tzinfo=UTC))
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.rain_last_hour", "1")
    hass.states.async_set("sensor.humidity", "50")
    await setup_conditions({})
    assert hass.states.get("binary_sensor.lawn_wet").state == "on"

    hass.states.async_set("sensor.rain_last_hour", "0")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.lawn_wet").state == "on"

    await _tick(hass, freezer, timedelta(hours=2))
    hass.states.async_set("sensor.humidity", "60")
    hass.states.async_set("sensor.air_temperature", "18")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.lawn_wet").state == "on"

    await _tick(hass, freezer, timedelta(minutes=61))
    assert hass.states.get("binary_sensor.lawn_wet").state == "off"


async def test_invalid_frost_settings_block_mowing_and_notify(
    hass: HomeAssistant, setup_conditions
) -> None:
    notifications = async_mock_service(hass, "persistent_notification", "create")
    dismissals = async_mock_service(hass, "persistent_notification", "dismiss")
    hass.states.async_set("sensor.air_temperature", "20")
    hass.states.async_set("sensor.rain_last_hour", "0")
    hass.states.async_set("sensor.humidity", "50")
    await setup_conditions({"air_frost_temperature": 5, "air_thaw_temperature": 5})

    frozen = hass.states.get("binary_sensor.lawn_frozen")
    assert frozen.state == "on"
    assert frozen.attributes["configuration_error"] == (
        "Air thaw temperature must exceed air frost temperature."
    )
    assert [call.data["notification_id"] for call in notifications] == [
        "lawn_mower_scheduler_frost_settings"
    ]
    assert [call.data["notification_id"] for call in dismissals] == [
        "lawn_mower_scheduler_growth_settings"
    ]
