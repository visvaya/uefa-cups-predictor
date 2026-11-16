// Run with: node --test <this directory>
import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  checkItems,
  formatReport,
  newestEligible,
  parseList,
  parseVersion,
  readPin,
} from './check-freshness.mjs';

const NOW = Date.parse('2026-11-15T12:00:00Z');
const daysAgo = (days) => new Date(NOW - days * 24 * 60 * 60 * 1000).toISOString();

test('a stable version is read from a version or a tag; pre-releases are not versions', () => {
  assert.deepEqual(parseVersion('v8.30.1'), [8, 30, 1]);
  assert.deepEqual(parseVersion('rust-v1.2.3'), [1, 2, 3]);
  assert.deepEqual(parseVersion('12.21.0'), [12, 21, 0]);
  assert.equal(parseVersion('2.0.0-rc.1'), undefined);
  assert.equal(parseVersion('nightly'), undefined);
  assert.equal(parseVersion(undefined), undefined);
});

test('the newest eligible release skips releases younger than the release age', () => {
  const releases = [
    { version: 'v1.9.0', publishedAt: daysAgo(30) },
    { version: 'v1.10.0', publishedAt: daysAgo(8) },
    { version: 'v1.11.0', publishedAt: daysAgo(2) },
    { version: 'v2.0.0-beta.1', publishedAt: daysAgo(20) },
  ];
  assert.deepEqual(newestEligible(releases, { nowMs: NOW, minAgeDays: 7 }), [1, 10, 0]);
  assert.deepEqual(newestEligible(releases, { nowMs: NOW, minAgeDays: 0 }), [1, 11, 0]);
  assert.equal(newestEligible(releases, { nowMs: NOW, minAgeDays: 60 }), undefined);
});

test('a pin is read through the first capture group, and a lost pattern reads as undefined', () => {
  const workflow = 'env:\n  GITLEAKS_VERSION: "8.30.1"\n  GITLEAKS_SHA256: abc\n';
  assert.deepEqual(readPin(workflow, 'GITLEAKS_VERSION:[ "]*([0-9.]+)'), [8, 30, 1]);
  assert.equal(readPin(workflow, 'ACTIONLINT_VERSION:[ "]*([0-9.]+)'), undefined);
  assert.deepEqual(readPin('{ "packageManager": "pnpm@12.14.0" }', '"packageManager": "pnpm@([0-9.]+)"'), [12, 14, 0]);
});

const LIST = {
  minimumReleaseAgeDays: 7,
  items: [
    { name: 'npm dependencies', mechanism: 'dependabot', where: 'npm, /' },
    { name: 'Node patch', mechanism: 'check-latest', where: 'setup-node check-latest' },
    {
      name: 'pnpm',
      mechanism: 'job',
      check: { file: 'package.json', pattern: '"packageManager": "pnpm@([0-9.]+)"', npm: 'pnpm' },
      howToBump: 'set packageManager to the new version and run pnpm install',
    },
    {
      name: 'gitleaks',
      mechanism: 'job',
      check: { file: '.github/workflows/security.yml', pattern: 'GITLEAKS_VERSION:[ "]*([0-9.]+)', github: 'gitleaks/gitleaks' },
      howToBump: 'update GITLEAKS_VERSION and GITLEAKS_SHA256',
    },
    {
      name: 'zizmor',
      mechanism: 'job',
      check: { file: '.github/zizmor-requirements.txt', pattern: 'zizmor==([0-9.]+)', pypi: 'zizmor' },
      howToBump: 'update the version and the hashes in the requirements line',
    },
  ],
};

