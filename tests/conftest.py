import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from pathlib import Path
import shutil

import pytest
from pytest_homeassistant.common import async_mock_service

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml_dict

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def settle_event_triggers(hass: HomeAssistant) -> None:
    # Event triggers dispatch through loop.call_soon, which async_block_till_done
    # does not track once the publishing automation task has finished.
    block_till_done = hass.async_block_till_done

    async def settle(*args, **kwargs) -> None:
        for _ in range(3):
            await block_till_done(*args, **kwargs)
            await asyncio.sleep(0)
        await block_till_done(*args, **kwargs)

    hass.async_block_till_done = settle


@pytest.fixture(autouse=True)
async def remove_automations(hass: HomeAssistant) -> AsyncGenerator[None]:
    yield
    if component := hass.data.get("automation"):
        for entity in list(component.entities):
            await component.async_remove_entity(entity.entity_id)
    # The statistics sensor schedules purge timers that outlive the test.
    if (sensors := hass.data.get("sensor")) and sensors.get_entity(
        "sensor.lawn_growth_index_72h"
    ):
        await sensors.async_remove_entity("sensor.lawn_growth_index_72h")


@pytest.fixture
def hass_config_dir(hass_tmp_config_dir: str) -> str:
    for source in (ROOT / "blueprints").rglob("*.yaml"):
        destination = Path(hass_tmp_config_dir) / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return hass_tmp_config_dir


@pytest.fixture
def setup_conditions(
    hass: HomeAssistant, setup_package
) -> Callable[[dict[str, object]], Awaitable[None]]:
    async def setup(inputs: dict[str, object]) -> None:
        await setup_package()
        if not hass.services.has_service("persistent_notification", "create"):
            assert await async_setup_component(hass, "persistent_notification", {})
        assert await async_setup_component(
            hass,
            "automation",
            {
                "automation": [
                    {
                        "id": "lawn_conditions_test",
                        "alias": "Lawn conditions test",
                        "use_blueprint": {
                            "path": "lawn_mower_scheduler/lawn_conditions.yaml",
                            "input": {
                                "temperature_sensor": "sensor.air_temperature",
                                "rain_sensor": "sensor.rain_last_hour",
                                "humidity_sensor": "sensor.humidity",
                                **inputs,
                            },
                        },
                    }
                ]
            },
        )
        await hass.async_block_till_done()
        # Saving an automation in the UI reloads automations.
        hass.bus.async_fire("automation_reloaded")
        await hass.async_block_till_done()

    return setup


@pytest.fixture
def mower_starts(hass: HomeAssistant) -> list:
    return async_mock_service(hass, "lawn_mower", "start_mowing")


@pytest.fixture
def setup_scheduler(
    hass: HomeAssistant, setup_package
) -> Callable[[dict[str, object] | None], Awaitable[None]]:
    async def setup(inputs: dict[str, object] | None = None) -> None:
        await setup_package()
        hass.states.async_set("lawn_mower.test_mower", "docked")
        hass.states.async_set("schedule.mowing", "off")
        hass.states.async_set("binary_sensor.lawn_wet", "off")
        hass.states.async_set("binary_sensor.lawn_frozen", "off")
        for entity in (
            "input_datetime.lawn_mower_last_started",
            "input_datetime.lawn_mower_last_completed",
        ):
            await hass.services.async_call(
                "input_datetime",
                "set_datetime",
                {"entity_id": entity, "datetime": "2000-01-01 00:00:00"},
                blocking=True,
            )
        assert await async_setup_component(
            hass,
            "automation",
            {
                "automation": [
                    {
                        "id": "lawn_mower_test_schedule",
                        "alias": "Lawn mower test schedule",
                        "use_blueprint": {
                            "path": "lawn_mower_scheduler/lawn_mower_schedule.yaml",
                            "input": {
                                "mower_entity": "lawn_mower.test_mower",
                                "schedule_entity": "schedule.mowing",
                                **(inputs or {}),
                            },
                        },
                    }
                ]
            },
        )
        await hass.async_block_till_done()
        assert hass.states.get("automation.lawn_mower_test_schedule") is not None

    return setup


@pytest.fixture
def support_package() -> dict:
    return load_yaml_dict(str(ROOT / "packages" / "lawn_mower.yaml"))


@pytest.fixture
def setup_package(
    hass: HomeAssistant, support_package: dict
) -> Callable[[], Awaitable[None]]:
    async def setup() -> None:
        for domain in ("input_select", "input_datetime", "sensor", "template"):
            assert await async_setup_component(hass, domain, support_package)
        await hass.async_block_till_done()

    return setup
