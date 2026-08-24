# Growatt Export Controller for Home Assistant

Community Home Assistant integration for controlling Growatt export settings through the Growatt cloud web flow.

> This project is not affiliated with Growatt. Growatt can change the undocumented web endpoints at any time.

## RC1 features

- UI config flow with Growatt login validation
- Browser-compatible Growatt cloud session and automatic re-login
- `Meter Enable` switch
- `Export percentage` slider
- `growatt_export_controller.set_export_limit` action
- Automatic electricity-price control
- Automatic discovery and ranking of numeric electricity-price sensors, including Zonneplan-style tariff sensors
- Configurable activation and recovery thresholds with hysteresis
- Configurable tax basis conversion
- Default low-price behavior: **Meter Enable ON and export percentage 100%**
- Default normal behavior: **Meter Enable OFF and export percentage 100%**
- Immediate evaluation on price changes, periodic safety checks, and optional periodic reapplication
- Status, current comparison price, diagnostics, retries and redacted debug logging

## Installation with HACS

1. In HACS, add `https://github.com/mkleinb/growatt-export-controller` as a custom integration repository.
2. Install **Growatt Export Controller**.
3. Restart Home Assistant.
4. Open **Settings → Devices & services → Add integration** and select **Growatt Export Controller**.

For a local RC test, replace the complete directory:

```text
/config/custom_components/growatt_export_controller
```

with the directory from this repository, then restart Home Assistant.

## Initial Growatt configuration

Enter:

- Growatt username and password
- inverter serial number
- command server URL (`https://server.growatt.com`)
- initial local entity state (normally export 100%, Meter Enable off)

The daily password shown by the Growatt web interface is a browser-side gate and is not part of the successful `tcpSet.do` request captured for this inverter.

## Price automation

Open **Settings → Devices & services → Growatt Export Controller → Configure**.

Recommended first test:

- Enable price automation
- Select the detected Zonneplan current electricity tariff sensor
- Activation threshold: `0.05` EUR/kWh
- Recovery threshold: `0.06` EUR/kWh
- Below threshold: Meter Enable **on**, export **100%**
- Above recovery threshold: Meter Enable **off**, export **100%**
- Keep both tax-basis switches equal when the sensor and thresholds are already on the same basis

At startup, the integration applies the desired price-control state once because this cloud integration has no reliable settings readback endpoint.

## Actions

```yaml
action: growatt_export_controller.set_export_limit
data:
  percentage: 100
  meter_enabled: true
```

Force a price evaluation and resend the desired state:

```yaml
action: growatt_export_controller.evaluate_price_control
data:
  force_apply: true
```

## Important behavior

The switch and slider show the last state successfully commanded by Home Assistant. They are not a live readback of the inverter. Periodic reapplication can be used to reconcile changes made outside Home Assistant.

## Debug logging

```yaml
logger:
  default: info
  logs:
    custom_components.growatt_export_controller: debug
```

Growatt credentials and account fields are redacted from request payload logging.

## Fast Synology test deployment

The repository contains a deployment script for the NAS settings used during development:

```bash
cd ~/Projects/growatt_export_controller
./scripts/deploy_to_synology.sh
```

Defaults:

- SSH user: `maurice`
- NAS: `192.168.1.5`
- SSH port: `21967`
- Home Assistant config: `/volume1/docker/homeassistant`

The script first creates a timestamped backup of the installed integration and then synchronizes only `custom_components/growatt_export_controller`. It does not restart Home Assistant automatically. Restart the Home Assistant container in Synology Container Manager after deployment.

To restore the most recent backup:

```bash
./scripts/rollback_on_synology.sh
```

The connection settings can be overridden, for example:

```bash
NAS_HOST=192.168.1.10 NAS_PORT=22 ./scripts/deploy_to_synology.sh
```

## RC1 limitations

- The switch and percentage entity are optimistic and show the last command accepted by Growatt, not live inverter readback.
- The price-control hysteresis mode is held in memory. After a Home Assistant restart, the integration evaluates from normal mode and reconciles the desired state.
- Growatt uses undocumented web endpoints and may change the login or command flow without notice.
