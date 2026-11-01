import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { scriptHashes, staticSecurityHeaders, headersFile } from './build-security.mjs';
import worker from '../workers/electricity.mjs';

test('CSP authorises exact generated scripts and fails if Cloudflare cannot accept it', () => {
  const source = 'self.ready = true;\n';
  const html = `<script src="/_next/app.js" type="module"></script><script>${source}</script>`;
  const hash = `'sha256-${createHash('sha256').update(source).digest('base64')}'`;
  assert.deepEqual(scriptHashes(html), [hash]);
  assert.notDeepEqual(scriptHashes(html.replace('true', 'false')), [hash]);
  const csp = staticSecurityHeaders([html, html])['Content-Security-Policy'];
  assert.equal(csp.split(hash).length, 2);
  assert.match(csp, /script-src 'self' 'sha256-/);
  assert.doesNotMatch(csp, /script-src[^;]*'unsafe-/);
  assert.match(csp, /frame-ancestors 'none'/);
  assert.throws(() => scriptHashes('<script src="https://third-party.example/script.js"></script>'));
  assert.throws(() => scriptHashes('<script src="//third-party.example/script.js"></script>'));
  assert.throws(() => headersFile({ 'Content-Security-Policy': 'a'.repeat(2000) }));
  assert.throws(() => headersFile({ Test: 'value\nInjected: header' }));
});

test('electricity API protects errors, HEAD and conditional responses as well as JSON', async () => {
  const version = 'a'.repeat(24);
  const env = { ELECTRICITY_DATA: { async get(key, options) {
    return options.type === 'json' ? { records: [{ version }] } : new Blob(['{}']).stream();
  } } };
  for (const [pathname, init, expected] of [
    ['manifest.json', {}, 200],
    ['snapshot.json', { method: 'HEAD' }, 200],
    ['snapshot.json', { headers: { 'If-None-Match': `"${version}"` } }, 304],
    ['snapshot.json?v=invalid', {}, 400],
    ['private/state', {}, 404],
    ['snapshot.json', { method: 'POST' }, 405],
  ]) {
    const response = await worker.fetch(new Request('https://salmonofdata.com/api/electricity/' + pathname, init), env);
    assert.equal(response.status, expected);
    assert.equal(response.headers.get('X-Content-Type-Options'), 'nosniff');
    assert.equal(response.headers.get('X-Frame-Options'), 'DENY');
    assert.match(response.headers.get('Content-Security-Policy'), /default-src 'none'/);
  }
  const unavailable = await worker.fetch(new Request('https://salmonofdata.com/api/electricity/snapshot.json'), {
    ELECTRICITY_DATA: { async get() { throw new Error('KV unavailable'); } },
  });
  assert.equal(unavailable.status, 503);
  assert.equal(unavailable.headers.get('X-Content-Type-Options'), 'nosniff');
  assert.match(unavailable.headers.get('Content-Security-Policy'), /default-src 'none'/);
});
