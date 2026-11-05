from datetime import datetime, timezone
import unittest
from unittest.mock import patch

import forecasts


class ForecastTests(unittest.TestCase):
    def slots(self, step, value):
        return {f'{i // 60:02}:{i % 60:02}:00': value for i in range(0, 1440, step)}

    def test_combined_peak_uses_matching_times_not_sum_of_separate_peaks(self):
        wind, solar = self.slots(15, 50), self.slots(15, 0)
        wind['06:00:00'] = 400
        solar['12:00:00'] = 150
        self.assertEqual(forecasts.wind_solar_peak(wind, solar), 400)
        del solar['06:00:00']
        self.assertIsNone(forecasts.wind_solar_peak(wind, solar))

    def test_expected_demand_keeps_observed_peak_as_day_advances(self):
        actual = {clock: 800 for clock in self.slots(15, 0) if clock < '13:30:00'}
        actual['08:15:00'] = 1200
        forecast = {clock: 1000 for clock in self.slots(30, 0) if clock >= '13:30:00'}
        self.assertEqual(forecasts.demand_peak(actual, forecast), 1200)
        forecast['17:30:00'] = 1300
        self.assertEqual(forecasts.demand_peak(actual, forecast), 1300)
        del forecast['17:30:00']
        self.assertIsNone(forecasts.demand_peak(actual, forecast))

    def test_demand_allows_only_the_short_actual_to_forecast_publication_gap(self):
        actual = {clock: 800 for clock in self.slots(15, 0) if clock <= '13:15:00'}
        forecast = {clock: 1000 for clock in self.slots(30, 0) if clock >= '14:00:00'}
        self.assertEqual(forecasts.demand_peak(actual, forecast), 1000)
        del actual['06:00:00']
        self.assertIsNone(forecasts.demand_peak(actual, forecast))

    def test_source_date_region_zero_and_conflicting_duplicates(self):
        row = {'FieldName': 'SOLAR_FCAST', 'Region': 'NI', 'Value': 0, 'EffectiveTime': '01-Nov-2026 00:00:00'}
        self.assertEqual(forecasts.readings({'Rows': [row]}, 'SOLAR_FCAST', '2026-11-01'), {'00:00:00': 0})
        self.assertEqual(forecasts.readings({'Rows': [row]}, 'SOLAR_FCAST', '2026-11-02'), {})
        self.assertEqual(forecasts.readings({'Rows': [{**row, 'Region': 'ALL'}]}, 'SOLAR_FCAST', '2026-11-01'), {})
        with self.assertRaises(ValueError):
            forecasts.readings({'Rows': [row, {**row, 'Value': 20}]}, 'SOLAR_FCAST', '2026-11-01')

    def test_collection_retains_the_matching_peak_time_and_first_tie(self):
        now = datetime(2026, 11, 1, 14, tzinfo=timezone.utc)
        actual = {clock: 800 for clock in self.slots(15, 0) if clock <= '13:15:00'}
        demand = {clock: 1000 for clock in self.slots(30, 0) if clock >= '14:00:00'}
        demand.update({'17:30:00': 1500, '18:00:00': 1500})
        def rows(values, field):
            return {'Rows': [{'Region': 'NI', 'FieldName': field, 'Value': value,
                'EffectiveTime': '01-Nov-2026 ' + clock} for clock, value in values.items()]}
        def fetch(name, day):
            values = demand if name == 'demand' else self.slots(15, 0)
            return rows(values, forecasts.FEEDS[name][2]), 'https://example.test/' + name
        for observed, value, clock in [(1400, 1500, '17:30'), (1600, 1600, '08:15')]:
            with self.subTest(observed=observed), patch.object(forecasts, 'fetch_forecast', side_effect=fetch):
                actual['08:15:00'] = observed
                source = {'source_grid_payloads': [{'data': rows(actual, 'SYSTEM_DEMAND'), 'url': 'https://example.test/actual'}]}
                peak = forecasts.collect(source, now=now)['demand']
                self.assertEqual((peak['value'], peak['time']), (value, clock))

    def test_failed_forecasts_preserve_only_same_day_peaks(self):
        now = datetime(2026, 11, 1, 14, tzinfo=timezone.utc)
        previous = {'date': '2026-11-01', 'demand': {'value': 1200}, 'windSolar': {'value': 400}}
        with patch.object(forecasts, 'fetch_forecast', side_effect=RuntimeError('source down')):
            current = forecasts.collect({}, previous, now)
            self.assertEqual(current, previous)
            tomorrow = forecasts.collect({}, previous, datetime(2026, 11, 2, 1, tzinfo=timezone.utc))
            self.assertIsNone(tomorrow['demand'])
            self.assertIsNone(tomorrow['windSolar'])


if __name__ == '__main__':
    unittest.main()
