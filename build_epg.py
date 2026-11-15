#!/usr/bin/env python3
"""Build a filtered combined XMLTV guide: full Ganja + selected Strong channels."""
import gzip, json, os, sys, tempfile, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

GANJA_EPG_URL = "https://github.com/ferteque/Curated-M3U-Repository/raw/refs/heads/main/epg6.xml.gz"
STRONG_SERVER = "http://cf.hsaurascdk87.xyz"
CATEGORY_IDS = ["60", "43", "995"]
OUTPUT = "combined.xml.gz"

def download(url, path, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "EijanCombinedEPG/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response, open(path, "wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)

def strong_api(action, category_id=None):
    params = {
        "username": os.environ["STRONG_USERNAME"],
        "password": os.environ["STRONG_PASSWORD"],
        "action": action,
    }
    if category_id is not None:
        params["category_id"] = str(category_id)
    url = STRONG_SERVER + "/player_api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "EijanCombinedEPG/1.0"})
    with urllib.request.urlopen(req, timeout=180) as response:
        data = json.loads(response.read().decode("utf-8"))
    if isinstance(data, dict) and data.get("user_info", {}).get("auth") == 0:
        raise RuntimeError("Strong rejected the Xtream credentials.")
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected Strong API response for {action}.")
    return data

def get_selected_epg_ids():
    ids = set()
    for category_id in CATEGORY_IDS:
        for stream in strong_api("get_live_streams", category_id):
            value = str(stream.get("epg_channel_id") or "").strip()
            if value:
                ids.add(value)
    if not ids:
        raise RuntimeError("No EPG IDs found in Strong categories 60, 43 and 995.")
    print(f"Found {len(ids)} distinct Strong EPG IDs.")
    return ids

def copy_xmltv_children(source, out, wanted_ids=None, seen_channels=None):
    """Stream channel/programme elements; retain all if wanted_ids is None."""
    depth = 0
    root_element = None
    root_attrs = {}
    channel_count = programme_count = 0

    for event, elem in ET.iterparse(source, events=("start", "end")):
        if event == "start":
            depth += 1
            if depth == 1:
                root_element = elem
                root_attrs = dict(elem.attrib)
            continue

        if depth == 2:
            tag = elem.tag.rsplit("}", 1)[-1] if isinstance(elem.tag, str) else ""
            keep = False
            if tag == "channel":
                channel_id = str(elem.attrib.get("id", "")).strip()
                if wanted_ids is None:
                    keep = True
                    if seen_channels is not None and channel_id:
                        seen_channels.add(channel_id)
                else:
                    keep = bool(channel_id and channel_id in wanted_ids)
                if keep:
                    channel_count += 1
            elif tag == "programme":
                channel_id = str(elem.attrib.get("channel", "")).strip()
                keep = wanted_ids is None or channel_id in wanted_ids
                if keep:
                    programme_count += 1

            if keep:
                out.write(ET.tostring(elem, encoding="unicode"))
                out.write("\n")
            elem.clear()
            if root_element is not None:
                root_element.clear()
        depth -= 1

    return channel_count, programme_count, root_attrs

def main():
    if not os.environ.get("STRONG_USERNAME") or not os.environ.get("STRONG_PASSWORD"):
        raise RuntimeError("Set STRONG_USERNAME and STRONG_PASSWORD in GitHub Actions Secrets.")

    strong_ids = get_selected_epg_ids()
    with tempfile.TemporaryDirectory() as tmp:
        gz_path = os.path.join(tmp, "ganja.xml.gz")
        ganja_path = os.path.join(tmp, "ganja.xml")
        strong_path = os.path.join(tmp, "strong.xml")
        body_path = os.path.join(tmp, "body.xml")
        final_path = os.path.join(tmp, "combined.xml")

        print("Downloading Ganja XMLTV...")
        download(GANJA_EPG_URL, gz_path)
        print("Decompressing Ganja XMLTV...")
        with gzip.open(gz_path, "rb") as src, open(ganja_path, "wb") as dst:
            while True:
                block = src.read(1024 * 1024)
                if not block:
                    break
                dst.write(block)

        print("Downloading Strong XMLTV...")
        strong_url = STRONG_SERVER + "/xmltv.php?" + urllib.parse.urlencode({
            "username": os.environ["STRONG_USERNAME"],
            "password": os.environ["STRONG_PASSWORD"],
        })
        download(strong_url, strong_path)

        # Ganja is authoritative for duplicate XMLTV channel IDs.
        ganja_channel_ids = set()
        with open(body_path, "w", encoding="utf-8", newline="\n") as out:
            g_ch, g_pr, root_attrs = copy_xmltv_children(
                ganja_path, out, wanted_ids=None, seen_channels=ganja_channel_ids
            )
            strong_only_ids = strong_ids - ganja_channel_ids
            if strong_only_ids:
                s_ch, s_pr, _ = copy_xmltv_children(
                    strong_path, out, wanted_ids=strong_only_ids
                )
            else:
                s_ch = s_pr = 0
            out.write("</tv>\n")

        attrs = " ".join(f"{key}={quoteattr(str(value))}" for key, value in root_attrs.items())
        opening = ("<tv " + attrs + ">\n") if attrs else "<tv>\n"
        with open(final_path, "wb") as dst:
            dst.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            dst.write(opening.encode("utf-8"))
            with open(body_path, "rb") as src:
                while True:
                    block = src.read(1024 * 1024)
                    if not block:
                        break
                    dst.write(block)

        # Stable gzip metadata avoids a new commit when content is unchanged.
        with open(final_path, "rb") as src, gzip.GzipFile(OUTPUT, "wb", mtime=0) as gz:
            while True:
                block = src.read(1024 * 1024)
                if not block:
                    break
                gz.write(block)

    print("Combined EPG completed.")
    print(f"Ganja retained: {g_ch} channels / {g_pr} programmes")
    print(f"Strong added: {s_ch} channels / {s_pr} programmes")
    print(f"Strong EPG IDs requested: {len(strong_ids)}")
    print(f"Output: {OUTPUT} ({os.path.getsize(OUTPUT):,} bytes)")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"BUILD FAILED: {error}", file=sys.stderr)
        raise
