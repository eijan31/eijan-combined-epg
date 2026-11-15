# Eijan Combined EPG — Ganja + Strong (PH / KR / JP)

This package contains the GitHub Actions XMLTV builder and the companion Google Apps Script playlist merger.

## Files

- `build_epg.py` — downloads the Ganja and Strong XMLTV feeds, preserves Ganja's guide, and adds Strong guide data only for unambiguous exact channel-name matches in the correct country-suffix group (`.ph`, `.kr`, `.jp`). Unmatched or ambiguous Strong channels receive a dummy XMLTV channel named after the Strong channel, with no programme listings.
- `.github/workflows/update-epg.yml` — runs the builder manually or every six hours and publishes all three generated files.
- `google-apps-script/Code.gs` — companion Apps Script for updating the master M3U playlist and assigning each Strong stream its mapped or dummy `tvg-id`.

## Install in GitHub

1. Extract this ZIP on your computer first. GitHub's normal repository upload does not unpack a ZIP automatically.
2. Upload the **contents** of the extracted folder into the root of your `eijan-combined-epg` repository. Preserve the `.github/workflows/` folder structure. The `google-apps-script` folder is included as a backup/reference; it is not required by the GitHub Actions workflow.
3. In GitHub, open **Settings → Secrets and variables → Actions** and create these repository secrets:
   - `STRONG_USERNAME`
   - `STRONG_PASSWORD`
4. Open **Actions → Update combined EPG → Run workflow**.
5. When it succeeds, confirm these files appear in the repository root:
   - `combined.xml.gz`
   - `strong_epg_match_report.csv`
   - `strong_epg_map.json`

## Run schedule

The workflow runs every six hours (`17 */6 * * *`) and can also be started manually from the Actions tab.

## Apps Script setup

Use `google-apps-script/Code.gs` as the companion playlist merger. Review its `SETTINGS`, enter your current Strong credentials there if the script requires them, then run `saveInitialConfig()` and `runDaily()` as directed by the script. Do not commit credentials to GitHub. Keep the Google Drive master M3U private because stream URLs can contain account credentials.

## Combined EPG URL

After the first successful workflow run, the EPG URL is:

`https://raw.githubusercontent.com/eijan31/eijan-combined-epg/main/combined.xml.gz`

The mapping JSON URL used by the Apps Script is:

`https://raw.githubusercontent.com/eijan31/eijan-combined-epg/main/strong_epg_map.json`

## Matching policy

- PH streams are checked only against Strong XMLTV channel IDs ending in `.ph`.
- KR streams are checked only against IDs ending in `.kr`.
- JP streams are checked only against IDs ending in `.jp`.
- Only a unique exact normalized channel-name match is accepted.
- Fuzzy suggestions are not automatically assigned. No unique exact match means a dummy channel entry with no programmes.
- If a matched channel ID already exists in Ganja, the existing Ganja guide is retained for that ID.

## Security

Never put Xtream credentials in `build_epg.py`, the workflow file, or any committed file. Store the GitHub Actions credentials only in repository Secrets. If credentials were previously exposed in chat or code, rotate them.
