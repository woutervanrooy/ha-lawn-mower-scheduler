from datetime import UTC, datetime, timedelta

import pytest
from pytest_homeassistant.common import async_fire_time_changed

from homeassistant.core import HomeAssistant


async def test_dormant_lawn_in_auto_still_has_a_weekly_interval(
    hass: HomeAssistant, setup_package
) -> None:
    await setup_package()
    hass.states.async_set("sensor.lawn_growth_index_72h", "0")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.lawn_days_between_mows").state == "7"


@pytest.mark.parametrize(
    ("mode", "growth", "expected"),
    [
        ("Auto", "unavailable", "7"),
        ("Auto", "19.9", "7"),
        ("Auto", "20", "4"),
        ("Auto", "39.9", "4"),
        ("Auto", "40", "3"),
        ("Auto", "60", "2"),
        ("Auto", "80", "1"),
        ("Always daily", "0", "1"),
        ("Disabled", "100", "0"),
    ],
)
async def test_growth_mapping_and_modes(
    hass: HomeAssistant, setup_package, mode: str, growth: str, expected: str
) -> None:
    await setup_package()
    hass.states.async_set("sensor.lawn_growth_index_72h", growth)
    await hass.services.async_call(
        "input_select",
        "select_option",
        {"entity_id": "input_select.lawn_mower_mode", "option": mode},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.lawn_days_between_mows").state == expected


async def test_growth_average_keeps_more_than_twenty_samples_over_72_hours(
    hass: HomeAssistant, setup_package, freezer
) -> None:
    freezer.move_to(datetime(2026, 11, 6, 12, tzinfo=UTC))
    await setup_package()

    for value in range(22):
        hass.states.async_set("sensor.lawn_growth_index", str(value))
        await hass.async_block_till_done()
        freezer.tick(timedelta(hours=3))
        async_fire_time_changed(hass, datetime.now(UTC))
        await hass.async_block_till_done()

    assert hass.states.get("sensor.lawn_growth_index_72h").state == "10.5"

    freezer.tick(timedelta(hours=10, seconds=1))
    async_fire_time_changed(hass, datetime.now(UTC))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.lawn_growth_index_72h").state == "11.5"
    await hass.data["sensor"].async_remove_entity("sensor.lawn_growth_index_72h")
