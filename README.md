# Lawn mower scheduler

A portable collection of Home Assistant blueprints for one lawn mower.
No custom integration or dashboard plugins are required.

- A growth index and its rolling 72-hour average choose the mowing interval.
- `Auto` never drops below a weekly target, including during dormancy.
- `Always daily` uses one calendar day between full mows.
- `Disabled` prevents scheduled starts, but manual jobs are still tracked.
- Wet grass and likely frost delay mowing until conditions clear.
- An optional mowed-area check distinguishes a full mow from edge trimming.

Requires **Home Assistant 2024.11.0 or newer** for template blueprints. The
automation is configured in the UI or YAML; template blueprint inputs are
configured in YAML. This folder is independent of the previous lawn-mower setup.

## Files

| File | Purpose |
| --- | --- |
| [Support package](packages/lawn_mower.yaml) | Mode, timestamps, 72-hour average and mowing interval |
| [Growth blueprint](blueprints/template/lawn_mower_scheduler/lawn_growth_index.yaml) | Configurable temperature/light/moisture model |
| [Wet blueprint](blueprints/template/lawn_mower_scheduler/lawn_wet.yaml) | Rain, dew proxy, irrigation and drying delay |
| [Frozen blueprint](blueprints/template/lawn_mower_scheduler/lawn_frozen.yaml) | Air/ground frost hysteresis and thaw delay |
| [Scheduler blueprint](blueprints/automation/lawn_mower_scheduler/lawn_mower_schedule.yaml) | Scheduled starts and manual/job tracking |
| [Template example](examples/templates.yaml) | Generic template instances with editable inputs |
| [Scheduler example](examples/scheduler.yaml) | Generic YAML automation instance |
| [Dashboard card](dashboard_card.yaml) | Built-in entities card with mode and status |

## Install

1. Copy the two `lawn_mower_scheduler` blueprint directories to your Home
   Assistant configuration directory, preserving their domain:

   ```text
   blueprints/automation/lawn_mower_scheduler/lawn_mower_schedule.yaml
   blueprints/template/lawn_mower_scheduler/lawn_growth_index.yaml
   blueprints/template/lawn_mower_scheduler/lawn_wet.yaml
   blueprints/template/lawn_mower_scheduler/lawn_frozen.yaml
   ```

2. Copy the [support package](packages/lawn_mower.yaml) to your configuration's
   `packages` directory. Enable packages if they are not already enabled:

   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```

3. Copy the [template example](examples/templates.yaml) into that packages
   directory as `lawn_conditions.yaml`. Select your air-temperature, last-hour
   rain and humidity sensors. Uncomment any optional inputs you want.
   Alternatively, uncomment the instances in the support package; **do not
   instantiate the same template entities twice**.

4. Create a **Schedule** helper in **Settings -> Devices & services -> Helpers**.
   Set the times when a session may start. Daily windows allow the daily/high
   growth modes to work; sparse windows or persistent bad weather can postpone
   a mow beyond the target interval. Ending a window does not stop a mower
   that has already started.

5. Run **Developer tools -> YAML -> Check configuration** and restart Home
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

6. Create an automation from the scheduler blueprint in
   **Settings -> Automations & scenes -> Blueprints**. Select the mower and
   Schedule helper. Optional event/area/rain-delay inputs are empty by default:
   connect only the entities your mower actually exposes.
   Alternatively, use the [scheduler example](examples/scheduler.yaml) as a
   package. **Create one scheduler instance, not both versions.**

   New date/time helpers default to midnight today, which becomes the initial
   mowing-history baseline. Set the actual last full-mow and last-start dates
   during setup if you know them. Otherwise, the first automatic mow becomes
   eligible after the calculated interval from that baseline. Restored helpers
   retain their actual history; no `initial` value resets them on restart.

7. Set the mode you want. The options are `Auto`, `Always daily`, `Disabled`,
   in that order. The restored mode survives restarts; a new or unrestorable
   selection falls back to `Auto`.

8. Optionally paste the [dashboard card](dashboard_card.yaml) into a manual
   dashboard card.

## Adapting settings

User settings are blueprint inputs, not separate settings helpers:

- Edit template inputs in your `lawn_conditions.yaml` package and reload
  template entities from Developer tools -> YAML, or restart Home Assistant.
- Edit scheduler inputs in its automation settings and save.
- Keep the mode and last-started/completed helpers: they are runtime control
  and history, not tuning parameters.

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
produce an unknown index with a `configuration_error` attribute.

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
| Irrigation activity | Optional on/off entity or open/closed valve |
| Mower rain sensor | Optional on/off binary sensor |
| Rain threshold | 0.5 mm, inclusive |
| Dew humidity threshold | 92%, inclusive |
| Drying time | 3 hours after all wetting conditions clear |

Any selected wetting source turns the sensor on. New rain, irrigation or high
humidity cancels the drying delay; the full delay begins again when every source
clears. Opening/closing an irrigation valve also counts as activity.

Humidity is a deliberately simple dew estimate; shaded grass can dry more
slowly. Increase drying time or lower the humidity threshold for a more cautious
setup. Missing configured weather/activity readings make the guard unavailable,
which does not permit mowing.

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
blocks until a thaw is confirmed. Thaw thresholds must exceed frost thresholds.

Wet/frozen off-delay timers are native template-entity timers, not persistent
wetting/thaw history. A restart or template reload can reset an in-progress
delay. These are approximate lawn guards, not a guarantee that grass is dry or
fully thawed.

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
3. Configure the three template instances and the new scheduler. Do not leave
   the old job/wet/frost tracking automations active.
4. Set the new mode explicitly after restart: old `Paused` or `Minimum weekly`
   selections are no longer valid and can fall back to Auto.
5. Remove orphaned old settings helpers, deployed/enabled switches, dew sensors
   and wet/frost latches after checking for external references.

The existing growth-average and interval dashboard references remain valid.
The new weather entities are `binary_sensor.lawn_wet` and
`binary_sensor.lawn_frozen`.

## Publishing later

The collection has no vendor-specific entity IDs. Put this folder in its own
repository, choose a license, and replace/uncomment the `source_url` placeholders
in each blueprint when a public URL exists. Template and automation blueprints
can then be distributed with the support package and examples. No integration
manifest or marketplace publication is included here.

The default package supports one mower. Additional mowers need distinct mode,
timestamp and template entities and corresponding blueprint inputs.

## Development checks

Tests use the real Home Assistant engine, not a replacement template/automation
interpreter. Development dependencies currently target Home Assistant 2026.11.0
and require Python 3.14.2 or newer on Linux (Windows users can use WSL).
The blueprint and installation schemas were also validated against Home
Assistant 2024.11.3; the behavioral tests run against the pinned development
version.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Physical mower operation and the freshness of a real mower's area/event sensors
still require validation on the user's Home Assistant installation.
