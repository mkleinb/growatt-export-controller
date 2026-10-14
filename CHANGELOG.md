# Changelog

## 1.5.1
- Fix stalled solar telemetry caused by price-control status updates resetting the refresh timer.
- Preserve telemetry refresh health when publishing control status.
- Add regression tests for periodic telemetry and status updates.
- Update Python aliases for lint compatibility.

## 1.0.0
- Initial working Growatt Export Controller integration
- Browser-compatible login flow
- Export limit control via `tcpSet.do`
- Service, switch, number and sensor entities
