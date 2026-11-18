"""Exercise every Smart Grid caller against the accepted request contract."""
from datetime import date, datetime, timedelta
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import forecasts
from roi import collect as roi
from roi import history as roi_history
from electricity import replay
import refresh_history as ni_history
import snapshot as ni_snapshot


class GridRequestTests(unittest.TestCase):
    def query(self, url):
        query = {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}
        # Reproduce the operator's rejection rather than accepting any URL.
        if query['dateRange'] != 'day':
            raise HTTPError(url, 400, 'Invalid request', {}, None)
        return query

    def payload(self, query, field, clock='23:00:00'):
        return json.dumps({'Rows': [dict(Region=query['region'], FieldName=field, Value=0,
            EffectiveTime=query['dateTo'] + ' ' + clock)]}).encode()

    def test_ni_overview_requests_all_required_actuals(self):
        fields = dict(demand='SYSTEM_DEMAND', generation='GEN_EXP', wind='WIND_ACTUAL',
                      solar='SOLAR_ACTUAL', interconnection='INTER_MOYLE')
        def source(request, **kwargs):
            query = self.query(request.full_url)
            self.assertEqual(query['region'], 'NI')
            self.assertEqual(query['dateTo'], '01-Nov-2026')
            return io.BytesIO(self.payload(query, fields[query['chartType']]))
        with patch.object(ni_snapshot.urllib.request, 'urlopen', side_effect=source):
            for chart, field in fields.items():
                with self.subTest(chart=chart):
                    area = chart + 'actual' if chart != 'interconnection' else chart
                    data = ni_snapshot.fetch_grid(chart, area, '01-Nov-2026')
                    self.assertEqual(data['data']['Rows'][0]['FieldName'], field)

    def test_roi_actuals_and_forecasts_use_the_supported_request(self):
        now = datetime(2026, 11, 1, 12)
        def source(url):
            query = self.query(url)
            self.assertEqual(query['region'], 'ROI')
            self.assertEqual(query['dateFrom'], '01-Nov-2026')
            fields = dict(demand='SYSTEM_DEMAND', generation='GEN_EXP', wind='WIND_ACTUAL',
                          solar='SOLAR_ACTUAL', interconnection='INTER_EWIC')
            return self.payload(query, fields[query['chartType']], '11:45:00')
        with tempfile.TemporaryDirectory() as directory, patch.object(roi, 'CACHE', Path(directory)), \
                patch.object(roi, 'NOW', now), patch.object(roi, 'fetch', side_effect=source) as fetch:
            for chart in ['demand', 'generation', 'wind', 'solar', 'interconnection']:
                roi.download_grid(('ROI', chart))
            for chart in ['demand', 'wind', 'solar']:
                roi.download_forecast(chart)
            self.assertEqual(fetch.call_count, 8)

    def test_ni_forecast_requests_keep_the_requested_date_and_area(self):
        def source(request, **kwargs):
            query = self.query(request.full_url)
            self.assertEqual(query['region'], 'NI')
            self.assertEqual(query['dateFrom'], query['dateTo'])
            self.assertEqual(query['dateTo'], '01-Nov-2026')
            self.assertEqual(query['areas'], query['chartType'] + 'forecast')
            return io.BytesIO(self.payload(query, forecasts.FEEDS[query['chartType']][2]))
        with patch.object(forecasts.urllib.request, 'urlopen', side_effect=source):
            for chart in forecasts.FEEDS:
                forecasts.fetch_forecast(chart, '2026-11-01')

    def historical_source(self, url, headers):
        query = self.query(url)
        first = datetime.strptime(query['dateFrom'], '%d-%b-%Y')
        last = datetime.strptime(query['dateTo'], '%d-%b-%Y')
        # The multi-day body can be empty despite real daily observations.
        # One genuinely missing day must remain a gap, not become zero.
        rows = []
        if first == last and first.day != 2:
            for minute in range(0, 1440, 15):
                at = first + timedelta(minutes=minute)
                rows.append(dict(Region=query['region'], FieldName='SYSTEM_DEMAND', Value=100,
                                 EffectiveTime=at.strftime('%d-%b-%Y %H:%M:%S')))
        return json.dumps({'Rows': rows}).encode()

    def test_ni_history_recovers_daily_data_from_empty_ranges_and_keeps_gaps(self):
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 11, 4, tzinfo=tz)
        with tempfile.TemporaryDirectory() as directory, patch.object(ni_history, 'CACHE', Path(directory)), \
                patch.object(ni_history, 'datetime', Clock), \
                patch.object(ni_history, 'fetch', side_effect=self.historical_source), patch.object(ni_history.time, 'sleep'):
            data = ni_history.grid_month(('demand', 2026, 11, True))
        self.assertEqual(len(data['rows']), 192)
        self.assertEqual({row[0][:10] for row in data['rows']}, {'2026-11-01', '2026-11-03'})
        self.assertTrue(data['emptyRangeChecked'])

    def test_roi_history_recovers_daily_data_from_empty_ranges_and_keeps_gaps(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(roi_history, 'fetch', side_effect=self.historical_source), patch.object(ni_history.time, 'sleep'):
            data = roi_history.grid_month(('demand', 2026, 11, True), Path(directory), date(2026, 11, 4))
        self.assertEqual(len(data['rows']), 192)
        self.assertEqual({row[0][:10] for row in data['rows']}, {'2026-11-01', '2026-11-03'})
        self.assertTrue(data['emptyRangeChecked'])

    def test_partial_ranges_retry_missing_days_and_replace_a_complete_revision_as_a_whole(self):
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 11, 4, tzinfo=tz)
        for region, module in [('NI', ni_history), ('ROI', roi_history)]:
            attempts = {}
            def daily(day, count=96, value=100):
                return [dict(Region=region, FieldName='SYSTEM_DEMAND', Value=value,
                    EffectiveTime=(datetime(2026, 11, day) + timedelta(minutes=i * 15)).strftime('%d-%b-%Y %H:%M:%S'))
                    for i in range(count)]
            def source(url, headers):
                query = self.query(url)
                if query['dateFrom'] != query['dateTo']:
                    return json.dumps({'Rows': daily(1) + daily(3, 95)}).encode()
                day = datetime.strptime(query['dateFrom'], '%d-%b-%Y').day
                self.assertIn(day, [2, 3])  # Complete and unfinished days need no request.
                attempts[day] = attempts.get(day, 0) + 1
                rows = daily(3, value=200) if day == 3 and attempts[day] > 1 else []
                return json.dumps({'Rows': rows}).encode()
            with self.subTest(region=region), tempfile.TemporaryDirectory() as directory, \
                    patch.object(module, 'fetch', side_effect=source), patch.object(ni_history.time, 'sleep'), \
                    patch.object(ni_history, 'datetime', Clock), patch.object(ni_history, 'CACHE', Path(directory)):
                if region == 'NI':
                    data = module.grid_month(('demand', 2026, 11, True))
                else:
                    data = module.grid_month(('demand', 2026, 11, True), Path(directory), date(2026, 11, 4))
            self.assertEqual(len(data['rows']), 192)
            self.assertEqual({row[1] for row in data['rows'] if row[0].startswith('2026-11-03')}, {200})
            self.assertEqual(attempts, {2: 3, 3: 2})

    def test_replay_uses_supported_ranges_for_both_regions(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(replay, 'fetch', side_effect=self.historical_source), patch.object(replay.time, 'sleep'):
            for region in ['ni', 'roi']:
                data = replay.grid_month(region, 'demand', date(2026, 11, 1), date(2026, 11, 3),
                                         Path(directory), True, [])
                self.assertEqual(len(data['rows']), 192)
                self.assertEqual({row[0][:10] for row in data['rows']}, {'2026-11-01', '2026-11-03'})

    def test_daily_retries_do_not_replace_a_better_partial_response(self):
        def rows(count, value):
            return [dict(EffectiveTime=(datetime(2026, 11, 1) + timedelta(minutes=i * 15)).strftime('%d-%b-%Y %H:%M:%S'),
                         Value=value) for i in range(count)]
        previous = rows(95, 100)
        with patch.object(ni_history.time, 'sleep'):
            result = ni_history.fill_grid_days(previous, date(2026, 11, 1), date(2026, 11, 1),
                                               lambda *_: rows(94, 200))
        self.assertEqual(result, previous)


if __name__ == '__main__':
    unittest.main()
