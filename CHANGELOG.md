# Changelog

## 1.2.0-rc.1

- Added automatic discovery of likely numeric electricity-price sensors.
- Added price automation with activation/recovery hysteresis.
- Added configurable triggered and normal Growatt targets.
- Set the requested low-price default to Meter Enable on and export 100%.
- Added tax-basis conversion options and common unit normalization.
- Added immediate state-change evaluation, periodic checks and reapplication.
- Added current price and price-control status sensors.
- Added `evaluate_price_control` action and diagnostics.
- Updated options flow for current Home Assistant versions.
- Tightened Growatt command success detection to `success: true` / `inv_set_success`.
- Reduced sensitive HTTP traces to debug logging and redacted account fields.

## 1.0.0

- Initial working Growatt cloud export control.
