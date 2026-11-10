# Lawn mower scheduler

A portable collection of Home Assistant blueprints for one lawn mower.
The collection uses built-in Home Assistant components and needs no custom
dashboard plugins. Your mower integration must provide a compatible
`lawn_mower` entity.

Source: [woutervanrooy/ha-lawn-mower-scheduler](https://github.com/woutervanrooy/ha-lawn-mower-scheduler).
Shared under the [MIT license](LICENSE).

- A growth index and its rolling 72-hour average choose the mowing interval.
- `Auto` never drops below a weekly target, including during dormancy.
- `Always daily` uses one calendar day between full mows.
- `Disabled` prevents scheduled starts, but manual jobs are still tracked.
- Wet grass and likely frost delay mowing until conditions clear.
- An optional mowed-area check distinguishes a full mow from edge trimming.

Requires **Home Assistant 2024.11.0 or newer**. The collection consists of
**one support package** and **two automation blueprints**. Both blueprints are
imported, configured and updated from the Home Assistant UI.

## Files

| File | Purpose |
| --- | --- |
| [Support package](packages/lawn_mower.yaml) | Mode, timestamps, growth/wet/frozen entities, 72-hour average and mowing interval |
| [Lawn conditions blueprint](blueprints/automation/lawn_mower_scheduler/lawn_conditions.yaml) | Growth model, wet-grass and frost guards with their tuning settings |
| [Scheduler blueprint](blueprints/automation/lawn_mower_scheduler/lawn_mower_schedule.yaml) | Scheduled starts and manual/job tracking |
| [Conditions example](examples/conditions.yaml) | Optional YAML alternative to the conditions automation UI |
| [Scheduler example](examples/scheduler.yaml) | Optional YAML alternative to the scheduler automation UI |
| [Dashboard card](dashboard_card.yaml) | Built-in entities card with mode and status |

The conditions automation calculates the growth index and the wet/frozen
guards, then publishes them to the package's entities. The package holds no
personal settings, so it rarely needs to change.

## Install

### Prerequisites

- Home Assistant **2024.11.0 or newer**.
- A native `lawn_mower` entity supporting `lawn_mower.start_mowing` and reporting
  `docked`, `mowing` and, where available, `returning`.
- Numeric sensors for current air temperature in **Celsius**, rainfall in the
  **last hour in mm** and relative humidity in **percent**. Do not substitute a
  daily rain total or a rain-rate sensor for the last-hour total.
- A **Schedule** helper for permitted start times, created in step 4 below.

Values are **not automatically converted**. Optional ground temperature must
also be in Celsius; bucket values use mm, soil moisture uses percent,
irradiation uses kWh/m2 and mowed area uses m2. See [Adapting settings](#adapting-settings).
The default support package is for one mower.

### Installation steps

1. Copy the [support package](packages/lawn_mower.yaml) to your configuration's
   `packages` directory, for example as `packages/lawn_mower.yaml`. Enable
   packages if they are not already enabled:

   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```

   Merge this into an existing `homeassistant:` section rather than adding a
   duplicate section. This is the only file you copy by hand; the repository's
   tests and development requirements are not needed on your Home Assistant.

2. Run **Developer tools -> YAML -> Check configuration** and restart Home
   Assistant. Verify the entity IDs below. Keep these IDs when using the default
   support package; entity name collisions can create suffixed IDs.

   ```text
   input_select.lawn_mower_mode
   input_datetime.lawn_mower_last_started
   input_datetime.lawn_mower_last_completed
   sensor.lawn_growth_index
   sensor.lawn_growth_index_72h
   sensor.lawn_days_between_mows
   binary_sensor.lawn_wet
   binary_sensor.lawn_frozen
   ```

   The growth, wet and frozen entities stay `unknown` until the conditions
   automation from step 3 publishes their first values. Unknown guards do not
   permit mowing.

3. Import both blueprints:

   - [Import the lawn conditions blueprint](https://my.home-assistant.io/redirect/blueprint_import?blueprint_url=https%3A%2F%2Fgithub.com%2Fwoutervanrooy%2Fha-lawn-mower-scheduler%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Flawn_mower_scheduler%2Flawn_conditions.yaml)
   - [Import the scheduler blueprint](https://my.home-assistant.io/redirect/blueprint_import?blueprint_url=https%3A%2F%2Fgithub.com%2Fwoutervanrooy%2Fha-lawn-mower-scheduler%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Flawn_mower_scheduler%2Flawn_mower_schedule.yaml)

   Or use **Settings -> Automations & scenes -> Blueprints -> Import blueprint**
   with the [source URLs](#source-and-updates). Then create an automation from
   the **Lawn conditions** blueprint. Select your air-temperature, last-hour
   rain and humidity sensors, plus any optional sensors you have. Saving it
   publishes the first values immediately.

4. Create a **Schedule** helper in **Settings -> Devices & services -> Helpers**.
   Set the times when a session may start. Daily windows allow the daily/high
   growth modes to work; sparse windows or persistent bad weather can postpone
   a mow beyond the target interval. Ending a window does not stop a mower
   that has already started.

5. Create an automation from the **scheduler** blueprint. Select the mower and
   Schedule helper. Optional event/area/rain-delay inputs are empty by default:
   connect only the entities your mower actually exposes.

   New date/time helpers default to midnight today, which becomes the initial
   mowing-history baseline. Set the actual last full-mow and last-start dates
   during setup if you know them. Otherwise, the first automatic mow becomes
   eligible after the calculated interval from that baseline. Restored helpers
   retain their actual history; no `initial` value resets them on restart.

6. Set the mode you want. The options are `Auto`, `Always daily`, `Disabled`,
   in that order. The restored mode survives restarts; a new or unrestorable
   selection falls back to `Auto`.

7. Optionally paste the [dashboard card](dashboard_card.yaml) into a manual
   dashboard card.

Create **one** conditions automation and **one** scheduler automation. Two
conditions automations would overwrite each other's values.

### Optional YAML automations

If you prefer YAML over the automation UI, copy the
[conditions example](examples/conditions.yaml) and
[scheduler example](examples/scheduler.yaml) to your `packages` directory
instead of creating the automations in steps 3 and 5. Their `use_blueprint.path`
expects the blueprints in `blueprints/automation/lawn_mower_scheduler/`. If you
imported the blueprints from GitHub, they are normally saved under
`woutervanrooy/`; change the paths to match:

```yaml
use_blueprint:
  path: woutervanrooy/lawn_conditions.yaml  # or woutervanrooy/lawn_mower_schedule.yaml
```

Do not create the same automation in both the UI and YAML.

## Adapting settings

User settings are blueprint inputs, not separate settings helpers:

- Edit sensors and growth/wet/frost tuning in the **Lawn conditions**
  automation's settings and save. Saving recalculates the values immediately.
- Edit scheduler inputs in its automation settings and save.
- Keep the mode and last-started/completed helpers: they are runtime control
  and history, not tuning parameters.

Invalid combinations, such as a thaw threshold that does not exceed its frost
threshold, create a persistent notification explaining the problem.

Use **Celsius**, rainfall/bucket **mm**, soil humidity **percent**, irradiation
**kWh/m2**, and mowed area **m2**. Values are not automatically converted from
other units.

### Growth model

The temperature factor is the existing cool-season Gaussian growth curve:

```text
temperature_factor = exp(-0.5 * ((temperature - optimum) / width)^2)
growth_index = temperature_factor * light_factor * moisture_factor * 100
```

The light factor is irradiation divided by light saturation, clamped to 0..1.
The soil-percent factor rises linearly from the minimum factor at the dry
percentage to 1 at the moist percentage. The bucket factor is
`1 + min(bucket, 0) / drought_deficit`, clamped to the minimum factor..1.
When both moisture sensors are selected, the lower factor wins.

| Input | Default | Effect |
| --- | --- | --- |
| Air temperature | Required | Current temperature; forecast sensors are not needed |
| 24-hour irradiation | Empty | Without a valid reading, light factor is 1 |
| Soil moisture percent | Empty | Optional calibrated moisture reading |
| Bucket sensor | Empty | Optional negative water deficit or Smart Irrigation sensor |
| Bucket attribute | `bucket` | Clear this input to read the sensor state instead |
| Optimum temperature | 20 Celsius | Location of the temperature peak |
| Curve width | 5.5 Celsius | Higher values broaden the growth curve |
| Light saturation | 4 kWh/m2 | More irradiation is needed when raised |
| Dry/moist soil | 15% / 30% | Calibrate to your sensor; dry must be below moist |
| Drought deficit scale | 20 mm | Higher values weaken the bucket's drought effect |
| Minimum moisture factor | 0.3 | Growth retained under very dry conditions |

Missing/invalid optional growth readings contribute a neutral factor; a missing
air temperature makes the Growth Index unavailable. Invalid model settings
also make it unavailable and create a persistent notification.

The support package uses the existing mapping:

| 72-hour average index | Auto interval |
| --- | --- |
| Below 20 | 7 calendar days |
| 20 to below 40 | 4 calendar days |
| 40 to below 60 | 3 calendar days |
| 60 to below 80 | 2 calendar days |
| 80 and above | 1 calendar day |

An unavailable average falls back to 7 days in Auto. The average initially uses
the history available so far; a complete 72-hour window needs three days of
history. The Statistics sensor keeps up to 100,000 samples to avoid the default
20-sample truncation and keeps the last reading during constant conditions.
If you exclude entities from Recorder, keep the Growth Index included to
restore its history after a restart.

### Optional daily irradiation

If your weather integration only supplies irradiance in W/m2:

1. Create an **Integral** helper from the irradiance sensor. Use the left
   Riemann-sum method, `k` prefix, hours, and a maximum sub-interval of 10 minutes.
   The output is cumulative kWh/m2.
2. Create a **Statistics** helper from that integral. Choose `change`, a
   maximum age of 24 hours, and a sample limit large enough for a full day
   (for example 10,000 rather than the default 20).
3. Select that Statistics sensor as the Growth Index's irradiation input.

Irradiation is optional and is **not used to determine drying**.

### Wet grass

| Input | Default |
| --- | --- |
| Rain in the last hour | Required sensor, in mm |
| Relative humidity | Required sensor, in percent |
| Air temperature | Required sensor, in Celsius |
| Ground temperature | Optional grass-level sensor, in Celsius |
| Irrigation activity | Optional on/off entity or open/closed valve |
| Mower rain sensor | Optional on/off binary sensor |
| Rain threshold | 0.5 mm, inclusive |
| Dew point margin | 1 Celsius above the calculated dew point |
| Drying time | 3 hours after all wetting conditions clear |

The dew point is calculated from air temperature and relative humidity using
the Magnus formula. When configured, the ground temperature sensor is used as
the grass-surface temperature; otherwise air temperature is used. Dew counts
when the selected temperature is within the configured margin above the dew
point. A humidity reading of 0% or less does not produce a dew point. Rain,
irrigation activity or the mower rain sensor also independently marks the lawn
wet. Opening/closing an irrigation valve counts as activity.

New rain, dew, irrigation or mower rain cancels the drying delay; the full delay
begins again when every wetting condition clears. Increase the dew point margin
or drying time for a more cautious setup. Missing configured weather/activity
readings, including a selected but unavailable ground temperature sensor, make
the guard unavailable, which does not permit mowing. This is an estimate:
shaded grass may remain wet after its surface warms above the dew point.

### Frozen lawn

| Input | Default |
| --- | --- |
| Air temperature | Required |
| Ground temperature | Optional |
| Air/ground frost thresholds | 3 / 1 Celsius, inclusive |
| Air/ground thaw thresholds | 5 / 3 Celsius, inclusive |
| Thaw time | 2 hours |

Either cold source turns the sensor on. Both selected sources must reach their
thaw thresholds continuously for the thaw delay; without a ground sensor, only
air is checked. In between, the previous state is retained. If there is no
previous clear state and readings are between thresholds, it conservatively
blocks until a thaw is confirmed. Thaw thresholds must exceed frost thresholds;
invalid thresholds keep the guard on, set its `configuration_error` attribute
and create a persistent notification.

Drying and thaw deadlines are stored in the `dry_at` and `thaw_at` attributes
and survive restarts and automation reloads. Unrelated sensor updates do not
extend a pending delay. Without a previous clear state, such as on a fresh
install or after the guard was unavailable, the full delay applies. These are
approximate lawn guards, not a guarantee that grass is dry or fully thawed.

### Scheduling and completion

- The scheduler checks at local midnight, when a window opens, mode becomes
  enabled, the interval changes, or a wet/frozen/rain-delay guard clears. The
  midnight check also supports continuously open windows. Every attempt
  rechecks the current window, mode, docked state, interval and minimum start gap.
- Short queued runs serialize starts while still handling job events promptly.
  There is no long-running weather wait and no extra lock helper.
- Intervals count local **calendar days** since the last full completed mow,
  not exact 24-hour periods. The separate minimum start gap uses actual hours.
- The start gap defaults to **4 hours**, including manual starts and scheduled
  start attempts. Raising it reduces retries after failed jobs.
- An optional mower rain-delay sensor blocks while on or unavailable.
- Missing/unavailable required support timestamps do not allow a start; verify
  the configured helper IDs rather than treating missing history as a new lawn.

Optional job event entities must expose the event timestamp as their state.
For completion events, `event_type` must match the configured success types
(default `finished` and `finished_with_warnings`). Consecutive events of the same
type are detected by their changing timestamps.

When a job-start event is selected, it supplies last-started time; otherwise,
`docked -> mowing` supplies it. When a completion event is selected, it alone
is authoritative; otherwise, `mowing/returning -> docked` supplies completion.
Restored event entities appearing at startup are not treated as new jobs.

The optional mowed-area sensor must still show the current job's area when the
completion signal arrives. With it selected, only a numeric area at or above
**Full lawn area** (default **90 m2**) counts; unavailable readings and edge-only
jobs below the threshold leave last-completed time unchanged. With no area
sensor, every successful event/docking fallback counts, so edge trimming can
reset the interval. State-only fallback cannot distinguish a successful job
from an aborted job that returns to the dock; use completion events if available.

No mower-specific progress threshold is required. Completed jobs are recorded
in every mode, including Disabled, and while weather blocks automatic starts.
Disabling the mode does not stop an already-running mower.

## Migration from the previous setup

1. Disable the old scheduler automation before installing these files.
2. Replace the old package rather than loading both. The mode and timestamp
   helper IDs, Growth Index unique ID and statistics unique ID are retained.
   Preserve existing last-started/completed timestamps.
3. Configure the conditions and scheduler automations. Do not leave the old
   job/wet/frost tracking automations active.
4. Set the new mode explicitly after restart: old `Paused` or `Minimum weekly`
   selections are no longer valid and can fall back to Auto.
5. Remove orphaned old settings helpers, deployed/enabled switches, dew sensors
   and wet/frost latches after checking for external references.

The existing growth-average and interval dashboard references remain valid.
The new weather entities are `binary_sensor.lawn_wet` and
`binary_sensor.lawn_frozen`.

### From the template-blueprint version

Earlier versions of this collection used three template blueprints for growth,
wet and frozen. To upgrade:

1. Note your template inputs, then remove the three `use_blueprint` template
   instances (for example `packages/lawn_conditions.yaml`).
2. Replace the support package with the current version and restart. The
   unique IDs `lawn_growth_index`, `lawn_wet` and `lawn_frozen` are unchanged,
   so entity IDs and growth history are kept.
3. Import the lawn conditions blueprint and create its automation with your
   noted inputs.
4. Delete `blueprints/template/lawn_mower_scheduler/` once nothing uses it.

## Source and updates

Each blueprint's `source_url` points to its public file on `main`:

| Blueprint | Source URL |
| --- | --- |
| Lawn conditions | [lawn_conditions.yaml](https://github.com/woutervanrooy/ha-lawn-mower-scheduler/blob/main/blueprints/automation/lawn_mower_scheduler/lawn_conditions.yaml) |
| Scheduler | [lawn_mower_schedule.yaml](https://github.com/woutervanrooy/ha-lawn-mower-scheduler/blob/main/blueprints/automation/lawn_mower_scheduler/lawn_mower_schedule.yaml) |

These addresses provide source tracking and UI re-import, **not automatic
updates** or release-version pinning. Re-import replaces blueprint definitions
and keeps your configured automation inputs; it does not update the support
package or examples. Changes to a definition, including its defaults, can
still affect mowing behavior. Review changes on `main` before updating.
After re-importing the conditions blueprint, the old `dew_humidity` input is
ignored; configure the new `dew_point_margin` input in the automation instead.

### Safe update checklist

1. Wait for the mower to dock. Note your current mode, then select **Disabled**.
   Disabled does not stop an already-running job.
2. Back up your Home Assistant configuration, blueprint files, customized inputs
   and last-started/completed history. Re-import overwrites local blueprint edits.
3. Review the source changes. Go to **Settings -> Automations & scenes ->
   Blueprints**, open each blueprint's menu and select **Re-import blueprint**.
   Keep the existing installed paths.
4. If the support package changed, merge the changes manually. Preserve helper
   IDs, unique IDs and history.
5. Run **Check configuration**, then reload automations (and template entities
   if the package changed) or restart Home Assistant.
6. Verify entity IDs, history and the availability/plausibility of wet/frozen
   guards, then restore your previous mode. An on guard is valid when the lawn
   is wet or frozen; do not force it off to resume mowing.

See Home Assistant's [blueprint update instructions](https://www.home-assistant.io/docs/automation/using_blueprints/#re-importing-a-blueprint).

## License and sharing

This collection is published under the [MIT license](LICENSE). Share the
repository and blueprint source links together with the support-package
installation instructions. No integration manifest or marketplace package is
required for this blueprint collection.

The default package supports one mower. Additional mowers need distinct mode,
timestamp and template entities and corresponding blueprint inputs.

## Development checks

Tests use the real Home Assistant engine, not a replacement template/automation
interpreter. Development dependencies currently target Home Assistant 2026.11.0
and require Python 3.14.2 or newer on Linux (Windows users can use WSL).
The full behavioral suite, including the copied-blueprint and imported-blueprint
installation layouts, also passed on Home Assistant 2024.11.0 using the
matching `pytest-homeassistant-custom-component` release. Publishing checks
are covered by the focused `tests/test_installation.py` tests.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Physical mower operation and the freshness of a real mower's area/event sensors
still require validation on the user's Home Assistant installation.
