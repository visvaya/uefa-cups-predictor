#!/usr/bin/env node
// Weekly freshness check for the versioned items no dependency bot updates, run by
// .github/workflows/freshness.yml.
// Reads .github/freshness.json, the project's one list of versioned items and their mechanisms, and
// checks every item whose mechanism is "job": a pin (file + pattern, first capture group is the version)
// against the newest stable release on GitHub, npm or PyPI that is at least minimumReleaseAgeDays old.
// Usage: node scripts/check-freshness.mjs [path/to/freshness.json]   (GITHUB_TOKEN raises the API limit)
// Exit codes: 0 all current, 1 outdated item, unreadable pin or invalid list, 2 network or API failure.
import { readFileSync, realpathSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const DAY_MS = 24 * 60 * 60 * 1000;
const DEFAULT_LIST = '.github/freshness.json';
const MECHANISMS = new Set(['dependabot', 'check-latest', 'job', 'manual']);

/** Stable x.y.z inside a version or tag ("v1.2.3", "rust-v1.2.3"); undefined for pre-releases. */
export const parseVersion = (text) => {
  const match = /(?:^|[^0-9.])v?([0-9]+)[.]([0-9]+)[.]([0-9]+)(-[0-9A-Za-z.-]+)?(?![0-9A-Za-z.])/.exec(` ${text ?? ''}`);
  if (match === null || match[4] !== undefined) return undefined;
  return [Number(match[1]), Number(match[2]), Number(match[3])];
};

export const compareVersions = (a, b) => {
  const index = a.findIndex((part, i) => part !== b[i]);
  return index === -1 ? 0 : a[index] - b[index];
};

const show = (version) => version.join('.');

/** The newest stable release published at least minAgeDays before now, or undefined. */
export const newestEligible = (releases, { nowMs, minAgeDays }) =>
  releases
    .map((release) => ({ version: parseVersion(release.version), publishedMs: Date.parse(release.publishedAt) }))
    .filter((release) => release.version !== undefined && nowMs - release.publishedMs >= minAgeDays * DAY_MS)
    .map((release) => release.version)
    .reduce((best, version) => (best === undefined || compareVersions(version, best) > 0 ? version : best), undefined);

/** Parses the list at the boundary; returns { ok, value } or { ok: false, error }. */
export const parseList = (raw) => {
  const errors = [];
  const minimumReleaseAgeDays = raw?.minimumReleaseAgeDays ?? 7;
  if (!Number.isInteger(minimumReleaseAgeDays) || minimumReleaseAgeDays < 0)
    errors.push('minimumReleaseAgeDays must be a whole number of days');
  const items = Array.isArray(raw?.items) ? raw.items : [];
  if (items.length === 0) errors.push('items must list every versioned item of the project');
  items.forEach((item, index) => {
    const label = typeof item?.name === 'string' ? item.name : `item ${index + 1}`;
    if (typeof item?.name !== 'string') errors.push(`${label}: name is missing`);
    if (!MECHANISMS.has(item?.mechanism)) errors.push(`${label}: mechanism must be one of ${[...MECHANISMS].join(', ')}`);
    if (item?.mechanism !== 'job' && typeof item?.where !== 'string')
      errors.push(`${label}: where must say which configuration keeps it current`);
    if (item?.mechanism === 'job') {
      const check = item.check ?? {};
      const isPin = typeof check.file === 'string' && typeof check.pattern === 'string';
      const sources = ['github', 'npm', 'pypi'].filter((key) => typeof check[key] === 'string');
      if (!(isPin && sources.length === 1))
        errors.push(`${label}: a job check needs file, pattern and one of github, npm or pypi`);
      if (isPin && typeof item.howToBump !== 'string') errors.push(`${label}: howToBump is missing`);
    }
  });
  return errors.length > 0 ? { ok: false, error: errors } : { ok: true, value: { minimumReleaseAgeDays, items } };
};

/** The pinned version of a job item, or undefined when the pattern no longer matches. */
export const readPin = (text, pattern) => parseVersion(new RegExp(pattern, 'm').exec(text)?.[1]);

/** Outcome of a pin against the newest eligible release. */
export const pinResult = ({ pinned, newest, howToBump, minAgeDays }) => {
  if (pinned === undefined) return { status: 'unreadable', text: 'pin not found: fix file or pattern in the freshness list' };
  if (newest === undefined) return { status: 'ok', text: `pinned ${show(pinned)}, no release older than ${minAgeDays} days` };
  return compareVersions(newest, pinned) > 0
    ? { status: 'outdated', text: `pinned ${show(pinned)}, latest ${show(newest)}: ${howToBump}` }
    : { status: 'ok', text: `pinned ${show(pinned)}, latest ${show(newest)}` };
};

/** The printed report and the exit code for all items. */
export const formatReport = (results) => ({
  exitCode: results.some((result) => result.status !== 'ok') ? 1 : 0,
  text: `${results.map((result) => `${result.name}: ${result.status === 'ok' ? '' : `${result.status.toUpperCase()}, `}${result.text}`).join('\n')}\n`,
});

const githubReleases = async (fetchJson, repo) =>
  (await fetchJson(`https://api.github.com/repos/${repo}/releases?per_page=100`))
    .filter((release) => release.draft !== true && release.prerelease !== true)
    .map((release) => ({ version: release.tag_name, publishedAt: release.published_at }));

const pypiReleases = async (fetchJson, name) => {
  const doc = await fetchJson(`https://pypi.org/pypi/${name}/json`);
  return Object.entries(doc.releases ?? {})
    .filter(([, files]) => files.length > 0 && files.every((file) => file.yanked !== true))
    .map(([version, files]) => ({ version, publishedAt: files[0].upload_time_iso_8601 }));
};

const npmReleases = async (fetchJson, name) => {
  const doc = await fetchJson(`https://registry.npmjs.org/${name.replaceAll('/', '%2F')}`);
  return Object.keys(doc.versions ?? {}).map((version) => ({ version, publishedAt: doc.time?.[version] }));
};

const RELEASE_SOURCES = { github: githubReleases, npm: npmReleases, pypi: pypiReleases };

/** Checks every job item; I/O comes in as parameters so tests run without a network. */
export const checkItems = async ({ list, readText, fetchJson, nowMs }) => {
  const minAgeDays = list.minimumReleaseAgeDays;
  const jobs = list.items.filter((item) => item.mechanism === 'job');
  return Promise.all(
    jobs.map(async (item) => {
      const { check } = item;
      const pinned = readPin(readText(check.file), check.pattern);
      const source = Object.keys(RELEASE_SOURCES).find((key) => typeof check[key] === 'string');
      const releases = await RELEASE_SOURCES[source](fetchJson, check[source]);
      const newest = newestEligible(releases, { nowMs, minAgeDays });
      return { name: item.name, ...pinResult({ pinned, newest, howToBump: item.howToBump, minAgeDays }) };
    }),
  );
};

const fetchJsonWith = (token) => async (url) => {
  const github = url.startsWith('https://api.github.com/');
  const response = await fetch(url, {
    headers: {
      accept: github ? 'application/vnd.github+json' : 'application/json',
      'user-agent': 'freshness-check',
      ...(github && token ? { authorization: `Bearer ${token}` } : {}),
    },
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) throw new Error(`${response.status} from ${url}`);
  return response.json();
};

const main = async () => {
  const root = process.cwd();
  const readText = (file) => readFileSync(path.join(root, file), 'utf8');
  const listPath = process.argv[2] ?? DEFAULT_LIST;
  let list;
  try {
    list = parseList(JSON.parse(readFileSync(path.resolve(root, listPath), 'utf8')));
  } catch (error) {
    list = { ok: false, error: [`${listPath}: ${error.message}`] };
  }
  if (!list.ok) {
    process.stderr.write(`${list.error.join('\n')}\n`);
    return 1;
  }
  try {
    const results = await checkItems({
      list: list.value,
      readText,
      fetchJson: fetchJsonWith(process.env.GITHUB_TOKEN),
      nowMs: Date.now(),
    });
    const report = formatReport(results);
    process.stdout.write(report.text);
    return report.exitCode;
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    return error instanceof SyntaxError || error.code === 'ENOENT' ? 1 : 2;
  }
};

// Compared through realpath: Node reports a symlinked or junctioned script by its real path.
const isEntry = () => {
  try {
    return import.meta.url === pathToFileURL(realpathSync(process.argv[1] ?? '')).href;
  } catch {
    return false;
  }
};
if (isEntry()) process.exitCode = await main();
