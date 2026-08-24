# Growatt Export Controller project

## Goal

Provide a reliable Home Assistant custom integration that controls Growatt export settings through the Growatt cloud and can automatically switch those settings from a selected electricity-price sensor.

## Proven Growatt command

The integration uses the browser-compatible login flow and sends `backflow_setting` commands to `tcpSet.do`. A command is considered successful only when Growatt explicitly returns `success: true` or `inv_set_success`.

## Price-control defaults

At or below the configured activation threshold:

- Meter Enable: on
- Export percentage: 100%

At or above the configured recovery threshold:

- Meter Enable: off
- Export percentage: 100%

## Important limitation

The cloud flow has no reliable settings readback in this integration. Entities therefore represent the last command successfully sent by Home Assistant. An optional reapply interval can reconcile changes made outside Home Assistant.
