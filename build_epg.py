import csv
import gzip
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# ============================================================
# CONFIGURATION
# ============================================================

GANJA_EPG_URL = (
    "https://github.com/ferteque/"
    "Curated-M3U-Repository/raw/refs/heads/main/epg6.xml.gz"
)
STRONG_SERVER = "http://cf.hsaurascdk87.xyz"
STRONG_USERNAME = os.environ.get("STRONG_USERNAME", "")
STRONG_PASSWORD = os.environ.get("STRONG_PASSWORD", "")

CATEGORY_IDS = {
    "60": {"country": "PHILIPPINES", "suffix": ".ph", "dummy_prefix": "strong.ph"},
    "43": {"country": "SOUTH KOREA", "suffix": ".kr", "dummy_prefix": "strong.kr"},
    "995": {"country": "JAPAN", "suffix": ".jp", "dummy_prefix": "strong.jp"},
}

OUTPUT = "combined.xml.gz"
REPORT = "strong_epg_match_report.csv"
MAP_OUTPUT = "strong_epg_map.json"


# ============================================================
# DOWNLOAD / API
# ============================================================

def download(url, timeout=300):
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 EPG-Builder"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def strong_api(action, extra=None):
    if not STRONG_USERNAME or not STRONG_PASSWORD:
        raise RuntimeError("Missing STRONG_USERNAME or STRONG_PASSWORD GitHub Secrets.")
    params = {
        "username": STRONG_USERNAME,
        "password": STRONG_PASSWORD,
        "action": action,
    }
    if extra:
        params.update(extra)
    url = (
        STRONG_SERVER.rstrip("/")
        + "/player_api.php?"
        + urllib.parse.urlencode(params)
    )
    data = download(url)
    try:
        return json.loads(data.decode("utf-8-sig"))
    except Exception as exc:
        raise RuntimeError(f"Strong API returned invalid JSON for {action}: {exc}")


def get_selected_streams():
    selected = []
    for category_id, settings in CATEGORY_IDS.items():
        country = settings["country"]
        print(f"Fetching Strong {country} streams...")
        streams = strong_api("get_live_streams", {"category_id": category_id})
        if not isinstance(streams, list):
            raise RuntimeError(f"Invalid Strong stream list for {country}.")
        for stream in streams:
            selected.append({
                "category_id": category_id,
                "country": country,
                "suffix": settings["suffix"],
                "dummy_prefix": settings["dummy_prefix"],
                "name": str(stream.get("name", "")).strip(),
                "stream_id": str(stream.get("stream_id", "")).strip(),
                "epg_channel_id": str(stream.get("epg_channel_id", "") or "").strip(),
            })
    print(f"Total selected Strong streams: {len(selected)}")
    return selected


# ============================================================
# CONSERVATIVE CHANNEL MATCHING
# ============================================================

QUALITY_WORDS = {
    "HD", "FHD", "UHD", "4K", "8K", "SD", "RAW", "VIP",
    "HEVC", "H264", "H265", "LIVE"
}


def normalize_name(value):
    value = str(value or "").upper()
    value = re.sub(r"^[A-Z]{2}\s*:\s*", "", value)
    for word in QUALITY_WORDS:
        value = re.sub(rf"\b{re.escape(word)}\b", " ", value)
    value = re.sub(r"[\(\[].*?[\)\]]", " ", value)
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return " ".join(value.split())


def read_strong_xmltv(xml_data):
    print("Reading Strong XMLTV feed...")
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as exc:
        raise RuntimeError(f"Strong XMLTV is not valid XML: {exc}")

    channels = {}
    for element in root.findall("channel"):
        channel_id = element.attrib.get("id", "").strip()
        names = [
            child.text.strip()
            for child in element.findall("display-name")
            if child.text and child.text.strip()
        ]
        if channel_id:
            channels[channel_id] = {"element": element, "names": names}

    programmes_by_channel = {}
    for programme in root.findall("programme"):
        channel_id = programme.attrib.get("channel", "").strip()
        if channel_id:
            programmes_by_channel.setdefault(channel_id, []).append(programme)

    print(f"Total Strong XMLTV channels: {len(channels)}")
    for suffix in (".ph", ".kr", ".jp"):
        count = sum(cid.lower().endswith(suffix) for cid in channels)
        print(f"XMLTV IDs ending in {suffix}: {count}")
    return root, channels, programmes_by_channel


def exact_country_match(stream, xmltv_channels):
    """Return one unambiguous exact normalized match, otherwise None."""
    wanted = normalize_name(stream["name"])
    if not wanted:
        return None

    suffix = stream["suffix"].lower()
    matches = []

    for channel_id, channel in xmltv_channels.items():
        if not channel_id.lower().endswith(suffix):
            continue
        candidate_names = list(channel["names"])
        candidate_names.append(channel_id)
        if any(normalize_name(name) == wanted for name in candidate_names):
            matches.append(channel_id)

    matches = sorted(set(matches))
    return matches[0] if len(matches) == 1 else None


def dummy_epg_id(stream):
    # Stable ID; same category + stream ID produces the same XMLTV ID every run.
    safe_stream_id = re.sub(r"[^A-Za-z0-9_-]", "_", stream["stream_id"])
    if not safe_stream_id:
        raise RuntimeError(f"Missing Strong stream_id for {stream['name']!r}")
    return f"{stream['dummy_prefix']}.{stream['category_id']}.{safe_stream_id}"


