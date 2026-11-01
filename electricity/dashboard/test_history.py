"""Numerical checks for missing data, averages, signed flows and interval energy."""
import unittest
from unittest.mock import patch
import tempfile
import gzip
import json
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
import refresh_history as history


class HistoryTests(unittest.TestCase):
    def day(self, value, count=96):
        return [(f"{i // 4:02}:{i % 4 * 15:02}:00", value) for i in range(count)]

    def test_missing_intervals_are_not_zero(self):
        self.assertEqual(history.daily_average(self.day(100, 95), 96), (None, 95))
        self.assertEqual(history.daily_average(self.day(0), 96), (0, 96))

    def test_conflicting_duplicates_reject_day(self):
        self.assertIsNone(history.daily_average(self.day(100) + [('00:00:00', 200)], 96)[0])
        self.assertEqual(history.daily_average(self.day(100) + [('00:00:00', 100)], 96), (100, 96))

    def test_uniform_samples_match_time_average(self):
        values = self.day(0)
        values = [(stamp, 100 if i < 48 else 200) for i, (stamp, _) in enumerate(values)]
        self.assertEqual(history.daily_average(values, 96)[0], 150)

    def test_import_export_sign_is_preserved(self):
        self.assertEqual(history.daily_average(self.day(-50), 96)[0], -50)

    def test_half_hour_meter_energy_to_power(self):
        raw = b'<Report Date="2026-01-01" PublishTime="2026-01-02T14:00:00"><Row ResourceName="GU_503740" StartTime="2026-01-01T00:00:00" EndTime="2026-01-01T00:29:59" MeteredMW="25"/></Report>'
        with tempfile.TemporaryDirectory() as directory, patch.object(history, 'CACHE', Path(directory)), patch.object(history, 'fetch', return_value=raw):
            result = history.meter_report({'ResourceName':'PUB_DailyMeterDataD1_test-energy.xml'})
        power = result['rows'][0][2]
        self.assertEqual(power, 50)
        rows = [(f"{i // 2:02}:{i % 2 * 30:02}:00", power) for i in range(48)]
        average, count = history.daily_average(rows, 48)
        self.assertEqual((average, count), (50, 48))
        self.assertEqual(average * 24, 1200)

    def test_empty_large_window_is_rechecked_not_treated_as_missing_history(self):
        def source(url, headers):
            query = parse_qs(urlparse(url).query)
            start = datetime.strptime(query['dateFrom'][0], '%d-%b-%Y')
            end = datetime.strptime(query['dateTo'][0], '%d-%b-%Y')
            if (end-start).days == 30:
                return b'{"Rows":[]}'
            rows = []
            current = start
            while current < end + timedelta(days=1):
                rows.append(dict(FieldName='WIND_ACTUAL',Region='NI',Value=100,EffectiveTime=current.strftime('%d-%b-%Y %H:%M:%S')))
                current += timedelta(minutes=15)
            return json.dumps({'Rows':rows}).encode()
        with tempfile.TemporaryDirectory() as directory, patch.object(history, 'CACHE', Path(directory)), patch.object(history, 'fetch', side_effect=source) as fetch:
            # An old empty-cache entry must not permanently mask real observations.
            (Path(directory)/'wind-2026-01.json.gz').write_bytes(gzip.compress(b'{"rows":[]}'))
            result = history.grid_month(('wind',2026,1,False))
            self.assertEqual(len(result['rows']), 31*96)
            self.assertEqual(len(result['urls']), 3)
            self.assertEqual(fetch.call_count, 3)
            history.grid_month(('wind',2026,1,False))
            self.assertEqual(fetch.call_count, 3)


if __name__ == '__main__':
    unittest.main()