test('a valid list parses; every item needs a mechanism and every non-job item says where', () => {
  assert.equal(parseList(LIST).ok, true);
  const broken = parseList({
    items: [
      { name: 'a', mechanism: 'renovate' },
      { name: 'b', mechanism: 'dependabot' },
      { name: 'c', mechanism: 'job', check: { file: 'x', pattern: '(1)' } },
      { name: 'd', mechanism: 'job', check: { file: 'x', pattern: '(1)', npm: 'd' } },
    ],
  });
  assert.equal(broken.ok, false);
  assert.deepEqual(broken.error, [
    'a: mechanism must be one of dependabot, check-latest, job, manual',
    'a: where must say which configuration keeps it current',
    'b: where must say which configuration keeps it current',
    'c: a job check needs file, pattern and one of github, npm or pypi',
    'c: howToBump is missing',
    'd: howToBump is missing',
  ]);
  assert.equal(parseList({ items: [] }).ok, false);
});

const FILES = {
  'package.json': JSON.stringify({ packageManager: 'pnpm@12.14.0' }, null, 2),
  '.github/workflows/security.yml': 'env:\n  GITLEAKS_VERSION: 8.30.1\n',
  '.github/zizmor-requirements.txt': 'zizmor==1.30.0 --hash=sha256:abc\n',
};
const RESPONSES = {
  'https://registry.npmjs.org/pnpm': {
    versions: { '12.14.0': {}, '12.21.0': {}, '13.0.0': {} },
    time: { '12.14.0': daysAgo(40), '12.21.0': daysAgo(10), '13.0.0': daysAgo(1) },
  },
  'https://api.github.com/repos/gitleaks/gitleaks/releases?per_page=100': [
    { tag_name: 'v8.30.1', published_at: daysAgo(50), draft: false, prerelease: false },
    { tag_name: 'v8.31.0', published_at: daysAgo(3), draft: false, prerelease: false },
  ],
  'https://pypi.org/pypi/zizmor/json': {
    releases: {
      '1.30.0': [{ upload_time_iso_8601: daysAgo(60) }],
      '1.31.0': [{ upload_time_iso_8601: daysAgo(20) }],
      '1.32.0': [{ upload_time_iso_8601: daysAgo(15), yanked: true }],
      '1.33.0': [],
    },
  },
};

test('only job items are checked, with the release age applied to pins', async () => {
  const results = await checkItems({
    list: parseList(LIST).value,
    readText: (file) => FILES[file],
    fetchJson: async (url) => RESPONSES[url],
    nowMs: NOW,
  });
  assert.deepEqual(
    results.map(({ name, status }) => [name, status]),
    [
      ['pnpm', 'outdated'],
      ['gitleaks', 'ok'],
      ['zizmor', 'outdated'],
    ],
  );
  assert.match(results[2].text, /pinned 1[.]30[.]0, latest 1[.]31[.]0/);
  assert.match(results[0].text, /pinned 12[.]14[.]0, latest 12[.]21[.]0: set packageManager/);
});

test('the report fails on any item that is not current and names it', () => {
  const report = formatReport([
    { name: 'gitleaks', status: 'ok', text: 'pinned 8.30.1, latest 8.30.1' },
    { name: 'pnpm', status: 'outdated', text: 'pinned 12.14.0, latest 12.21.0: bump' },
  ]);
  assert.equal(report.exitCode, 1);
  assert.equal(report.text, 'gitleaks: pinned 8.30.1, latest 8.30.1\npnpm: OUTDATED, pinned 12.14.0, latest 12.21.0: bump\n');
  assert.equal(formatReport([{ name: 'x', status: 'ok', text: 'fine' }]).exitCode, 0);
});

test('a network failure propagates so the caller exits with 2', async () => {
  await assert.rejects(
    checkItems({
      list: parseList(LIST).value,
      readText: (file) => FILES[file],
      fetchJson: async () => {
        throw new Error('503 from api');
      },
      nowMs: NOW,
    }),
    /503/,
  );
});

test('pre-releases without a hyphen (PyPI rc, alpha, beta) are not stable', () => {
  assert.equal(parseVersion('1.33.0rc1'), undefined);
  assert.equal(parseVersion('2.0.0b2'), undefined);
  assert.equal(parseVersion('1.32.0')?.join('.'), '1.32.0');
});
