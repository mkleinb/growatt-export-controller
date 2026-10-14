"""Exercise the real status publisher without requiring a Home Assistant install."""

import ast
import unittest
from dataclasses import dataclass, replace
from pathlib import Path

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "custom_components/growatt_export_controller/coordinator.py"
)


def load_publisher():
    """Compile the actual method; model only Home Assistant's scheduler below."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "GrowattExportControllerCoordinator"
    )
    method = next(
        node for node in coordinator.body
        if isinstance(node, ast.FunctionDef) and node.name == "_publish_state"
    )
    namespace = {"replace": replace}
    module = ast.Module(body=[method], type_ignores=[])
    # Execute only this repository's publisher, not an external code fragment.
    exec(compile(module, str(SOURCE), "exec"), namespace)  # noqa: S102
    return namespace["_publish_state"]


@dataclass
class State:
    price_mode: str = "normal"
    solar_energy_total_kwh: float = 26257.5


class CoordinatorHarness:
    """Model the timer reset performed by HA's async_set_updated_data."""

    def __init__(self):
        self._state = State()
        self.data = self._state
        self.now = 0
        self.next_refresh = 300
        self.telemetry_reads = 0
        self.notifications = []
        self.last_update_success = False
        self.last_exception = RuntimeError("previous telemetry failure")
        self.pending_refresh = True

    def async_set_updated_data(self, data):
        self.data = data
        self.next_refresh = self.now + 300
        self.last_update_success = True
        self.pending_refresh = False
        self.async_update_listeners()

    def async_update_listeners(self):
        self.notifications.append(self.data)

    def advance(self, seconds):
        self.now = seconds
        if self.now >= self.next_refresh:
            self.telemetry_reads += 1
            self.next_refresh = self.now + 300


class PublishStateTests(unittest.TestCase):
    def setUp(self):
        self.publish = load_publisher()
        self.coordinator = CoordinatorHarness()

    def test_frequent_price_updates_do_not_starve_telemetry(self):
        for seconds in range(60, 1201, 60):
            self.coordinator.now = seconds
            self.publish(self.coordinator, price_mode="sleeping")
            self.coordinator.advance(seconds)
        self.assertEqual(self.coordinator.telemetry_reads, 4)
        self.assertEqual(len(self.coordinator.notifications), 20)

    def test_status_update_preserves_pending_refresh_and_deadline(self):
        self.coordinator.now = 299
        self.publish(self.coordinator, price_mode="normal")
        self.assertEqual(self.coordinator.next_refresh, 300)
        self.assertTrue(self.coordinator.pending_refresh)
        self.coordinator.advance(300)
        self.assertEqual(self.coordinator.telemetry_reads, 1)

    def test_listeners_receive_updated_state_and_existing_solar_total(self):
        self.publish(self.coordinator, price_mode="sleeping")
        self.assertIs(self.coordinator.data, self.coordinator._state)
        self.assertEqual(self.coordinator.notifications, [self.coordinator.data])
        self.assertEqual(self.coordinator.data.price_mode, "sleeping")
        self.assertEqual(self.coordinator.data.solar_energy_total_kwh, 26257.5)

    def test_status_update_does_not_mark_failed_telemetry_successful(self):
        exception = self.coordinator.last_exception
        self.publish(self.coordinator, price_mode="normal")
        self.assertFalse(self.coordinator.last_update_success)
        self.assertIs(self.coordinator.last_exception, exception)


if __name__ == "__main__":
    unittest.main()
