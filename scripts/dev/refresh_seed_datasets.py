"""Regenerate the builtin SeedDSL reference datasets from their authoritative sources.

Invoked by ``refresh-seed-datasets.ps1``. Needs the network (it is a script, not a
test). Each dataset is built from a pinned or hash-recorded source whose terms
permit redistribution, and is written as::

    {"provenance": {"source", "url", "version", "retrieved", "licence", "transform"},
     "records": [...]}

into ``datrix-codegen-kernel/src/datrix_codegen_kernel/seed_data``. Afterwards the
script compares every file with ``SEED_DATASETS`` in ``datrix_common`` (row count,
column names and types, longest string, largest integer, natural-key uniqueness)
and exits non-zero while they differ, printing the values the schema must carry.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

WORKSPACE = Path(__file__).resolve().parents[3]
DATA_DIR = WORKSPACE / "datrix-codegen-kernel" / "src" / "datrix_codegen_kernel" / "seed_data"
DEFAULT_CACHE = WORKSPACE / ".tmp" / "seed-source-cache"

CLDR_VERSION = "48.2.3"
CLDR_BASE = f"https://raw.githubusercontent.com/unicode-org/cldr-json/{CLDR_VERSION}/cldr-json"
APACHE_HTTPD_TAG = "2.4.66"
TZDATA_VERSION = "2026.5"
TZDATA_REFERENCE_INSTANT = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)

SIX_URL = (
    "https://www.six-group.com/dam/download/financial-information/data-center/"
    "iso-currrency/lists/list-one.xml"
)
LOC_639_URL = "https://www.loc.gov/standards/iso639-2/ISO-639-2_utf-8.txt"
APACHE_MIME_URL = f"https://raw.githubusercontent.com/apache/httpd/{APACHE_HTTPD_TAG}/docs/conf/mime.types"
IANA_HTTP_URL = "https://www.iana.org/assignments/http-status-codes/http-status-codes-1.csv"
PYPI_TZDATA_URL = f"https://pypi.org/pypi/tzdata/{TZDATA_VERSION}/json"

UNICODE_LICENCE = "Unicode License v3 (https://www.unicode.org/license.txt)"
M49_ROOT = "001"
USER_ASSIGNED_NUMERIC_FROM = 900

CATEGORY_BY_CLASS = {
    1: "informational",
    2: "success",
    3: "redirection",
    4: "client_error",
    5: "server_error",
}


class Fetcher:
    """Download with an on-disk cache keyed by URL, and hash what was read."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, url: str) -> bytes:
        cached = self.cache_dir / hashlib.sha256(url.encode()).hexdigest()
        if cached.exists():
            return cached.read_bytes()
        request = urllib.request.Request(url, headers={"User-Agent": "datrix-seed-refresh"})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        cached.write_bytes(data)
        return data

    def try_get(self, url: str) -> bytes | None:
        try:
            return self.get(url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def json(self, url: str) -> dict:
        return json.loads(self.get(url).decode("utf-8"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def provenance(*, source: str, url: str, version: str, licence: str, transform: str) -> dict[str, str]:
    return {
        "source": source,
        "url": url,
        "version": version,
        "retrieved": date.today().isoformat(),
        "licence": licence,
        "transform": transform,
    }


# --------------------------------------------------------------------------- CLDR


def cldr_territories(fetch: Fetcher) -> dict[str, str]:
    url = f"{CLDR_BASE}/cldr-localenames-full/main/en/territories.json"
    return fetch.json(url)["main"]["en"]["localeDisplayNames"]["territories"]


def build_countries(fetch: Fetcher) -> tuple[list[dict], dict]:
    names = cldr_territories(fetch)
    mappings = fetch.json(f"{CLDR_BASE}/cldr-core/supplemental/codeMappings.json")[
        "supplemental"
    ]["codeMappings"]
    containment = fetch.json(f"{CLDR_BASE}/cldr-core/supplemental/territoryContainment.json")[
        "supplemental"
    ]["territoryContainment"]
    region_of_group = _m49_regions(containment)
    leaf_group: dict[str, str] = {}
    for group, entry in containment.items():
        if not group.isdigit() or entry.get("_grouping") == "true":
            continue
        for member in entry["_contains"]:
            if len(member) == 2:
                leaf_group[member] = group
    records = []
    for alpha2 in sorted(names):
        mapping = mappings.get(alpha2)
        if len(alpha2) != 2 or not alpha2.isalpha() or mapping is None:
            continue
        if "_alpha3" not in mapping or "_numeric" not in mapping:
            continue
        if int(mapping["_numeric"]) >= USER_ASSIGNED_NUMERIC_FROM:
            continue
        group = leaf_group.get(alpha2)
        region = region_of_group.get(group, "") if group else ""
        records.append(
            {
                "alpha2": alpha2,
                "alpha3": mapping["_alpha3"],
                "numeric": mapping["_numeric"],
                "name": names[alpha2],
                "region": names[region] if region else "",
                "subRegion": names[group] if group else "",
            }
        )
    meta = provenance(
        source="Unicode CLDR territory names (English) and M49 territory containment",
        url=f"{CLDR_BASE}/cldr-localenames-full/main/en/territories.json",
        version=f"CLDR {CLDR_VERSION}",
        licence=UNICODE_LICENCE,
        transform=(
            "Rows are CLDR territories with a two-letter code, an ISO 3166-1 alpha-3 and a numeric "
            "code below 900 (user-assigned codes excluded) from supplemental codeMappings. region is "
            "the UN M49 region (child of 001) and subRegion the M49 group that directly contains the "
            "country, both from supplemental territoryContainment, named by the CLDR English "
            "territory names. Territories M49 does not place carry empty region and subRegion."
        ),
    )
    return records, meta


def _m49_regions(containment: dict) -> dict[str, str]:
    """Map every numeric M49 group to the child of 001 it descends from."""
    parents: dict[str, str] = {}
    for group, entry in containment.items():
        if not group.isdigit() or entry.get("_grouping") == "true":
            continue
        for member in entry["_contains"]:
            if member.isdigit():
                parents[member] = group
    result: dict[str, str] = {}
    for group in list(containment):
        if not group.isdigit() or group == M49_ROOT:
            continue
        current = group
        while parents.get(current) not in (None, M49_ROOT):
            current = parents[current]
        if parents.get(current) == M49_ROOT or current in containment[M49_ROOT]["_contains"]:
            result[group] = current
    return result


def build_subdivisions(fetch: Fetcher, country_codes: set[str]) -> tuple[list[dict], dict]:
    url = f"{CLDR_BASE}/cldr-subdivisions-full/subdivisions/en/en.json"
    names = fetch.json(url)["subdivisions"]["localeDisplayNames"]["subdivisions"]
    records = []
    for cldr_id in sorted(names):
        country = cldr_id[:2].upper()
        if country not in country_codes:
            continue
        records.append(
            {"code": f"{country}-{cldr_id[2:].upper()}", "countryAlpha2": country, "name": names[cldr_id]}
        )
    meta = provenance(
        source="Unicode CLDR subdivision names (English)",
        url=url,
        version=f"CLDR {CLDR_VERSION}",
        licence=UNICODE_LICENCE,
        transform=(
            "CLDR subdivision ids (usca) normalised to ISO 3166-2 form (US-CA); rows whose country "
            "is not in the countries dataset are dropped. CLDR carries names only, so a subdivision "
            "has no category."
        ),
    )
    return records, meta


def build_languages(fetch: Fetcher) -> tuple[list[dict], dict]:
    raw = fetch.get(LOC_639_URL)
    records = []
    for line in raw.decode("utf-8-sig").splitlines():
        parts = line.split("|")
        if len(parts) != 5 or not parts[2]:
            continue
        alpha2, english = parts[2], parts[3]
        records.append({"alpha2": alpha2, "name": english, "nativeName": _native_name(fetch, alpha2)})
    records.sort(key=lambda r: r["alpha2"])
    meta = provenance(
        source="ISO 639-2 code list, Library of Congress (ISO 639-2 registration authority)",
        url=LOC_639_URL,
        version=f"sha256:{sha(raw)}",
        licence="Public domain (published by the Library of Congress as the ISO 639-2 registration authority)",
        transform=(
            "Rows that carry an ISO 639-1 code; name is the registration authority's English name. "
            f"nativeName is the CLDR {CLDR_VERSION} name of the language in its own locale "
            "(Unicode License v3), empty when CLDR has no locale for the language."
        ),
    )
    return records, meta


def _native_name(fetch: Fetcher, alpha2: str) -> str:
    data = fetch.try_get(f"{CLDR_BASE}/cldr-localenames-full/main/{alpha2}/languages.json")
    if data is None:
        return ""
    languages = json.loads(data.decode("utf-8"))["main"][alpha2]["localeDisplayNames"]["languages"]
    return languages.get(alpha2, "")


# --------------------------------------------------------------------- the others


def build_currencies(fetch: Fetcher) -> tuple[list[dict], dict]:
    raw = fetch.get(SIX_URL)
    root = ET.fromstring(raw)
    published = root.attrib["Pblshd"]
    by_code: dict[str, dict] = {}
    for entry in root.iter("CcyNtry"):
        code = entry.findtext("Ccy")
        minor = entry.findtext("CcyMnrUnts")
        if not code or minor is None or not minor.isdigit():
            continue
        record = {
            "alphabeticCode": code,
            "numericCode": entry.findtext("CcyNbr", ""),
            "name": entry.findtext("CcyNm", ""),
            "minorUnits": int(minor),
        }
        if by_code.setdefault(code, record) != record:
            raise SystemExit("ISO 4217 code %s appears with two different definitions" % code)
    meta = provenance(
        source="ISO 4217 List One, published by SIX (ISO 4217 maintenance agency)",
        url=SIX_URL,
        version=f"Published {published}",
        licence="Published by SIX for free use",
        transform=(
            "Current currencies and funds only, one row per alphabetic code. Entries without a "
            "currency and entries without minor units (precious metals, testing and unit codes) "
            "are omitted."
        ),
    )
    return [by_code[code] for code in sorted(by_code)], meta


def build_timezones(fetch: Fetcher) -> tuple[list[dict], dict]:
    release = fetch.json(PYPI_TZDATA_URL)
    wheel = next(u for u in release["urls"] if u["filename"].endswith(".whl"))
    archive = zipfile.ZipFile(io.BytesIO(fetch.get(wheel["url"])))
    identifiers = archive.read("tzdata/zones").decode("utf-8").split()
    records = []
    for identifier in sorted(identifiers):
        if "/" not in identifier and identifier != "UTC":
            continue
        zone = ZoneInfo.from_file(
            io.BytesIO(archive.read(f"tzdata/zoneinfo/{identifier}")), key=identifier
        )
        standard = zone.utcoffset(TZDATA_REFERENCE_INSTANT) - zone.dst(TZDATA_REFERENCE_INSTANT)
        minutes = int(standard.total_seconds() // 60)
        sign = "+" if minutes >= 0 else "-"
        records.append(
            {
                "identifier": identifier,
                "utcOffset": "%s%02d:%02d" % (sign, abs(minutes) // 60, abs(minutes) % 60),
                "region": identifier.split("/", 1)[0],
            }
        )
    meta = provenance(
        source="IANA Time Zone Database via the tzdata PyPI distribution",
        url=wheel["url"],
        version=f"tzdata {TZDATA_VERSION}",
        licence="Time zone data: public domain; tzdata packaging: Apache-2.0",
        transform=(
            "Identifiers that contain a '/' plus UTC. utcOffset is the standard (non-DST) offset at "
            f"the reference instant {TZDATA_REFERENCE_INSTANT.isoformat()}, computed with zoneinfo; "
            "region is the identifier prefix before the first '/'."
        ),
    )
    return records, meta


def build_mime_types(fetch: Fetcher) -> tuple[list[dict], dict]:
    raw = fetch.get(APACHE_MIME_URL)
    records = []
    for line in raw.decode("utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2 or "/" not in parts[0]:
            continue
        records.append(
            {"type": parts[0], "extension": "." + parts[1], "category": parts[0].split("/", 1)[0]}
        )
    records.sort(key=lambda r: r["type"])
    if len({r["type"] for r in records}) != len(records):
        raise SystemExit("mime.types lists a media type twice")
    meta = provenance(
        source="Apache HTTP Server mime.types",
        url=APACHE_MIME_URL,
        version=f"httpd {APACHE_HTTPD_TAG}",
        licence="Apache-2.0",
        transform=(
            "One row per media type that lists an extension; extension is the first listed one; "
            "category is the top-level type."
        ),
    )
    return records, meta


def build_http_status_codes(fetch: Fetcher) -> tuple[list[dict], dict]:
    raw = fetch.get(IANA_HTTP_URL)
    records = []
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        value, phrase = row["Value"].strip(), row["Description"].strip()
        if not value.isdigit() or phrase in ("Unassigned", "(Unused)") or "(TEMPORARY" in phrase:
            continue
        records.append(
            {"code": int(value), "phrase": phrase, "category": CATEGORY_BY_CLASS[int(value) // 100]}
        )
    records.sort(key=lambda r: r["code"])
    meta = provenance(
        source="IANA HTTP Status Code Registry",
        url=IANA_HTTP_URL,
        version=f"sha256:{sha(raw)}",
        licence="Public domain (IANA registry data, CC0 1.0)",
        transform=(
            "Assigned codes only (unassigned, unused and temporary registrations omitted); "
            "category from the code class."
        ),
    )
    return records, meta


# ------------------------------------------------------------------------ output


def write_dataset(filename: str, records: list[dict], meta: dict[str, str]) -> None:
    lines = ",\n".join("  " + json.dumps(record, ensure_ascii=False) for record in records)
    text = '{"provenance": %s,\n "records": [\n%s\n ]}\n' % (
        json.dumps(meta, ensure_ascii=False, indent=1).replace("\n", "\n "),
        lines,
    )
    (DATA_DIR / filename).write_text(text, encoding="utf-8", newline="\n")
    print("wrote %s: %d records" % (filename, len(records)))


def schema_drift() -> int:
    """Compare every written file with SEED_DATASETS and print what the schema must carry."""
    from datrix_common.builtins.objects.seed import SEED_DATASETS

    drift = 0
    for method, schema in SEED_DATASETS.items():
        filename = SEED_FILE_BY_METHOD[method]
        records = json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))["records"]
        measured = {"row_count": len(records)}
        for column in schema.columns:
            values = [r[column.name] for r in records]
            if column.type == "String":
                measured[column.name] = max(len(v) for v in values)
            else:
                measured[column.name] = max(values)
        declared = {"row_count": schema.row_count}
        for column in schema.columns:
            declared[column.name] = column.max_length if column.type == "String" else column.max_value
        if measured != declared:
            drift += 1
            print("SCHEMA DRIFT %s: declared %s, measured %s" % (method, declared, measured))
    return drift


SEED_FILE_BY_METHOD = {
    "countries": "iso_3166_countries.json",
    "subdivisions": "iso_3166_2_subdivisions.json",
    "currencies": "iso_4217_currencies.json",
    "timezones": "iana_timezones.json",
    "languages": "iso_639_languages.json",
    "mimeTypes": "mime_types.json",
    "httpStatusCodes": "http_status_codes.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    fetch = Fetcher(args.cache_dir)

    countries, meta = build_countries(fetch)
    write_dataset(SEED_FILE_BY_METHOD["countries"], countries, meta)
    subdivisions, meta = build_subdivisions(fetch, {c["alpha2"] for c in countries})
    write_dataset(SEED_FILE_BY_METHOD["subdivisions"], subdivisions, meta)
    for method, build in (
        ("currencies", build_currencies),
        ("timezones", build_timezones),
        ("languages", build_languages),
        ("mimeTypes", build_mime_types),
        ("httpStatusCodes", build_http_status_codes),
    ):
        records, meta = build(fetch)
        write_dataset(SEED_FILE_BY_METHOD[method], records, meta)
    drift = schema_drift()
    if drift:
        print("%d dataset(s) differ from SEED_DATASETS: update the schema constants." % drift)
        return 1
    print("every dataset matches SEED_DATASETS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
