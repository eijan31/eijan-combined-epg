/**
 * GANJA + STRONG CLOUD PLAYLIST MERGER
 * Google Apps Script — runs in Google's cloud, no PC required.
 *
 * SETUP:
 * 1) Put your Drive file IDs and Strong credentials in saveInitialConfig().
 * 2) Run saveInitialConfig() once.
 * 3) Run testGanjaSource(), then listStrongCategories().
 * 4) Copy the category IDs you want into SELECTED_STRONG_CATEGORY_IDS.
 * 5) Run runDaily() manually once to test.
 * 6) Run installDailyTrigger() once.
 */

const SETTINGS = {
  // The ID is the long string between /d/ and /view in a Google Drive file URL.
  GANJA_FILE_ID: '1jmg6A7jWqvHi84ycm-k_chiPBNsOCAfG',

  // Create an empty .m3u file in Drive for the output, then paste its file ID.
  // The script updates this same file so the master URL/file ID stays stable.
  MASTER_FILE_ID: '1UbI_RnkAgQ9cKyUAR0O9e0Rcecjy-0hF',
  EPG_URL: 'https://raw.githubusercontent.com/eijan31/eijan-combined-epg/main/combined.xml.gz',
  EPG_MAP_URL: 'https://raw.githubusercontent.com/eijan31/eijan-combined-epg/main/strong_epg_map.json',

  // Strong Xtream Codes connection.
  STRONG_SERVER: 'http://cf.hsaurascdk87.xyz',
  STRONG_USERNAME: 'PASTE_YOUR_STRONG_USERNAME',
  STRONG_PASSWORD: 'PASTE_YOUR_STRONG_PASSWORD',

  // These are matched against Strong's live category names (case-insensitive exact match).
  // If Strong's labels are longer (e.g. 'PH - Philippines'), use the exact labels instead.
  SELECTED_STRONG_CATEGORY_IDS: ['60', '43', '995'],
  SELECTED_STRONG_CATEGORY_NAMES: ['PH| PHILIPINES ᴴᴰ/ᴿᴬᵂ', 'KR| SOUTH KOREA', 'JP| JAPAN HD/4K'],
  // The script resolves the category names to current provider IDs each run.

  // Categories displayed first, in this exact order.
  // All other Ganja categories retain their original order.
  CATEGORY_ORDER: [
    'EPGenius',
    'News Networks',
    'Sport Networks',
    'TV Guide (USA)',
    'TV Guide (UK)',
    'TV Guide (Canada)',
    'TV Guide (Australia)',
    'PH| PHILIPINES',
    'KR| SOUTH KOREA',
    'JP| JAPAN HD/4K',
    'Tennis',
    'NFL Sunday Ticket',
    'NBA League Pass',
    'MLB.tv',
    'College Football',
    'WNBA League Pass',
    'College Basketball',
    'NHL Center Ice',
    'PPV Event 2026',
    'MLS Direct Kick',
    'PPV Event',
    'Formula 1',
    'Sports PPV',
    'FIFA+',
    'Golf',
    'UFC Fight Pass',
    'UEFA'
  ],
  // Preserve the original Ganja entries and append selected Strong channels.
  // Exact stream URL duplicates are skipped; same-name/different-URL channels remain.
  KEEP_BACKUPS: true,
  BACKUP_FOLDER_NAME: 'Playlist Merger Backups',
  TIMEZONE: 'Asia/Manila',
  DAILY_HOUR: 4
};


/** Run once after editing SETTINGS above. Stores config in Script Properties. */
function saveInitialConfig() {
  validateSettings_(false);
  PropertiesService.getScriptProperties().setProperty('MERGER_SETTINGS', JSON.stringify(SETTINGS));
  Logger.log('Settings saved. Credentials are stored in this private Apps Script project.');
}


/** Checks that the configured Ganja file can be read. */
function testGanjaSource() {
  const cfg = getConfig_();
  const file = DriveApp.getFileById(cfg.GANJA_FILE_ID);
  const text = file.getBlob().getDataAsString('UTF-8');
  const parsed = parseM3u_(text);
  if (!parsed.entries.length) throw new Error('Ganja file contains no recognizable #EXTINF entries.');
  Logger.log('Ganja OK: ' + file.getName() + ' | ' + parsed.entries.length + ' entries | ' + text.length + ' characters');
}


