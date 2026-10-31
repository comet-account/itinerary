import os
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

APP = Path(os.environ.get('ITINERARY_APP', Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location('export_share', APP / 'scripts/export_share.py')
assert spec is not None and spec.loader is not None
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def fixture():
    place = {'name': '公開食堂', 'category': 'restaurant', 'location': {'address': 'Tokyo'},
             'googleMaps': {'placeId': 'ChIJtest'}, 'notes': 'LEAK-place', 'phone': 'LEAK-phone'}
    trip = {'name': 'Public trip', 'startDate': '2027-02-02', 'endDate': '2027-02-03',
            'token': 'LEAK-token', 'visits': [
                {'placeRef': 'food', 'startTime': '2027-02-02T12:00', 'durationMinutes': 60,
                 'notes': 'LEAK-visit', 'activity': 'LEAK-freeform', 'booking': 'LEAK-booking'}]}
    return trip, {'food': place, 'unrelated': {'name': 'LEAK-unrelated'}}


class PublicJsonTest(unittest.TestCase):
    def test_existing_export_writes_allowlisted_json_even_when_encrypted(self):
        trip, places = fixture()
        with tempfile.TemporaryDirectory() as td:
            page = export.export_trip(trip, places, Path(td), slug='test', token='LEAK-token')
            target = page.with_name('itinerary.json')
            self.assertTrue(target.is_file(), 'existing export must also write public itinerary.json')
            data = json.loads(target.read_text())
            self.assertEqual(set(data), {'schemaVersion', 'version', 'name', 'startDate', 'endDate', 'stops', 'restaurants'})
            self.assertEqual(data['schemaVersion'], 1)
            self.assertEqual(data['startDate'], trip['startDate'])
            self.assertEqual(data['endDate'], trip['endDate'])
            stop = data['stops'][0]
            self.assertEqual(set(stop), {'name', 'category', 'address', 'googleMapsUrl', 'startTime', 'durationMinutes', 'alternatives'})
            self.assertEqual(stop['name'], '公開食堂')
            self.assertEqual(stop['address'], 'Tokyo')
            self.assertIn('query_place_id=ChIJtest', stop['googleMapsUrl'])
            self.assertEqual(data['restaurants'][0]['name'], stop['name'])
            self.assertNotIn('LEAK', target.read_text())
            self.assertIn('Unlock itinerary', page.read_text())
            plain = export.decrypt_html_payload(export.extract_encrypted_payload(page.read_text()), 'LEAK-token')
            self.assertIn('公開食堂', plain)

    def test_exclusions_apply_to_stops_backups_and_composite_candidates(self):
        trip, places = fixture()
        visit = trip['visits'][0]
        visit['shoppingBackups'] = [{'name': 'Public backup', 'address': 'Osaka', 'notes': 'LEAK-note'},
                                    {'placeRef': 'missing', 'name': 'LEAK-missing'}]
        places['food']['googleMaps']['candidates'] = [{'name': 'Public candidate', 'address': 'Kyoto'}]
        flags = [{'labels': [label.upper()]} for label in export.PRIVATE_LABELS]
        flags += [{key: True} for key in ('private', 'hidden', 'reservation')]
        flags += [{'public': False}, {'published': False}, {'visibility': 'private'}]
        for i, flag in enumerate(flags):
            secret = {'name': f'LEAK-{i}', **flag}
            places[f'secret{i}'] = secret
            trip['visits'].append({'placeRef': f'secret{i}', 'startTime': '2027-02-02T13:00'})
            trip['visits'].append({'placeRef': 'food', 'startTime': '2027-02-02T14:00', **flag})
            visit['shoppingBackups'].extend([secret, {'placeRef': f'secret{i}'}, {'placeRef': 'food', **flag}])
            places['food']['googleMaps']['candidates'].append(secret)
        data = export.public_itinerary_json(trip, places)
        self.assertEqual(len(data['stops']), 1)
        self.assertEqual({p['name'] for p in data['stops'][0]['alternatives']}, {'Public backup', 'Public candidate'})
        self.assertNotIn('LEAK', json.dumps(data))

    def test_exact_venue_urls_and_no_url_credentials(self):
        trip, places = fixture()
        identity = places['food']['googleMaps']
        for url in ('https://maps.app.goo.gl/nn976JtkrDBVfJwF7',
                    'https://www.google.com/maps/search/?api=1&query=Cafe&query_place_id=ChIJtest'):
            identity['sourceUrl'] = url
            self.assertEqual(export.public_itinerary_json(trip, places)['stops'][0]['googleMapsUrl'], url)
        for url in ('https://www.google.com/maps/search/?query=Cafe&token=LEAK',
                    'https://user:LEAK@www.google.com/maps/place/Cafe',
                    'https://evil.example/maps/place/LEAK',
                    'https://maps.app.goo.gl/abc#token=LEAK'):
            identity['sourceUrl'] = url
            actual = export.public_itinerary_json(trip, places)['stops'][0]['googleMapsUrl']
            self.assertNotIn('LEAK', actual)
            self.assertIn('query_place_id=ChIJtest', actual)
        identity['status'] = 'placeholder'
        self.assertIsNone(export.public_itinerary_json(trip, places)['stops'][0]['googleMapsUrl'])
        identity['status'] = 'composite'
        self.assertIsNone(export.public_itinerary_json(trip, places)['stops'][0]['googleMapsUrl'])

    def test_version_is_deterministic_public_content_hash(self):
        trip, places = fixture()
        initial = export.public_itinerary_json(trip, places)
        self.assertRegex(initial['version'], r'^[0-9a-f]{64}$')
        places['food']['notes'] = 'changed private note'
        self.assertEqual(initial, export.public_itinerary_json(trip, places))
        places['food']['name'] = 'Updated venue'
        self.assertNotEqual(initial['version'], export.public_itinerary_json(trip, places)['version'])

    def test_private_trip_and_nested_scalar_injection_fail_closed(self):
        trip, places = fixture()
        for flag in ({'private': True}, {'published': False}, {'labels': ['hidden']}):
            with self.assertRaises(ValueError):
                export.public_itinerary_json({**trip, **flag}, places)
        trip['visits'][0]['durationMinutes'] = {'contact': 'LEAK'}
        with self.assertRaises(ValueError):
            export.public_itinerary_json(trip, places)

    def test_json_only_cli_preserves_existing_site_bytes(self):
        trip, places = fixture()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app = root / 'app'
            (app / 'data').mkdir(parents=True)
            (app / 'data/trips.json').write_text(json.dumps({'trips': [trip]}))
            (app / 'data/saved-places.json').write_text(json.dumps(places))
            page = export.export_trip(trip, places, root / 'out', slug='test', token='test-token')
            before = page.read_bytes()
            asset = page.parent / 'untouched.bin'
            asset.write_bytes(b'preserve asset')
            args = ['Public trip', '--app', str(app), '--out', str(root / 'out'), '--slug', 'test', '--json-only']
            self.assertEqual(export.main(args), 0)
            self.assertEqual(page.read_bytes(), before)
            self.assertEqual(asset.read_bytes(), b'preserve asset')
            self.assertEqual(json.loads(page.with_name('itinerary.json').read_text()), export.public_itinerary_json(trip, places))


if __name__ == '__main__':
    unittest.main()
