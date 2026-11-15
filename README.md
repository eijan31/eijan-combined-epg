# Eijan Combined EPG

This project builds one XMLTV guide containing the complete Ganja guide plus Strong programme data for selected channels in categories 60 (Philippines), 43 (South Korea), and 995 (Japan).

**Duplicate policy:** if Ganja and Strong use the same XMLTV channel ID, Ganja is kept as the authoritative source for that ID.

## Install

1. Create a **public** GitHub repository named `eijan-combined-epg`.
2. Upload `build_epg.py`, `README.md`, and `.github/workflows/update-epg.yml`, preserving the folders.
3. In the repository, open **Settings → Secrets and variables → Actions**.
4. Add repository secrets named `STRONG_USERNAME` and `STRONG_PASSWORD`.
5. Open **Actions → Update combined EPG → Run workflow**.
6. After it succeeds, confirm `combined.xml.gz` appears in the repository.

## Playlist EPG URL

Replace `OWNER` with your GitHub username:

`https://raw.githubusercontent.com/OWNER/eijan-combined-epg/main/combined.xml.gz`

The workflow runs automatically every six hours. Scheduled GitHub runs are approximate, not exact.

## Security

Never commit Xtream credentials into the repository. Keep them only in GitHub Actions Secrets. The generated XMLTV file contains guide data, not stream URLs or account credentials.
