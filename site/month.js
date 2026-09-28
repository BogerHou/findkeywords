(() => {
  'use strict';
  const PAGE_SIZE = 50;
  const states = new Map();
  let state = {q: '', verdict: 'candidate', channel: 'all', research: 'included', page: 1};
  let activeVariant = 'month';
  function activate(data, variant = 'month') {
    const key = data?.meta?.runId || variant;
    if (!states.has(key)) states.set(key, {q: '', verdict: 'candidate', channel: 'all', research: 'included', page: 1});
    state = states.get(key);
    activeVariant = variant;
  }
  const verdicts = [
    ['candidate', '自动候选', 'candidate'],
    ['redirected', '跳转到其他域名', 'review'],
    ['registration_unknown', '注册时间未核实', 'review'],
    ['old', '超过注册窗口', 'reject'],
    ['parked', '停放 / 默认 / 待发布', 'reject'],
    ['thin', '页面内容不足', 'unknown'],
    ['unavailable', '未取得页面', 'unknown']
  ];
  const verdictMap = new Map(verdicts.map(([id, label, color]) => [id, {label, color}]));
  let indexedRows = [];
  let filteredRows = [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
  const number = value => value !== undefined && value !== null && value !== '' && Number.isFinite(Number(value)) ? Number(value).toLocaleString('zh-CN') : '—';
  const list = value => Array.isArray(value) ? value : [];
  const present = value => value !== undefined && value !== null && value !== '';
  const externalURL = value => {
    try {
      const u = new URL(String(value));
      return ['https:', 'http:'].includes(u.protocol) ? u.href : null;
    } catch { return null; }
  };
  const external = (url, label, cls = '') => {
    const safe = externalURL(url);
    return safe ? `<a href="${esc(safe)}" class="${cls}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>` : esc(label);
  };
  const resourceLink = (resource, label) => {
    const path = String(resource.path || '');
    if (!/^\.\.\/(?:reports|data|site)\/[A-Za-z0-9_./-]+$/.test(path) || path.slice(3).split('/').includes('..')) return esc(label || resource.title);
    return `<a href="${esc(path)}" target="_blank" rel="noopener">${esc(label || resource.title)} ↗</a>`;
  };
  const calendarDate = value => value ? esc(String(value).slice(0, 10)) : '未核实';
  const timeLabel = value => {
    if (!value) return '未记录';
    const d = new Date(value);
    return Number.isFinite(d.getTime()) ? esc(d.toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai', hour12: false})) + '（北京时间）' : esc(value);
  };
  const textBlock = value => {
    const values = Array.isArray(value) ? value : [value];
    return values.filter(present).map(v => `<p>${esc(v)}</p>`).join('') || '<span class="subtle">未取得</span>';
  };
  const verdict = row => {
    const known = verdictMap.get(row.verdict) || {label: '待归类', color: 'unknown'};
    return `<span class="tag month-status-${known.color}">${esc(row.verdictLabel || known.label)}</span>`;
  };
  function countInfo(data) {
    const s = data.summary || {};
    const rows = list(data.domains);
    return {
      uniqueDomains: s.uniqueDomains,
      probed: s.probed ?? rows.length,
      candidates: s.candidates ?? rows.filter(r => r.verdict === 'candidate').length,
      uniqueKeywordPhrases: s.uniqueKeywordPhrases ?? new Set(rows.flatMap(r => list(r.keywordCandidates).map(k => k.phrase))).size
    };
  }
  function methodHTML(data) {
    const s = data.summary || {};
    const a = data.acquisition || {};
    const screening = data.screening || {};
    const channels = list(screening.channels);
    const notes = list(screening.notes);
    const batches = list(a.batches);
    const count = countInfo(data);
    const rules = [
      ['自动候选', '注册日期落在核验时点往前 30 天内，页面通过自动实质内容规则，最终目标仍为同一域名。首次上线时间尚未核实。'],
      ['跨域跳转', '近期注册，但落地到其他域名；不能把目标网站当成本月新站。'],
      ['注册时间未核实', '页面有实质内容，但 RDAP 没有返回可确认的注册日期。'],
      ['超过注册窗口', '已取得注册日期，但它不在本轮近 30 天的注册范围内。'],
      ['停放或未成站', '页面命中出售、停放、即将上线或默认页等自动排除规则。'],
      ['页面不足或未取得', '页面内容不足，或请求失败、被拦截、返回非 HTML 等；这不证明网站永久不可用。']
    ];
    return `<details class="panel month-methods" id="month-methods"><summary>查看名单来源、抽样配额和逐级筛选规则</summary>
      <p class="month-method-intro">名单覆盖与逐站核验是两个阶段。本轮从月度名单按明确通道选取核验样本，并保留已核验样本的每条判定和原因。未抽中的名单域名没有经过网页判定，也不能记作“淘汰的网站”。</p>
      <div class="month-funnel">
        <div class="month-funnel-step"><span>01 · 月度名单去重</span><strong>${number(s.uniqueDomains)}</strong><p>原始名单 ${number(s.rawRows)} 条；不是已上线网站数。</p></div>
        <div class="month-funnel-step"><span>02 · 按规则选入核验</span><strong>${number(s.probeSelected)}</strong><p>按下表通道和配额分配；不代表全量网站质量排名。</p></div>
        <div class="month-funnel-step"><span>03 · 已完成逐域名核验</span><strong>${number(count.probed)}</strong><p>先抓页面，仅实质内容页查注册日期；尚余 ${number(s.remaining ?? 0)} 条。</p></div>
        <div class="month-funnel-step"><span>04 · 规则与内容复核保留</span><strong>${number(count.candidates)}</strong><p>近期注册＋实质页面＋同域目标，仍需人工与搜索需求验证。</p></div>
      </div>
      <h3 class="month-subheading">名单覆盖</h3>
      <p class="source-text">${external(a.sourceUrl, a.sourceName || '名单来源')} · ${esc(a.windowStart || data.meta?.windowStart || '—')} 至 ${esc(a.windowEnd || data.meta?.windowEnd || '—')}。已下载 ${number(s.downloadedDays)} / ${number(s.requestedDays)} 个日期批次。${[...new Set([a.coverageNote, data.meta?.sourceNote].filter(present))].map(esc).join(' ')}</p>
      ${screening.method ? `<p class="source-text">选样方法：${esc(screening.method)}</p>` : ''}
      ${channels.length ? `<h3 class="month-subheading">每条选样通道的规则和配额</h3><div class="table-wrap"><table class="mini-table month-quota-table"><thead><tr><th>通道</th><th>${activeVariant === 'tld' ? '名称初筛通过' : '符合规则的数量'}</th><th>配额</th><th>实际选入</th><th>可复核规则</th></tr></thead><tbody>${channels.map(c => `<tr><td>${esc(c.label || c.id)}</td><td>${number(c.eligible)}</td><td>${esc(c.quota)}</td><td>${number(c.selected)}</td><td>${esc(c.rule || '见完整规则文件')}</td></tr>`).join('')}</tbody></table></div>` : ''}
      ${notes.length ? `<p class="source-text">域名核验阶段的原始备注；以下不包含后续独立进行的趋势复核。</p><ul class="month-rule-list">${notes.map(note => `<li>${esc(note)}</li>`).join('')}</ul>` : ''}
      <div class="month-method-columns"><section><h3 class="month-subheading">结果分类的含义</h3><ul class="month-rule-list">${rules.map(([label, rule]) => `<li><strong>${label}：</strong>${rule}</li>`).join('')}</ul><p>这些标签由有优先顺序的自动规则产生，再合并有原文依据的 AI 内容复核纠正，互斥记录最终判定。为节省注册接口请求，先抓取页面，仅对实质内容页查询 RDAP；其余 ${number(s.registrationNotChecked ?? 0)} 条标记为“未查询注册日期”，不计入“已尝试但未核实”。完整规则和每条记录中的原因以原始文件为准。</p></section><section><h3 class="month-subheading">时间和证据的边界</h3><p>注册时间核验下限：${timeLabel(data.meta?.registrationCutoff)}。核验参照时点：${timeLabel(data.meta?.registrationReferenceTime)}。名单批次日期表示来源日期；它不等同于注册日期或首次上线日期。</p><p>本轮记录的是“现在访问到什么”。SSL 可用、域名刚注册或当前有页面，都不能单独证明过去一个月首次上线。${esc(data.meta?.launchNote || '')}</p><p>页面 title、description 和 H1 的原文片段不等于已整理搜索词。域名核验阶段只保存网页内容；${activeVariant === 'tld' ? '后续逐词提炼、是否实际查询及保存的趋势结果，见 <a href="#trends30">近30天趋势</a>。' : '本批次原文片段尚未逐一查询趋势。'}搜索规模、排名机会或网站流量仍未验证。</p></section></div>
      ${batches.length ? `<details class="data-disclosure"><summary>展开 ${batches.length} 个来源批次及校验信息</summary><div class="raw-data"><table class="mini-table"><thead><tr><th>批次日期</th><th>下载状态</th><th>名单行数</th><th>批次内去重</th><th>来源与 SHA-256</th></tr></thead><tbody>${batches.map(b => `<tr><td>${esc(b.date)}</td><td>${esc(b.status)}</td><td>${number(b.rows)}</td><td>${number(b.unique_domains)}</td><td>${external(b.url, '原始批次')}<div class="month-domain-meta"><code>${esc(b.sha256 || '未记录')}</code></div></td></tr>`).join('')}</tbody></table></div></details>` : ''}
    </details>`;
  }
  window.renderMonth = function renderMonth(data, options = {}) {
    activate(data, options.variant || 'month');
    if (!data) return '<section class="month-page"><div class="page-header"><div><h1>近一个月域名扩量</h1><p class="subtle">月度核验数据尚未生成。请在数据完成后重新加载页面。</p></div></div></section>';
    const s = data.summary || {};
    const m = data.meta || {};
    const count = countInfo(data);
    const running = m.status !== 'complete';
    const tld = options.variant === 'tld';
    const title = m.title || (tld ? '从名称，发现另一批网站。' : '近一个月，扩大域名线索池。');
    const subtitle = m.subtitle || (tld ? '后缀决定抽样优先级，名称规则独立于原有关键词表。留下的域名继续抓取网页、核验注册时间，并保存词句原文。' : `名单日期 ${m.windowStart || '—'} — ${m.windowEnd || '—'}。先抓取当前页面，再核查实质内容页的注册日期，并提取网页里的原始词句，保留每一步的依据。`);
    const keywordCSV = tld ? '../reports/tld-keywords-2026-09-26.csv' : '../reports/month-keywords-2026-09-26.csv';
    const channels = list(data.screening?.channels);
    const statusCounts = new Map();
    list(data.domains).forEach(r => statusCounts.set(r.verdict, (statusCounts.get(r.verdict) || 0) + 1));
    return `<section class="month-page" aria-label="${tld ? '后缀与名称独立筛选' : '月度域名扩量研究'}">
      <div class="page-header"><div><div class="eyebrow">${tld ? 'NAME DISCOVERY' : 'MONTHLY DISCOVERY'} / ${esc(m.runDate || '')}</div><h1>${esc(title)}</h1><p class="month-lede subtle">${esc(subtitle)}</p><div class="month-snapshot"><span class="snapshot-dot"></span>${running ? ((s.remaining ?? 0) === 0 && (s.contentReviewRemaining ?? 0) > 0 ? '内容复核中 · 页面探测已完成' : '核验进行中 · 本页为已保存的进度快照') : '本轮核验已完成 · 已保存的研究快照'}</div><div class="month-updated">更新于 ${timeLabel(m.generatedAt)}</div></div><div class="month-header-actions"><a class="btn btn-secondary" href="${keywordCSV}" download>${tld ? '导出研究范围内原文' : '导出候选词句'} ↓</a><button class="btn btn-secondary" id="month-show-methods">查看规则与配额 ↓</button></div></div>
      <div class="month-summary"><div><span>月度名单去重域名</span><strong>${number(count.uniqueDomains)}</strong><small>${number(s.downloadedDays)} / ${number(s.requestedDays)} 个日期批次；非上线站数</small></div><div><span>已完成逐域名核验</span><strong>${number(count.probed)}</strong><small>从 ${number(s.probeSelected)} 个选样域名中核验</small></div><div><span>内容筛选保留域名</span><strong>${number(count.candidates)}</strong><small>${tld ? '本轮选样排除了此前已探测域名' : `其中 ${number(s.newToPriorProbes)} 个此前未探测`}</small></div><div><span>${tld ? '研究范围内去重词句' : '去重的网页词句线索'}</span><strong>${number(tld ? s.researchUniqueKeywordPhrases : count.uniqueKeywordPhrases)}</strong><small>来自网页字段，未做搜索需求验证</small></div></div>
      <div class="notice month-definition"><strong>这里的“自动候选”还不是已确认的一个月内新上线网站。</strong> 自动初筛 ${number(s.automaticCandidates ?? s.candidates)} 个候选，已复核 ${number(s.contentReviewed ?? 0)} 个，纠正 ${number(s.contentCorrections ?? 0)} 个明显页面误收。保留项已通过注册时间和当前页面规则；其余样本先抓取页面，仅实质内容页进一步查询注册日期。首次上线时间尚未核实。${tld ? '原文片段不等于已整理搜索词；词级查询状态以 <a href="#trends30">近30天趋势</a> 为准。' : '标题、描述和 H1 的词句尚未逐一通过 Google Trends 验证。'}${(s.remaining ?? 0) > 0 ? ` 当前还有 ${number(s.remaining)} 个已选样域名待核验。` : ''}${(s.contentReviewRemaining ?? 0) > 0 ? ` 另有 ${number(s.contentReviewRemaining)} 个自动候选待内容复核。` : ''}${running ? ' 刷新可读取之后保存的新结果。' : ''}</div>
      ${tld && window.renderTldIntro ? window.renderTldIntro(data) : ''}
      ${methodHTML(data)}
      <div class="section-heading"><div><h2>逐域名核验记录</h2><p>${tld ? '默认查看本轮研究范围内的自动候选。核验结果与研究范围分别筛选；范围外记录仅显示中性摘要。' : '默认查看自动候选。切换“全部记录”可查所有已核验样本，包括排除项和失败原因。'}</p></div></div>
      <div class="toolbar month-toolbar"><div class="search-field"><span class="search-symbol">⌕</span><input type="search" class="search-input" id="month-search" value="${esc(state.q)}" placeholder="搜索域名、网页标题或词句线索" aria-label="搜索月度域名、网页标题或词句线索"></div><label class="field"><span class="sr-only">按选样通道筛选</span><select class="control" id="month-channel"><option value="all">全部选样通道</option>${channels.map(c => `<option value="${esc(c.id)}"${state.channel === c.id ? ' selected' : ''}>${esc(c.label || c.id)}</option>`).join('')}</select></label>${tld ? `<label class="field"><span class="sr-only">研究范围</span><select class="control" id="month-research"><option value="included"${state.research === 'included' ? ' selected' : ''}>本轮研究范围</option><option value="all"${state.research === 'all' ? ' selected' : ''}>全部核验记录（含隔离）</option></select></label>` : ''}<button class="btn btn-secondary" id="month-clear">重置筛选</button></div>
      <div class="filter-tabs month-status-tabs" aria-label="按核验结果筛选"><button class="filter-tab${state.verdict === 'all' ? ' active' : ''}" data-month-verdict="all" aria-pressed="${state.verdict === 'all'}">全部记录 <span>${number(list(data.domains).length)}</span></button>${verdicts.map(([id, label]) => `<button class="filter-tab${state.verdict === id ? ' active' : ''}" data-month-verdict="${id}" aria-pressed="${state.verdict === id}">${esc(label)} <span>${number(statusCounts.get(id) || 0)}</span></button>`).join('')}</div>
      <div class="table-meta"><span id="month-count" class="month-count" aria-live="polite"></span><span>每页 50 条 · 按保存顺序展示，无机会评分</span></div>
      <div class="table-wrap"><table class="month-table"><thead><tr><th scope="col">域名 / 选样来源</th><th scope="col">核验结果</th><th scope="col">注册日期</th><th scope="col">当前页面与词句证据</th></tr></thead><tbody id="month-rows"></tbody></table></div>
      <div class="month-pagination"><span id="month-pagination-note"></span><div class="month-page-buttons"><button class="btn btn-secondary btn-small" id="month-prev" aria-label="上一页域名记录">← 上一页</button><span class="month-page-position" id="month-page-position" aria-live="polite"></span><button class="btn btn-secondary btn-small" id="month-next" aria-label="下一页域名记录">下一页 →</button></div></div>
      <p class="export-note">${tld ? '研究范围内记录可展开查看页面原文、注册来源和判定依据；范围外记录使用中性别名并隐藏原文与外链。导出仅含研究范围内原文。' : '每条记录可展开查看页面原文、注册时间来源、选样理由及完整排除原因。'}页面内容可能已变化，本页显示采集时保存的文字。</p>
      <section class="panel detail-section"><div class="section-heading"><div><h2>原始文件与复核入口</h2><p>保留月度来源、选样记录和全部已核验结果，方便复现筛选过程。</p></div></div><div class="month-source-links">${list(data.resources).map(r => resourceLink(r)).join('') || '<span class="subtle">原始文件链接将随数据生成。</span>'}</div><p class="month-data-note">本轮扩大的是域名线索覆盖和逐站核验规模。${number(s.uniqueDomains)} 个名单域名中，只有 ${number(count.probed)} 个完成了本轮页面核验；其中实质内容页再查注册日期。${tld ? '本通道未抽中的域名没有经过本通道核验；原通道结果在“近30天扩量”页单独保留。' : '其余名单域名的页面与注册状态仍未知。'}旧的 32 个关键词及其趋势记录仍可在“已查趋势词”查看。</p></section>
    </section>`;
  };
  function domainRow(row) {
    if (row.sensitiveSuppressed) {
      const labels = {adult: '成人内容', gambling: '博彩相关', content_review: '原文待展示复核'};
      return `<tr class="row-hover month-isolated"><td><span class="month-domain">${esc(row.domain)}</span><div class="month-domain-meta">${esc(row.channelLabel || row.channel || '未记录通道')}</div></td><td>${verdict(row)}<p class="month-state-reason">已移出本轮研究范围</p><div class="month-word-chips">${list(row.researchCategories).map(c => `<span class="tag">${esc(labels[c] || '范围外内容')}</span>`).join('')}</div></td><td><div class="month-date">${row.registrationStatus === 'not_checked' ? '未查询' : calendarDate(row.registrationDate)}</div><div class="month-date-note">保留日期核验结果</div></td><td><div class="month-title">已移出本轮研究范围</div><p class="month-state-reason">${esc(row.researchNote || '按本轮暂定研究偏好跳过。')}</p><p class="month-word-note">仅保留中性核验记录；页面原文、外链与趋势入口已隐藏。</p></td></tr>`;
    }
    const words = list(row.keywordCandidates);
    const dates = list(row.sourceDates);
    const reason = list(row.reasons);
    const fieldLabels = {title: 'title', description: 'description', meta_description: 'description', h1: 'H1'};
    const registrationLabels = {verified_recent: '已核实：近 30 天注册', verified_old: '已核实：早于本轮窗口', unknown: '已查询，但注册日期未核实', not_checked: '未查询注册日期', recent: '已核实：近 30 天注册', old: '已核实：早于本轮窗口'};
    const source = present(row.registrationSource) ? external(row.registrationSource, 'RDAP 来源') : `<span class="subtle">${row.registrationStatus === 'not_checked' ? '未查询 RDAP' : '没有可用来源'}</span>`;
    const wordQuotes = words.map(k => `<p><strong>${esc(fieldLabels[k.field] || k.field || '网页字段')}：</strong>${esc(k.quote || k.phrase)}</p>`).join('');
    return `<tr class="row-hover"><td>${external('https://' + row.domain, row.domain, 'month-domain')}<div class="month-domain-meta">${esc(row.channelLabel || row.channel || '未记录通道')}<br>名单日期：${dates.length ? dates.map(esc).join('、') : '未记录'}</div></td>
      <td>${verdict(row)}<p class="month-state-reason">${esc(reason[0] || (row.verdict === 'candidate' ? '通过本轮自动候选规则，尚需人工复核。' : '详见完整记录。'))}</p></td>
      <td><div class="month-date">${row.registrationStatus === 'not_checked' ? '未查询' : calendarDate(row.registrationDate)}</div><div class="month-date-note">${esc(registrationLabels[row.registrationStatus] || (row.registrationDate ? '注册日期有记录' : '注册时间未核实'))}</div><div class="month-date-note">${source}</div></td>
      <td><div class="month-title">${esc(row.title || (row.fetchStatus === 'ok' ? '页面未提供 title' : '未取得页面标题'))}</div>${row.description ? `<p class="month-description">${esc(row.description)}</p>` : ''}${words.length ? `<div class="month-word-chips">${words.slice(0, 3).map(k => `<span class="tag">${esc(k.phrase)}</span>`).join('')}${words.length > 3 ? `<span class="tag">另 ${words.length - 3} 条</span>` : ''}</div><p class="month-word-note">网页词句线索，未验证搜索需求</p>` : ''}
      <details class="month-evidence"><summary>展开完整证据与判定原因</summary><dl class="evidence-list"><dt>最终页面</dt><dd>${row.finalUrl ? external(row.finalUrl, row.finalUrl) : '未取得'}</dd><dt>网页采集</dt><dd>${timeLabel(row.fetchedAt)}<br>${esc(row.fetchStatus || '状态未记录')}${present(row.httpStatus) ? ' · HTTP ' + esc(row.httpStatus) : ''}${row.fetchError ? `<br>${esc(row.fetchError)}` : ''}</dd><dt>注册证据</dt><dd>${row.registrationDate ? esc(row.registrationDate) : row.registrationStatus === 'not_checked' ? '页面未通过实质内容规则，因此未查询注册日期' : '已尝试查询，日期未核实'}<br>${source}${row.registrationError ? `<br>${esc(row.registrationError)}` : ''}</dd><dt>选样理由</dt><dd>${esc(row.selectionReason || '见选样规则文件')}</dd>${activeVariant === 'tld' && window.renderTldNameEvidence ? window.renderTldNameEvidence(row) : ''}<dt>判定原因</dt><dd>${textBlock(reason)}</dd><dt>title</dt><dd>${textBlock(row.title)}</dd><dt>description</dt><dd>${textBlock(row.description)}</dd><dt>H1</dt><dd>${textBlock(row.h1)}</dd>${wordQuotes ? `<dt>词句原文</dt><dd>${wordQuotes}${activeVariant === 'tld' && window.renderTldTrendsLinks ? window.renderTldTrendsLinks(words) : ''}</dd>` : ''}${row.visibleText ? `<dt>页面文字</dt><dd>${textBlock(row.visibleText)}</dd>` : ''}</dl><p class="month-row-note">${row.redirectedExternal ? '已跨域跳转。' : row.redirected ? '记录到页面跳转。' : ''} 首次上线时间未核实；本条判定来源：${row.reviewStatus === 'ai_content_reviewed' ? '自动规则＋AI内容复核' : '自动规则'}，尚未经过人工逐站确认。</p></details></td></tr>`;
  }
  function updateRows() {
    const q = state.q.trim().toLocaleLowerCase();
    const baseRows = indexedRows.filter(item => (activeVariant !== 'tld' || state.research === 'all' || !item.row.researchExcluded) && (state.channel === 'all' || item.row.channel === state.channel) && (!q || item.search.includes(q)));
    if (activeVariant === 'tld') {
      document.querySelectorAll('[data-month-verdict]').forEach(button => {
        const id = button.dataset.monthVerdict;
        const count = id === 'all' ? baseRows.length : baseRows.filter(item => item.row.verdict === id).length;
        const span = button.querySelector('span');
        if (span) span.textContent = number(count);
      });
    }
    filteredRows = baseRows.filter(item => state.verdict === 'all' || item.row.verdict === state.verdict).map(item => item.row);
    const pages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
    state.page = Math.max(1, Math.min(state.page, pages));
    const offset = (state.page - 1) * PAGE_SIZE;
    const displayed = filteredRows.slice(offset, offset + PAGE_SIZE);
    const total = indexedRows.length;
    document.getElementById('month-count').textContent = displayed.length ? `显示 ${number(offset + 1)}–${number(offset + displayed.length)} 条，共 ${number(filteredRows.length)} 条匹配 / ${number(total)} 条已核验记录` : `0 条匹配 / ${number(total)} 条已核验记录`;
    document.getElementById('month-rows').innerHTML = displayed.length ? displayed.map(domainRow).join('') : `<tr><td colspan="4"><div class="empty-state month-empty"><h3>${total ? '没有匹配的核验记录' : '尚无已保存的逐域名记录'}</h3><p>${total ? '可切换“全部记录”，或清除搜索词和选样通道。' : '数据仍在核验中时，本页只展示已经保存的结果。'}</p><button class="btn btn-secondary" id="month-empty-reset">查看全部记录</button></div></td></tr>`;
    document.getElementById('month-page-position').textContent = `${state.page} / ${pages} 页`;
    document.getElementById('month-pagination-note').textContent = `每页 ${PAGE_SIZE} 条；共 ${number(filteredRows.length)} 条符合当前筛选条件`;
    document.getElementById('month-prev').disabled = state.page <= 1;
    document.getElementById('month-next').disabled = state.page >= pages;
    document.getElementById('month-empty-reset')?.addEventListener('click', () => resetFilters('all'));
  }
  function syncTabs() {
    document.querySelectorAll('[data-month-verdict]').forEach(button => {
      const active = button.dataset.monthVerdict === state.verdict;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  }
  function resetFilters(verdictValue = 'candidate') {
    state.q = '';
    state.verdict = verdictValue;
    state.channel = 'all';
    state.research = 'included';
    state.page = 1;
    document.getElementById('month-search').value = '';
    document.getElementById('month-channel').value = 'all';
    if (document.getElementById('month-research')) document.getElementById('month-research').value = 'included';
    syncTabs();
    updateRows();
  }
  window.bindMonth = function bindMonth(data, options = {}) {
    activate(data, options.variant || 'month');
    if (!data || !document.getElementById('month-rows')) return;
    indexedRows = list(data.domains).map(row => ({row, search: [row.domain, row.title, row.description, ...list(row.keywordCandidates).map(k => k.phrase)].filter(present).join('\n').toLocaleLowerCase()}));
    document.getElementById('month-search').addEventListener('input', event => {state.q = event.target.value; state.page = 1; updateRows();});
    document.getElementById('month-channel').addEventListener('change', event => {state.channel = event.target.value; state.page = 1; updateRows();});
    document.getElementById('month-research')?.addEventListener('change', event => {state.research = event.target.value; state.page = 1; updateRows();});
    document.querySelectorAll('[data-month-verdict]').forEach(button => button.addEventListener('click', () => {state.verdict = button.dataset.monthVerdict; state.page = 1; syncTabs(); updateRows();}));
    document.getElementById('month-clear').addEventListener('click', () => resetFilters());
    document.getElementById('month-show-methods').addEventListener('click', () => {const details = document.getElementById('month-methods'); details.open = true; details.scrollIntoView({block: 'start', behavior: 'auto'});});
    document.getElementById('month-prev').addEventListener('click', () => {state.page--; updateRows(); document.getElementById('month-count').scrollIntoView({block: 'start', behavior: 'auto'});});
    document.getElementById('month-next').addEventListener('click', () => {state.page++; updateRows(); document.getElementById('month-count').scrollIntoView({block: 'start', behavior: 'auto'});});
    updateRows();
  };
})();
