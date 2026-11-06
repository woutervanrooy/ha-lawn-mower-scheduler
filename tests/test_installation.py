from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil

import pytest
from pytest_homeassistant.common import async_fire_time_changed

from homeassistant import config as config_util
from homeassistant.components.blueprint.models import Blueprint
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml_dict

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("domain", "filename", "source_url"),
    [
        (
            "automation",
            "lawn_mower_schedule.yaml",
            "https://github.com/woutervanrooy/ha-lawn-mower-scheduler/blob/main/"
            "blueprints/automation/lawn_mower_scheduler/lawn_mower_schedule.yaml",
        ),
        (
            "template",
            "lawn_growth_index.yaml",
            "https://github.com/woutervanrooy/ha-lawn-mower-scheduler/blob/main/"
            "blueprints/template/lawn_mower_scheduler/lawn_growth_index.yaml",
        ),
        (
            "template",
            "lawn_wet.yaml",
            "https://github.com/woutervanrooy/ha-lawn-mower-scheduler/blob/main/"
            "blueprints/template/lawn_mower_scheduler/lawn_wet.yaml",
        ),
        (
            "template",
            "lawn_frozen.yaml",
            "https://github.com/woutervanrooy/ha-lawn-mower-scheduler/blob/main/"
            "blueprints/template/lawn_mower_scheduler/lawn_frozen.yaml",
        ),
    ],
)
def test_blueprint_metadata_exposes_the_published_source(
    hass_config_dir: str, domain: str, filename: str, source_url: str
) -> None:
    path = Path(hass_config_dir) / "blueprints" / domain / "lawn_mower_scheduler" / filename
    blueprint = Blueprint(load_yaml_dict(str(path)), schema=BLUEPRINT_SCHEMA)

    assert blueprint.domain == domain
    assert blueprint.metadata.get("source_url") == source_url


@pytest.mark.parametrize(
    ("temperature", "growth", "interval"),
    [("20", "100.0", 1), ("9", "13.5", 7)],
)
@pytest.mark.parametrize("import_scheduler", [False, True], ids=["manual", "imported"])
async def test_generic_examples_load_and_use_the_first_installation_baseline(
    hass: HomeAssistant,
    hass_config_dir: str,
    mower_starts,
    freezer,
    temperature: str,
    growth: str,
    interval: int,
    import_scheduler: bool,
) -> None:
    freezer.move_to(datetime(2026, 11, 6, 12, tzinfo=UTC))
    packages = Path(hass_config_dir) / "packages"
    packages.mkdir()
    for source, filename in (
        (ROOT / "packages" / "lawn_mower.yaml", "lawn_mower.yaml"),
        (ROOT / "examples" / "templates.yaml", "lawn_conditions.yaml"),
        (ROOT / "examples" / "scheduler.yaml", "lawn_schedule.yaml"),
    ):
        shutil.copyfile(source, packages / filename)
    if import_scheduler:
        automation_dir = Path(hass_config_dir) / "blueprints" / "automation"
        imported_dir = automation_dir / "woutervanrooy"
        imported_dir.mkdir()
        (automation_dir / "lawn_mower_scheduler" / "lawn_mower_schedule.yaml").rename(
            imported_dir / "lawn_mower_schedule.yaml"
        )
    (Path(hass_config_dir) / "configuration.yaml").write_text(
        "homeassistant:\n  packages: !include_dir_named packages\n",
        encoding="utf-8",
    )
    hass.states.async_set("sensor.outdoor_temperature", temperature)
    hass.states.async_set("sensor.rain_last_hour", "0")
    hass.states.async_set("sensor.outdoor_humidity", "50")
    hass.states.async_set("lawn_mower.garden", "docked")
    hass.states.async_set("schedule.mowing", "off")

    config = await config_util.async_hass_config_yaml(hass)
    if import_scheduler:
        config["automation"][0]["use_blueprint"]["path"] = (
            "woutervanrooy/lawn_mower_schedule.yaml"
        )
    for domain in ("input_select", "input_datetime", "sensor", "template", "automation"):
        assert await async_setup_component(hass, domain, config)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.lawn_growth_index").state == growth
    assert hass.states.get("sensor.lawn_growth_index_72h").state == growth
    assert hass.states.get("sensor.lawn_days_between_mows").state == str(interval)

    freezer.tick(timedelta(hours=3))
    async_fire_time_changed(hass, datetime.now(UTC))
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.lawn_wet").state == "off"
    assert hass.states.get("binary_sensor.lawn_frozen").state == "off"

    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()
    assert not mower_starts
    hass.states.async_set("schedule.mowing", "off")
    freezer.tick(timedelta(days=interval))
    async_fire_time_changed(hass, datetime.now(UTC))
    await hass.async_block_till_done()
    hass.states.async_set("schedule.mowing", "on")
    await hass.async_block_till_done()
    assert len(mower_starts) == 1, tuple(
        hass.states.get(entity).state
        for entity in (
            "input_datetime.lawn_mower_last_started",
            "input_datetime.lawn_mower_last_completed",
            "sensor.lawn_days_between_mows",
        )
    )
    await hass.data["sensor"].async_remove_entity("sensor.lawn_growth_index_72h")