/** Run this first to see Strong's category IDs and names in the execution log. */
function listStrongCategories() {
  const cfg = getConfig_();
  const categories = xtreamGet_(cfg, 'get_live_categories');
  if (!Array.isArray(categories)) throw new Error('Strong did not return a category list. Check server URL and credentials.');
  categories.forEach(c => Logger.log('ID: ' + c.category_id + ' | CATEGORY: ' + c.category_name));
  Logger.log('Total Strong live-TV categories: ' + categories.length);
  return categories;
}


/** Main job: read latest Ganja file, fetch selected Strong categories, update stable master file. */
function runDaily() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) {
    Logger.log('Another merger run is active; this run is skipped.');
    return;
  }
  try {
    const cfg = getConfig_();
    if (!cfg.SELECTED_STRONG_CATEGORY_IDS || !cfg.SELECTED_STRONG_CATEGORY_IDS.length) {
      throw new Error('No Strong categories selected. Edit SETTINGS.SELECTED_STRONG_CATEGORY_IDS, run saveInitialConfig(), then run runDaily().');
    }

    const ganjaFile = DriveApp.getFileById(cfg.GANJA_FILE_ID);
    const ganjaText = ganjaFile.getBlob().getDataAsString('UTF-8');
    const ganja = parseM3u_(ganjaText);
    if (!ganja.entries.length) throw new Error('Ganja source is empty or invalid; master was not changed.');

    // Load the latest Python-generated stream-to-EPG map before changing the master.
    const epgMap = fetchStrongEpgMap_(cfg);

    const categories = xtreamGet_(cfg, 'get_live_categories');
    const categoryMap = {};
    categories.forEach(c => categoryMap[String(c.category_id)] = String(c.category_name || 'Strong'));

    const strongEntries = [];
    cfg.SELECTED_STRONG_CATEGORY_IDS.forEach(id => {
      const categoryName = categoryMap[String(id)];
      if (!categoryName) throw new Error('Selected Strong category ID no longer exists: ' + id + '. Run listStrongCategories() and update selection.');
      const streams = xtreamGet_(cfg, 'get_live_streams', String(id));
      if (!Array.isArray(streams)) throw new Error('Invalid stream response for Strong category ' + id);
      streams.forEach(stream => strongEntries.push(makeStrongEntry_(stream, categoryName, cfg, String(id), epgMap)));
    });

    const seen = {};
    ganja.entries.forEach(entry => {
      const url = entryUrl_(entry);
      if (url) seen[url] = true;
    });

    const additions = [];
    strongEntries.forEach(entry => {
      const url = entryUrl_(entry);
      if (url && !seen[url]) {
        seen[url] = true;
        additions.push(entry);
      }
    });

    const allEntries = sortEntriesByCategory_(
  ganja.entries.concat(additions),
  cfg.CATEGORY_ORDER || []
);
    const outputHeader = buildM3uHeader_(ganja.header, cfg.EPG_URL);

const output = outputHeader + '\n' +
  allEntries.map(e => e.join('\n')).join('\n') + '\n';

    const masterFile = DriveApp.getFileById(cfg.MASTER_FILE_ID);
    if (cfg.KEEP_BACKUPS) createBackup_(masterFile, cfg.BACKUP_FOLDER_NAME);

    // DriveApp File.setContent has a 10 MB content limit. Fail safely before changing master.
    if (output.length > 9.5 * 1024 * 1024) {
      throw new Error('Generated playlist is close to/exceeds DriveApp setContent limit. Master was not changed; use a Drive API resumable update implementation for larger files.');
    }
    masterFile.setContent(output);

    const summary = {
      ranAt: new Date().toISOString(),
      ganjaEntries: ganja.entries.length,
      strongFetched: strongEntries.length,
      strongAdded: additions.length,
      outputEntries: allEntries.length,
      masterFile: masterFile.getName()
    };
    PropertiesService.getScriptProperties().setProperty('LAST_SUCCESS', JSON.stringify(summary));
    Logger.log('SUCCESS: ' + JSON.stringify(summary));
  } catch (err) {
    Logger.log('FAILED: ' + (err && err.stack ? err.stack : err));
    throw err;
  } finally {
    lock.releaseLock();
  }
}


/** Creates/replaces this project's daily trigger. Run once after a successful manual test. */
function installDailyTrigger() {
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'runDaily') {
      ScriptApp.deleteTrigger(t);
    }
  });

  ScriptApp.newTrigger('runDaily')
    .timeBased()
    .everyHours(6)
    .create();

  Logger.log('Automatic playlist update installed: every 6 hours.');
}


/** Optional: view last successful run in logs. */
function showLastSuccess() {
  Logger.log(PropertiesService.getScriptProperties().getProperty('LAST_SUCCESS') || 'No successful run recorded yet.');
}