# ============================================================
# BUILD COMBINED XMLTV + STREAM-TO-EPG MAP
# ============================================================

def add_display_name(channel_element, name):
    display = ET.SubElement(channel_element, "display-name")
    display.text = name


def build_outputs(streams, strong_channels, programmes_by_channel):
    print("Downloading Ganja XMLTV...")
    compressed = download(GANJA_EPG_URL)
    try:
        ganja_xml = gzip.decompress(compressed)
    except Exception as exc:
        raise RuntimeError(f"Could not decompress Ganja XMLTV: {exc}")

    try:
        ganja_root = ET.fromstring(ganja_xml)
    except ET.ParseError as exc:
        raise RuntimeError(f"Ganja XMLTV is not valid XML: {exc}")

    if ganja_root.tag != "tv":
        raise RuntimeError("Ganja XMLTV root element is not <tv>.")

    print(
        f"Ganja source: {len(ganja_root.findall('channel')):,} channels, "
        f"{len(ganja_root.findall('programme')):,} programmes"
    )

    existing_ids = {
        element.attrib.get("id", "").strip()
        for element in ganja_root.findall("channel")
    }
    existing_programme_keys = {
        (
            p.attrib.get("channel", ""),
            p.attrib.get("start", ""),
            p.attrib.get("stop", ""),
        )
        for p in ganja_root.findall("programme")
    }

    mapping = {}
    report_rows = []
    matched = 0
    dummy = 0
    merged_programmes = 0

    for stream in streams:
        key = f"{stream['category_id']}:{stream['stream_id']}"
        matched_id = exact_country_match(stream, strong_channels)

        if matched_id and matched_id in existing_ids:
            # Do not override or duplicate a Ganja channel record.
            # Its existing EPG ID remains the source used by TiviMate.
            epg_id = matched_id
            status = "MATCHED_ID_ALREADY_IN_GANJA"
            matched += 1

        elif matched_id:
            epg_id = matched_id
            status = "MATCHED_EXACT_COUNTRY_SUFFIX"
            channel_source = strong_channels[matched_id]["element"]
            ganja_root.append(channel_source)
            existing_ids.add(matched_id)

            for programme in programmes_by_channel.get(matched_id, []):
                pkey = (
                    programme.attrib.get("channel", ""),
                    programme.attrib.get("start", ""),
                    programme.attrib.get("stop", ""),
                )
                if pkey not in existing_programme_keys:
                    ganja_root.append(programme)
                    existing_programme_keys.add(pkey)
                    merged_programmes += 1
            matched += 1

        else:
            epg_id = dummy_epg_id(stream)
            status = "DUMMY_NO_UNAMBIGUOUS_EXACT_MATCH"
            if epg_id not in existing_ids:
                channel_element = ET.Element("channel", {"id": epg_id})
                add_display_name(channel_element, stream["name"] or epg_id)
                ganja_root.append(channel_element)
                existing_ids.add(epg_id)
            dummy += 1

        mapping[key] = {
            "epg_id": epg_id,
            "status": status,
            "channel_name": stream["name"],
        }
        report_rows.append([
            stream["country"],
            stream["name"],
            stream["stream_id"],
            stream["epg_channel_id"],
            stream["suffix"],
            status,
            epg_id,
        ])

    # Write XMLTV (all original Ganja entries retained, plus verified Strong EPG
    # channel/programme records and empty dummy channel records).
    xml_output = ET.tostring(
        ganja_root, encoding="utf-8", xml_declaration=True
    )
    with open(OUTPUT, "wb") as f:
        f.write(gzip.compress(xml_output, compresslevel=6))

    with open(MAP_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(
            {"version": 1, "mappings": mapping},
            f,
            ensure_ascii=False,
            indent=2,
        )

    with open(REPORT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "country", "strong_channel", "strong_stream_id",
            "strong_epg_channel_id", "required_suffix", "result",
            "assigned_xmltv_id",
        ])
        writer.writerows(report_rows)

    print("----------------------------------------")
    print(f"Strong streams processed: {len(streams)}")
    print(f"Exact country-suffix matches: {matched}")
    print(f"Dummy EPG channels created: {dummy}")
    print(f"Strong programmes merged: {merged_programmes}")
    print(f"Combined XMLTV: {OUTPUT}")
    print(f"Stream mapping: {MAP_OUTPUT}")
    print(f"Report: {REPORT}")
    print("----------------------------------------")


def main():
    print("========================================")
    print("GANJA + STRONG COMBINED EPG BUILDER")
    print("Exact matches only; country suffixes .ph / .kr / .jp")
    print("Unmatched/ambiguous channels receive empty dummy EPG entries")
    print("========================================")

    streams = get_selected_streams()
    print("Downloading Strong XMLTV...")
    xmltv_url = (
        STRONG_SERVER.rstrip("/")
        + "/xmltv.php?"
        + urllib.parse.urlencode({
            "username": STRONG_USERNAME,
            "password": STRONG_PASSWORD,
        })
    )
    strong_xml_data = download(xmltv_url, timeout=300)
    print(f"Strong XMLTV downloaded: {len(strong_xml_data):,} bytes")

    _, strong_channels, programmes_by_channel = read_strong_xmltv(
        strong_xml_data
    )
    build_outputs(streams, strong_channels, programmes_by_channel)

    print("BUILD COMPLETED")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"BUILD FAILED: {error}", file=sys.stderr)
        raise
