
import gzip
import urllib.request
import xml.etree.ElementTree as ET

# ============================================================
# CONFIGURATION
# ============================================================

GANJA_EPG_URL = (
    "https://github.com/ferteque/"
    "Curated-M3U-Repository/raw/refs/heads/main/epg6.xml.gz"
)

DUMMY_EPG_URL = (
    "https://drive.google.com/uc?export=download&id="
    "18sCdvYM5-X9MF_kGD7jMCFP9R7yQG-do"
)

OUTPUT = "combined.xml.gz"


# ============================================================
# DOWNLOAD
# ============================================================

def download(url, timeout=300):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 EPG-Builder"}
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


# ============================================================
# BUILD COMBINED XMLTV
# ============================================================

def main():
    print("========================================")
    print("GANJA + STRONG DUMMY EPG BUILDER")
    print("========================================")

    # Download and decompress original Ganja EPG.
    print("Downloading Ganja XMLTV...")

    ganja_compressed = download(GANJA_EPG_URL)

    try:
        ganja_xml = gzip.decompress(ganja_compressed)
    except Exception as exc:
        raise RuntimeError(
            f"Could not decompress Ganja XMLTV: {exc}"
        )

    try:
        ganja_root = ET.fromstring(ganja_xml)
    except ET.ParseError as exc:
        raise RuntimeError(
            f"Ganja XMLTV is invalid: {exc}"
        )

    if ganja_root.tag != "tv":
        raise RuntimeError("Ganja XMLTV root is not <tv>.")

    original_channels = len(ganja_root.findall("channel"))
    original_programmes = len(ganja_root.findall("programme"))

    print(f"Ganja channels: {original_channels:,}")
    print(f"Ganja programmes: {original_programmes:,}")

    # Record existing channel IDs.
    existing_ids = {
        channel.attrib.get("id", "").strip()
        for channel in ganja_root.findall("channel")
    }

    # Download dummy XMLTV from Google Drive.
    print("Downloading Strong dummy XMLTV...")

    dummy_xml = download(DUMMY_EPG_URL)

    try:
        dummy_root = ET.fromstring(dummy_xml)
    except ET.ParseError as exc:
        raise RuntimeError(
            f"Dummy XMLTV is invalid: {exc}"
        )

    if dummy_root.tag != "tv":
        raise RuntimeError("Dummy XMLTV root is not <tv>.")

    dummy_channels = dummy_root.findall("channel")

    print(f"Dummy channels received: {len(dummy_channels):,}")

    # Append dummy channels without replacing Ganja channels.
    added = 0
    duplicates = 0

    for channel in dummy_channels:
        channel_id = channel.attrib.get("id", "").strip()

        if not channel_id:
            continue

        if channel_id in existing_ids:
            duplicates += 1
            continue

        ganja_root.append(channel)
        existing_ids.add(channel_id)
        added += 1

    # Verify all expected dummy IDs are present.
    missing = []

    for channel in dummy_channels:
        channel_id = channel.attrib.get("id", "").strip()

        if channel_id and channel_id not in existing_ids:
            missing.append(channel_id)

    if missing:
        raise RuntimeError(
            f"{len(missing)} dummy channel IDs are missing."
        )

    # Generate combined XMLTV.
    print("Generating combined XMLTV...")

    xml_output = ET.tostring(
        ganja_root,
        encoding="utf-8",
        xml_declaration=True
    )

    with open(OUTPUT, "wb") as output_file:
        output_file.write(
            gzip.compress(xml_output, compresslevel=6)
        )

    final_channels = len(ganja_root.findall("channel"))
    final_programmes = len(ganja_root.findall("programme"))

    print("----------------------------------------")
    print(f"Original Ganja channels: {original_channels:,}")
    print(f"Dummy channels received: {len(dummy_channels):,}")
    print(f"Dummy channels added: {added:,}")
    print(f"Duplicate IDs skipped: {duplicates:,}")
    print(f"Final XMLTV channels: {final_channels:,}")
    print(f"Final XMLTV programmes: {final_programmes:,}")
    print(f"Output file: {OUTPUT}")
    print("----------------------------------------")

    if added + duplicates != len(dummy_channels):
        raise RuntimeError(
            "Dummy channel count verification failed."
        )

    print("BUILD COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    main()
