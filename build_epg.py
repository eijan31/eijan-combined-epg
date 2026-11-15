
import gzip
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

# ============================================================
# CONFIGURATION
# ============================================================

GANJA_EPG_URL = (
    "https://github.com/ferteque/"
    "Curated-M3U-Repository/raw/refs/heads/main/epg6.xml.gz"
)

DUMMY_FILE_ID = "18sCdvYM5-X9MF_kGD7jMCFP9R7yQG-do"

DUMMY_EPG_URLS = [
    (
        "https://drive.usercontent.google.com/download"
        f"?id={DUMMY_FILE_ID}&export=download&confirm=t"
    ),
    (
        "https://drive.google.com/uc"
        f"?export=download&id={DUMMY_FILE_ID}&confirm=t"
    ),
]

OUTPUT = "combined.xml.gz"


# ============================================================
# DOWNLOAD
# ============================================================

def download(url, timeout=300):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 EPG-Builder",
            "Accept": "application/xml,text/xml,*/*",
        }
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
        content_type = response.headers.get("Content-Type", "")

        print(f"HTTP status: {response.status}")
        print(f"Content type: {content_type}")
        print(f"Downloaded: {len(data):,} bytes")

        return data


def download_dummy_xml():
    errors = []

    for url in DUMMY_EPG_URLS:
        print("Trying Google Drive download endpoint...")

        try:
            data = download(url)

            # Remove UTF-8 BOM if present.
            data = data.lstrip(b"\xef\xbb\xbf").strip()

            # Detect Google Drive HTML confirmation/error pages.
            preview = data[:500].lower()

            if (
                b"<html" in preview
                or b"<!doctype html" in preview
                or b"<head" in preview
            ):
                raise RuntimeError(
                    "Google Drive returned an HTML page instead "
                    "of the XMLTV file."
                )

            # Validate the actual XML before accepting it.
            root = ET.fromstring(data)

            if root.tag != "tv":
                raise RuntimeError(
                    f"Unexpected XML root element: {root.tag}"
                )

            return root

        except Exception as exc:
            message = str(exc)
            errors.append(message)
            print(f"Download attempt failed: {message}")

    raise RuntimeError(
        "Could not download a valid dummy XMLTV file from Google Drive.\n"
        + "\n".join(errors)
    )


# ============================================================
# BUILD COMBINED XMLTV
# ============================================================

def main():
    print("========================================")
    print("GANJA + STRONG DUMMY EPG BUILDER")
    print("========================================")

    # Download and decompress original Ganja EPG.
    print("\nDownloading Ganja XMLTV...")

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

    # Download and validate dummy XMLTV.
    print("\nDownloading Strong dummy XMLTV...")

    dummy_root = download_dummy_xml()
    dummy_channels = dummy_root.findall("channel")

    if not dummy_channels:
        raise RuntimeError(
            "The dummy XMLTV file contains no channel elements."
        )

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

    # Verify every dummy channel ID is present.
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
    print("\nGenerating combined XMLTV...")

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

    print("\n----------------------------------------")
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

    print("\nBUILD COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    main()
