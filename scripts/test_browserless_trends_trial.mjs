import assert from 'node:assert/strict';
import test from 'node:test';
import {classify, queryUrl, sanitize, timeWidget} from './browserless_trends_trial.mjs';

test('credential values and connection URLs are redacted from diagnostics', () => {
  const token = 'private+token';
  const raw = `Failed wss://host/chrome?token=${encodeURIComponent(token)} plain ${token}`;
  const safe = sanitize(raw, token);
  assert(!safe.includes(token));
  assert(!safe.includes(encodeURIComponent(token)));
  assert(!safe.includes('wss://'));
});

test('fixed URL scope and exact keyword survive Unicode and punctuation', () => {
  const window = {start: '2026-08-29', end: '2026-09-27', background_start: '2026-03-27'};
  for (const stage of ['chart30', 'background', 'repeat30']) {
    const u = new URL(queryUrl({keyword: 'a+b & 中文', stage}, window));
    assert.equal(u.hostname, 'trends.google.com');
    assert.equal(u.searchParams.get('q'), 'a+b & 中文');
    assert.equal(u.searchParams.get('geo'), 'US');
    assert.equal(u.searchParams.get('date'), `${stage === 'background' ? window.background_start : window.start} ${window.end}`);
  }
});

test('rate limits and verification cannot become no-data', () => {
  assert.equal(classify("doesn't have enough data", [{status: 429}]), 'rate_limited');
  assert.equal(classify('chart', [{status: 403}]), 'blocked');
  assert.equal(classify('chart', [{status: 429}, {status: 403}]), 'blocked');
  assert.equal(classify('Verify you are human', [{status: 429}]), 'blocked');
  assert.equal(classify('Our systems detected unusual traffic'), 'blocked');
  assert.equal(classify('Oops! Something went wrong.'), 'page_error');
  assert.equal(classify("doesn't have enough data"), null);
});

test('related-widget insufficiency is excluded from time-widget evidence', () => {
  const text = "Interest over time\nchart\nRelated topics\nHmm, your search doesn't have enough data to show here.";
  assert.equal(timeWidget(text), 'Interest over time\nchart\n');
  assert.equal(timeWidget('Related topics\nnot enough data'), null);
});
