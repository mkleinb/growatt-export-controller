# Growatt Export Controller Project

## Purpose

Home Assistant custom integration for controlling Growatt export limits via the Growatt cloud.

The integration currently supports:
- browser-compatible login flow
- export limit control via `tcpSet.do`
- meter enable / disable
- export percentage control

## Core principle

The integration must remain:
- reliable
- testable
- HACS-ready
- easy to maintain
- understandable for future contributors

## Current state

Working foundation:
- Growatt API integration works
- Home Assistant config flow exists
- Switch entity exists
- Number entity exists
- Sensor entity exists
- GitHub repository is created
- VSCode workflow is in place
- price sensor discovery is started

## Planned architecture

### Layers

1. **API layer**
   - login
   - session handling
   - Growatt requests
   - retries
   - response validation

2. **Decision layer**
   - evaluate current price
   - apply threshold logic
   - apply hysteresis
   - decide whether to enable or disable export control

3. **Automation layer**
   - select price source
   - monitor sensor changes
   - trigger Growatt actions when needed

4. **Presentation layer**
   - switch
   - number
   - sensor
   - diagnostics
   - options flow

## Price automation rules

The user can configure:
- a price source sensor
- an activation threshold
- a recovery threshold
- whether tax is included or excluded
- the meter state when triggered
- the export percentage when triggered
- the meter state when normal
- the export percentage when normal

Default user behavior:
- when electricity price is low or negative:
  - Meter Enable = on
  - Export Percentage = 100%
- when electricity price returns above threshold:
  - Meter Enable = off
  - Export Percentage = 100%

## Sensor discovery rules

The integration should automatically detect likely price sensors.

Preferred sensors:
- numeric sensors
- sensors with monetary device class
- sensors containing price-related keywords
- sensors with units like €/kWh or EUR/kWh
- sensors from known providers such as Zonneplan, Tibber, Nord Pool, ANWB, EasyEnergy

The UI should show only likely price sensors, so the user does not need to type entity IDs manually.

## Quality rules

All code changes should follow:
- small commits
- clear commit messages
- linting with Ruff
- formatting with Ruff
- basic compile checks
- readable logging
- type hints where practical

## Sprint roadmap

### Sprint 1
Repository scaffolding and GitHub setup

### Sprint 2
Developer tooling and code cleanup

### Sprint 3
Price sensor discovery and options flow

### Sprint 4
Price decision engine and hysteresis

### Sprint 5
Automatic switching based on configured price source

### Sprint 6
Diagnostics, tests, and documentation

### Sprint 7
HACS release preparation

## Notes

Keep the working Growatt control path stable while adding new features.
If a feature is not yet proven, keep it behind configuration or in a separate module.