/* ------------------------- internal helpers ------------------------- */

function getConfig_() {
  const raw = PropertiesService.getScriptProperties().getProperty('MERGER_SETTINGS');
  if (!raw) throw new Error('Run saveInitialConfig() first.');
  const cfg = JSON.parse(raw);
  validateConfig_(cfg);
  return cfg;
}

function validateSettings_(requireCategories) {
  validateConfig_(SETTINGS, requireCategories);
}

function validateConfig_(cfg, requireCategories) {
  ['GANJA_FILE_ID', 'MASTER_FILE_ID', 'STRONG_SERVER', 'STRONG_USERNAME', 'STRONG_PASSWORD'].forEach(k => {
    if (!cfg[k] || String(cfg[k]).indexOf('PASTE_') === 0 || String(cfg[k]).indexOf('YOUR_') >= 0) {
      throw new Error('Please replace SETTINGS.' + k + ' with your actual value.');
    }
  });
  if (requireCategories && (!cfg.SELECTED_STRONG_CATEGORY_IDS || !cfg.SELECTED_STRONG_CATEGORY_IDS.length)) {
    throw new Error('Select at least one Strong category.');
  }
}

function xtreamGet_(cfg, action, categoryId) {
  let server = String(cfg.STRONG_SERVER).trim().replace(/\/+$/, '');
  if (!/^https?:\/\//i.test(server)) server = 'http://' + server;
  const params = {
    username: cfg.STRONG_USERNAME,
    password: cfg.STRONG_PASSWORD,
    action: action
  };
  if (categoryId !== undefined) params.category_id = categoryId;
  const query = Object.keys(params).map(k => encodeURIComponent(k) + '=' + encodeURIComponent(params[k])).join('&');
  const url = server + '/player_api.php?' + query;
  const response = UrlFetchApp.fetch(url, {muteHttpExceptions: true, followRedirects: true});
  const code = response.getResponseCode();
  if (code < 200 || code >= 300) throw new Error('Strong API HTTP ' + code + ' for ' + action);
  const body = response.getContentText();
  let parsed;
  try { parsed = JSON.parse(body); } catch (e) { throw new Error('Strong returned non-JSON data for ' + action + ': ' + body.slice(0, 300)); }
  if (parsed && !Array.isArray(parsed) && parsed.user_info && parsed.user_info.auth === 0) {
    throw new Error('Strong rejected the Xtream credentials.');
  }
  return parsed;
}

function parseM3u_(text) {
  const lines = String(text || '').replace(/^\uFEFF/, '').split(/\r?\n/);
  let header = '#EXTM3U';
  const entries = [];
  let current = null;
  lines.forEach(line => {
    if (line.indexOf('#EXTM3U') === 0) { header = line; return; }
    if (line.indexOf('#EXTINF:') === 0) {
      if (current) entries.push(current);
      current = [line];
    } else if (current) {
      current.push(line);
    }
  });
  if (current) entries.push(current);
  return {header: header, entries: entries.filter(e => entryUrl_(e))};
}

function entryUrl_(entry) {
  for (let i = entry.length - 1; i >= 0; i--) {
    const line = String(entry[i]).trim();
    if (line && line.charAt(0) !== '#') return line;
  }
  return '';
}

function fetchStrongEpgMap_(cfg) {
  if (!cfg.EPG_MAP_URL) throw new Error('EPG_MAP_URL is missing from SETTINGS.');
  const response = UrlFetchApp.fetch(cfg.EPG_MAP_URL, {
    muteHttpExceptions: true,
    followRedirects: true,
    headers: {'Cache-Control': 'no-cache'}
  });
  const code = response.getResponseCode();
  if (code < 200 || code >= 300) {
    throw new Error('Could not download Strong EPG mapping JSON. HTTP ' + code +
      '. Run the GitHub Actions EPG workflow first; master playlist was not changed.');
  }
  let parsed;
  try {
    parsed = JSON.parse(response.getContentText());
  } catch (err) {
    throw new Error('Strong EPG mapping file is not valid JSON; master was not changed.');
  }
  if (!parsed || !parsed.mappings || typeof parsed.mappings !== 'object') {
    throw new Error('Strong EPG mapping JSON has no mappings object; master was not changed.');
  }
  Logger.log('Loaded Strong EPG mappings: ' + Object.keys(parsed.mappings).length);
  return parsed.mappings;
}

function makeDummyEpgId_(categoryId, streamId) {
  const prefixes = {
    '60': 'strong.ph',
    '43': 'strong.kr',
    '995': 'strong.jp'
  };
  const prefix = prefixes[String(categoryId)];
  if (!prefix) throw new Error('No dummy EPG prefix configured for Strong category ' + categoryId);
  const safeId = String(streamId).replace(/[^A-Za-z0-9_-]/g, '_');
  return prefix + '.' + String(categoryId) + '.' + safeId;
}

function makeStrongEntry_(s, categoryName, cfg, categoryId, epgMap) {
  const id = s.stream_id;
  if (id === undefined || id === null) throw new Error('Strong stream record has no stream_id.');
  const extension = String(s.container_extension || 'ts').replace(/^\./, '');
  let server = String(cfg.STRONG_SERVER).trim().replace(/\/+$/, '');
  if (!/^https?:\/\//i.test(server)) server = 'http://' + server;
  const streamUrl = server + '/live/' + encodeURIComponent(cfg.STRONG_USERNAME) + '/' +
    encodeURIComponent(cfg.STRONG_PASSWORD) + '/' + encodeURIComponent(String(id)) + '.' + encodeURIComponent(extension);
  const name = cleanAttr_(s.name || ('Channel ' + id));
  const logo = cleanAttr_(s.stream_icon || '');
  const mapKey = String(categoryId) + ':' + String(id);
  const mapped = epgMap && epgMap[mapKey] ? epgMap[mapKey].epg_id : '';
  const epg = cleanAttr_(mapped || makeDummyEpgId_(categoryId, id));
  const group = cleanAttr_(categoryName);
  const extinf = '#EXTINF:-1 tvg-id="' + epg + '" tvg-name="' + name +
    '" tvg-logo="' + logo + '" group-title="' + group + '",' + name;
  return [extinf, streamUrl];
}

function cleanAttr_(value) {
  return String(value).replace(/"/g, "'").replace(/[\r\n]/g, ' ');
}

function createBackup_(file, folderName) {
  const parentIter = file.getParents();
  const parent = parentIter.hasNext() ? parentIter.next() : DriveApp.getRootFolder();
  const folders = parent.getFoldersByName(folderName);
  const folder = folders.hasNext() ? folders.next() : parent.createFolder(folderName);
  const stamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyyMMdd-HHmmss');
  file.makeCopy(file.getName() + '.backup-' + stamp, folder);
}

/**
 * Sorts priority categories first.
 * All other categories retain their original relative order.
 */
function sortEntriesByCategory_(entries, priorityCategories) {

  function normalize_(value) {
    return String(value || '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '');
  }

  function getGroup_(entry) {
    const extinf = entry.find(line =>
      String(line).indexOf('#EXTINF:') === 0
    ) || '';

    const match = extinf.match(/group-title="([^"]*)"/i);
    return match ? match[1] : '';
  }

  const priority = priorityCategories.map(normalize_);

  return entries
    .map((entry, index) => {
      const group = normalize_(getGroup_(entry));
      const rank = priority.indexOf(group);

      return {
        entry: entry,
        originalIndex: index,
        rank: rank === -1 ? priority.length : rank
      };
    })
    .sort((a, b) =>
      a.rank - b.rank || a.originalIndex - b.originalIndex
    )
    .map(item => item.entry);
}
function buildM3uHeader_(originalHeader, epgUrl) {
  let header = String(originalHeader || '#EXTM3U');

  // Remove any previous EPG URL attributes.
  header = header.replace(
    /\s+(?:x-tvg-url|url-tvg)=(?:"[^"]*"|'[^']*'|[^\s]*)/gi,
    ''
  );

  // Attach the current external XMLTV source.
  return header.trim() +
    ' x-tvg-url="' + cleanAttr_(epgUrl) + '"';
}

function testGanjaEPG() {
  const url = 'https://github.com/ferteque/Curated-M3U-Repository/raw/refs/heads/main/epg6.xml.gz';

  const response = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    followRedirects: true
  });

  const blob = response.getBlob();

  Logger.log('HTTP STATUS: ' + response.getResponseCode());
  Logger.log('CONTENT TYPE: ' + blob.getContentType());
  Logger.log('COMPRESSED SIZE: ' + blob.getBytes().length + ' bytes');

  if (response.getResponseCode() !== 200) {
    throw new Error('Could not download Ganja EPG.');
  }

  const xml = Utilities.ungzip(blob).getDataAsString('UTF-8');

  Logger.log('DECOMPRESSED SIZE: ' + xml.length + ' characters');
  Logger.log('VALID XMLTV: ' + /<tv[\s>]/i.test(xml));
  Logger.log('SAMPLE: ' + xml.substring(0, 300));
}