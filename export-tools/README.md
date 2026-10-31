# Public itinerary JSON export

Public URL: https://comet-account.github.io/itinerary/japan-2027-yyuwzv/itinerary.json

This JSON is intentionally public, readable without a token, and NOT protected by the HTML unlock gate. The existing HTML encryption is unchanged. Static hosting has no editing API.

## Existing split architecture

The editable app, private data, and working exporter remain at `/home/comet/itinerary`. The Git-backed Pages output remains at `/home/comet/Documents/git/itinerary`. Do not initialize Git in the app or commit private data.

`public-json.patch` versions only the change to the existing `scripts/export_share.py`; it intentionally does not publish the entire app/exporter or its trip-specific HTML themes. The patch is already applied locally. For a pre-feature copy, inspect it then apply with `patch --dry-run -p1 < /path/to/public-json.patch` followed by `patch -p1 < /path/to/public-json.patch` from the app directory. Do not apply twice. `test_public_itinerary_json.py` is the matching synthetic-fixture test, also installed under the app's `tests/` directory.

Normal `npm run export:share -- <trip> ...` now emits both HTML and JSON from the same source. Existing `--token` still encrypts HTML only. Preserve an existing deployed site's exact bytes when updating JSON alone:

```
cd /home/comet/itinerary
npm run export:share -- japan-2027-feb --slug japan-2027-yyuwzv --json-only
```

No token is required for this mode. Review the generated file and Git diff before committing/pushing. Private source data is never copied to this repository.

## Schema version 1

Top-level allowlist: `schemaVersion`, `version`, `name`, `startDate`, `endDate`, `stops`, `restaurants`.

`version` is SHA-256 of UTF-8 compact, sorted-key JSON of all the other fields (Unicode unescaped). It changes only when public output changes; no generated timestamp causes churn. Dates/times retain source local ISO strings without inventing a timezone.

Each chronological stop has only `name`, `category`, `address`, `googleMapsUrl`, `startTime`, `durationMinutes`, and `alternatives`. Alternatives and the deduplicated food/restaurant/cafe index have only the four venue fields. The index includes source food-category placeholders; it does not imply a confirmed restaurant booking. Missing categories/addresses are empty strings; unknown durations are null. Placeholder/composite Google Maps links are null rather than pretending an area is an exact venue. Composite candidates appear as alternatives.

Exact Google venue links are preserved when safe; otherwise links are derived from name/address and a known Place ID. Only HTTPS Google Maps hosts and allowlisted query keys are accepted. URL credentials, fragments, non-Google hosts, and unknown query keys are not copied.

No freeform notes, activity text, labels, internal IDs, contact data, bookings, flight objects, credentials, photos, or arbitrary source fields are serialized. Private/secret/hide/hidden/internal/booking/reservation labels and boolean flags, public=false, published=false, and private visibility exclude records. These exclusions apply to visits, venues, referenced backups, inline alternatives, and composite candidates. Missing references are excluded rather than falling back to potentially private inline data. An excluded trip aborts publication. Only alternatives reachable from eligible visits are included, never unrelated saved places.

## Validation

From the app directory:

```
python3 -m unittest tests/test_public_itinerary_json.py -v
python3 -m unittest tests/test_public_itinerary_json.py tests/test_export_share.py tests/test_restaurant_photos.py tests/test_import_tabelog_place.py -v
python3 -m unittest discover -s tests -v
```

The first two commands pass 6 and 20 tests respectively. Full discovery runs 28 tests: 24 pass and four existing data-dependent map tests fail (arrival dinner reference removed, current venue metadata differs from old assumptions, photo count now 42 rather than 35, Akihabara browse time now 15:35/115 rather than 15:25/125). Reversing only this feature's exporter changes reproduces those same four failing tests. No itinerary data or old assertions were changed to hide them.

Run the versioned test directly against the local app:

```
ITINERARY_APP=/home/comet/itinerary python3 export-tools/test_public_itinerary_json.py -v
```
