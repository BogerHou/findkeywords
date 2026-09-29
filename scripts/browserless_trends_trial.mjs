#!/usr/bin/env node
// User-authorized cloud-browser trial. No direct Google API requests or retries.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const RUN = path.join(ROOT, 'results/local-trends-20260928');
const TOKEN_PATH = path.join(ROOT, 'runtime/browserless/token.txt');
const BUNDLED = path.join(process.env.HOME || '', '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core/index.mjs');

export function sanitize(value, token = '') {
  let text = String(value);
  if (token) text = text.split(token).join('[REDACTED]').split(encodeURIComponent(token)).join('[REDACTED]');
  return text.replace(/wss?:\/\/\S+/g, '[Browserless connection URL redacted]')
    .replace(/([?&](?:token|key|apiKey)=)[^&\s"']+/gi, '$1[REDACTED]');
}

export function queryUrl(item, window) {
  if (!['chart30', 'background', 'repeat30'].includes(item.stage)) throw new Error('Unknown stage');
  const u = new URL('https://trends.google.com/trends/explore');
  u.search = new URLSearchParams({date: `${item.stage === 'background' ? window.background_start : window.start} ${window.end}`, geo: 'US', q: item.keyword, hl: 'en'});
  return u.href;
}

export function classify(text, responses = []) {
  if (responses.some(r => r.status === 403) || /unusual traffic|captcha|verify (?:that )?you are human|access denied/i.test(text)) return 'blocked';
  if (responses.some(r => r.status === 429) || /too many requests/i.test(text)) return 'rate_limited';
  if (/something went wrong|try again later/i.test(text)) return 'page_error';
  return null;
}

export function timeWidget(text) {
  const start = text.indexOf('Interest over time');
  if (start < 0) return null;
  const ends = ['Interest by subregion', 'Interest by region', 'Related topics', 'Related queries']
    .map(label => text.indexOf(label, start)).filter(index => index > start);
  return text.slice(start, ends.length ? Math.min(...ends) : undefined);
}

function helper(command, args = []) {
  const r = spawnSync('python3', ['scripts/local_trends_review.py', command, ...args], {cwd: ROOT, encoding: 'utf8'});
  if (r.status !== 0) throw new Error(`Evidence helper failed: ${r.stderr || r.stdout}`);
  return JSON.parse(r.stdout);
}

function writeJson(file, value) {
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n', {mode: 0o600});
}

async function pageText(page) {
  const texts = [];
  for (const frame of page.frames()) {
    // Read only rendered DOM; never inspect page JS state, cookies or tokens.
    try { texts.push(await frame.locator('body').innerText({timeout: 1000})); } catch {}
  }
  return texts.join('\n');
}

async function chartReady(page, responses, deadline) {
  while (Date.now() < deadline) {
    const text = await pageText(page);
    const error = classify(text, responses);
    if (error) return {error, text};
    for (const frame of page.frames()) {
      let body;
      try { body = await frame.locator('body').innerText({timeout: 1000}); } catch { continue; }
      const chart = timeWidget(body);
      if (chart === null) continue;
      // Only the time widget's own message qualifies as no-data.
      if (/doesn't have enough data|not enough data/i.test(chart)) return {frame, text, chart, noData: true};
      const table = frame.getByRole('table').first();
      if (await table.count() && await table.getByRole('row').count() >= 2) return {frame, text, chart, noData: false};
    }
    // This polls rendered state; it sends no new Google query.
    await sleep(500);
  }
  return {error: 'chart_timeout', text: await pageText(page)};
}

export async function runTrial({maxQueries = 2, check = false} = {}) {
  if (!Number.isInteger(maxQueries) || maxQueries < 1 || maxQueries > 2) throw new Error('Trial permits 1 or 2 stages per cloud session');
  const token = process.env.BROWSERLESS_TOKEN?.trim() || (fs.existsSync(TOKEN_PATH) ? fs.readFileSync(TOKEN_PATH, 'utf8').trim() : '');
  if (check || !token) {
    const status = {state: token ? 'configured_not_connected' : 'awaiting_token', token_path: TOKEN_PATH, max_queries: maxQueries};
    console.log(JSON.stringify(status));
    return status;
  }
  const initial = helper('status');
  if (initial.pacing && !initial.pacing.allowed) {
    console.log(JSON.stringify({state: initial.pacing.state, next_allowed_at: initial.next_allowed_at}));
    return initial;
  }
  const trialId = new Date().toISOString().replace(/[:.]/g, '-');
  const trialDir = path.join(RUN, 'browserless-trials', trialId);
  fs.mkdirSync(trialDir, {recursive: true, mode: 0o700});
  const report = {execution: 'browserless_cloud', trial_id: trialId, started_at: new Date().toISOString(),
    endpoint: 'production-sfo.browserless.io/chrome', max_queries: maxQueries, attempts: [],
    policy: {serial: true, query_interval_seconds: 45, automatic_retries: 0, proxies: false, stealth: false, captcha_solving: false}};
  let browser, current = null, responses = [], page;
  const save = () => writeJson(path.join(trialDir, 'trial.json'), report);
  try {
    const library = process.env.PLAYWRIGHT_CORE_PATH || BUNDLED;
    const {chromium} = fs.existsSync(library) ? await import(pathToFileURL(library).href) : await import('playwright-core');
    const connectionStarted = Date.now();
    // Plain Chrome, fixed region, no local profile upload or proxy/stealth options.
    browser = await chromium.connectOverCDP(`wss://production-sfo.browserless.io/chrome?token=${encodeURIComponent(token)}&timeout=110000`, {timeout: 20000});
    report.connection_ms = Date.now() - connectionStarted;
    const sessionDeadline = connectionStarted + 105000; // Fits the documented 2-minute free session.
    const context = await browser.newContext({acceptDownloads: true});
    page = await context.newPage();
    page.setDefaultTimeout(10000);
    page.on('response', r => {
      const u = new URL(r.url());
      if (u.hostname === 'trends.google.com' && r.status() >= 400) {
        responses.push({status: r.status(), path: u.pathname, at: new Date().toISOString(), retry_after: r.headers()['retry-after'] || null});
      }
    });
    const window = JSON.parse(fs.readFileSync(path.join(RUN, 'queue.json'), 'utf8')).window;
    for (let i = 0; i < maxQueries; i++) {
      if (sessionDeadline - Date.now() < 35000) { report.stop_reason = 'session_budget'; break; }
      let claim = helper('claim');
      if (!claim.allowed && claim.state === 'waiting_interval' && claim.seconds_remaining <= 60
          && sessionDeadline - Date.now() > claim.seconds_remaining * 1000 + 35000) {
        await sleep(Math.ceil(claim.seconds_remaining * 1000) + 50);
        claim = helper('claim');
      }
      if (!claim.allowed) { report.stop_reason = claim.state; break; }
      current = {...claim, execution: 'browserless_cloud', requested_at: new Date().toISOString()};
      responses = [];
      const started = Date.now();
      const url = queryUrl(claim, window);
      await page.goto(url, {waitUntil: 'domcontentloaded', timeout: 25000});
      const result = await chartReady(page, responses, Math.min(sessionDeadline - 5000, Date.now() + 25000));
      const capturedAt = new Date().toISOString();
      current.url = page.url();
      current.captured_at = capturedAt;
      current.responses = responses;
      writeJson(path.join(trialDir, `observed-${i + 1}.json`), {keyword: claim.keyword, stage: claim.stage,
        execution: 'browserless_cloud', url: page.url(), captured_at: capturedAt, text: sanitize(result.text, token), responses});
      if (result.error) throw new Error(result.error);
      let evidence, kind;
      if (result.noData) {
        evidence = path.join(trialDir, `no-data-${i + 1}.json`); kind = '--dom';
        writeJson(evidence, {keyword: claim.keyword, url: page.url(), status: 'no_data', captured_at: capturedAt,
          execution: 'browserless_cloud', text: result.chart});
      } else {
        const downloadPromise = page.waitForEvent('download', {timeout: 12000});
        await result.frame.getByRole('button', {name: 'file_download', exact: true}).first().click();
        const download = await downloadPromise;
        evidence = path.join(trialDir, `chart-${i + 1}.csv`); kind = '--csv';
        await download.saveAs(evidence);
      }
      if (classify('', responses)) throw new Error(classify('', responses));
      const imported = helper('ingest', ['--keyword', claim.keyword, '--stage', claim.stage, '--url', page.url(),
        kind, evidence, '--captured-at', capturedAt, '--execution', 'browserless_cloud']);
      report.attempts.push({...current, status: 'imported', elapsed_ms: Date.now() - started,
        evidence: path.relative(ROOT, evidence), completed: imported.completed, pending: imported.pending});
      current = null;
      save();
      console.log(JSON.stringify({event: 'imported', ...report.attempts.at(-1)}));
    }
    report.state = 'finished';
  } catch (error) {
    report.error = sanitize(error.message, token);
    report.state = current ? 'query_failed' : 'connection_failed';
    if (current) {
      report.attempts.push({...current, status: 'failed', responses});
      try { await page.screenshot({path: path.join(trialDir, 'failure.png')}); } catch {}
      const reason = `Browserless cloud trial ${current.keyword} ${current.stage}: ${report.error}; evidence ${path.relative(ROOT, trialDir)}`;
      if (classify(report.error, responses) === 'blocked' || report.error === 'blocked') {
        helper('block', ['--reason', reason]);
      } else if (responses.some(r => r.status === 429) || report.error === 'rate_limited') {
        const retryAfter = responses.find(r => r.status === 429 && r.retry_after)?.retry_after;
        helper('cooldown', ['--reason', reason, ...(retryAfter ? ['--retry-after', retryAfter] : [])]);
      } else helper('block', ['--reason', reason]);
    }
  } finally {
    if (browser) try { await browser.close(); } catch {}
    report.finished_at = new Date().toISOString();
    save();
  }
  console.log(JSON.stringify(report));
  return report;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const index = args.indexOf('--max-queries');
  runTrial({check: args.includes('--check'), maxQueries: index < 0 ? 2 : Number(args[index + 1])})
    .catch(error => { console.error(sanitize(error.message, process.env.BROWSERLESS_TOKEN || '')); process.exitCode = 1; });
}
