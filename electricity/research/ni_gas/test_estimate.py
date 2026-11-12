"""Checks for fuel-curve integration and complete, correctly aligned gas days."""
from datetime import date, timedelta
from pathlib import Path
import unittest
from unittest.mock import patch

from electricity.research.ni_gas import estimate as model
from electricity.research.ni_gas.backtest import metrics


class GasEstimateTests(unittest.TestCase):
    def test_kilroot_piecewise_fuel_input_includes_online_base_once(self):
        curve = dict(baseGjPerHourLhv=703, segments=[[326, 6.79], [345, 10.9]])
        self.assertAlmostEqual(model.fuel_rate(335, curve), 3014.64)
        self.assertAlmostEqual(model.fuel_rate(326, curve), 2916.54)
        self.assertEqual(model.fuel_rate(0, curve), 0)
        self.assertEqual(model.fuel_rate(-2, curve), 0)

    def test_coolkeeragh_segments_integrate_marginal_not_average_rates(self):
        curve = dict(baseGjPerHourLhv=635.4, segments=[[211, 4.21], [260, 5.23], [310, 5.25]])
        self.assertAlmostEqual(model.fuel_rate(300, curve), 1989.98)

    def test_gas_days_follow_local_five_am_across_clock_changes(self):
        for day, hours in [(date(2026, 3, 28), 23), (date(2026, 10, 24), 25), (date(2026, 11, 4), 24)]:
            first, last = model.gas_window(day)
            self.assertEqual(last - first, timedelta(hours=hours))

    def test_incomplete_meter_day_cannot_produce_a_partial_residual(self):
        with patch.object(model, 'model_parameters', return_value={}), patch.object(model, 'read_meters', return_value={}):
            with self.assertRaisesRegex(ValueError, 'Incomplete gas day'):
                model.estimate(date(2026, 11, 4), Path('.'), Path('unused.xml'), Path('unused.json'))

    def test_long_observed_shutdown_establishes_cold_start_without_last_run(self):
        curve = dict(startupGjLhv=[639, 1134, 2025], startupCoolingHours=[8, 40, 150])
        self.assertEqual(model.startup_fuel(curve, 9), 1134)
        self.assertEqual(model.startup_fuel(curve, 60, exact_history=False), 2025)
        with self.assertRaisesRegex(ValueError, 'Insufficient offline history'):
            model.startup_fuel(curve, 5, exact_history=False)

    def test_backtest_distinguishes_daily_error_from_aggregate_bias(self):
        result = metrics([{'actual': 10, 'estimate': 12}, {'actual': 20, 'estimate': 18}], 'actual', 'estimate')
        self.assertEqual(result['meanAbsoluteErrorGwh'], 2)
        self.assertAlmostEqual(result['meanAbsolutePercentageError'], 15)
        self.assertEqual(result['aggregateBiasPercent'], 0)


if __name__ == '__main__':
    unittest.main()
