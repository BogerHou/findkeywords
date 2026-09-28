(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
  const list = value => Array.isArray(value) ? value : [];
  const num = value => value !== undefined && value !== null && value !== '' && Number.isFinite(Number(value)) ? Number(value).toLocaleString('zh-CN') : '待生成';
  const trendURL = (phrase, date) => 'https://trends.google.com/trends/explore?hl=zh-CN&geo=US&date=' + encodeURIComponent(date) + '&q=' + encodeURIComponent(phrase);
  const link = (url, label) => `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`;
  const nameLabels = {
    dictionary_segments: '通用词典完整分词',
    readable_coinage: '可读字符形态探索',
    short_abbreviation: '短缩写探索',
    alphanumeric_exploration: '少量数字名称探索'
  };
  const exclusionLabels = {
    encoded_idn: 'IDN 编码名称：本轮未做多语言分词',
    name_length_outside_2_32: '名称长度不在 2–32 字符',
    too_many_hyphens: '超过两个连字符或存在连续连字符',
    numeric_only: '名称全部为数字',
    repeated_character_run: '存在至少四个连续相同字符',
    too_many_digits: '数字超过两位或占比超过 40%',
    alphanumeric_not_short_enough: '带数字名称超过 16 字符',
    alphanumeric_no_name_clue: '带数字名称的字母部分未取得名称线索',
    no_dictionary_or_readability_clue: '未取得完整词典分词或本轮可读字符形态线索'
  };
  const defaultGroups = [
    {label: '常见通用后缀', tlds: ['com', 'net', 'org'], quota: '45%'},
    {label: '技术与应用方向', tlds: ['ai', 'io', 'app', 'dev', 'tech'], quota: '25%'},
    {label: '其他优先后缀', tlds: ['co', 'me', 'cc', 'tv'], quota: '20%'},
    {label: '其余后缀探索', tlds: [], quota: '10%'}
  ];
  function trendsWorkflow() {
    const trendSummary = window.FINDKEYWORDS_TRENDS30?.summary;
    const progress = trendSummary ? `已整理 ${num(trendSummary.terms)} 个词，实际查询 ${num(trendSummary.queried)} 个；${trendSummary.pending ? `尚有 ${num(trendSummary.pending)} 个待查。` : '当前提词队列已查完，数据不足仍单独标记。'}` : '逐站提词和实际查询结果正在整理。';
    return `<section class="panel tld-trends"><div class="section-heading"><div><h2>下一步：近30天，判断是否持续起量</h2><p>以近30天为主要筛选窗口，不限制行业。${progress}</p></div><a class="btn btn-secondary" href="#trends30">查看近30天实际结果 →</a></div>
      <div class="tld-window-grid"><div><span>主要窗口 · 最近 30 个完整日</span><strong>2026-08-27 — 2026-09-25</strong><p>看最近是否持续起量：多个日期仍有数据，近期水平是否高于同一窗口的前段，避免只看单次尖峰。</p></div><div><span>辅助背景 · 约 6 个月</span><strong>2026-03-26 — 2026-09-25</strong><p>需要时回看历史背景；不作为本轮的主要筛选窗口。</p></div></div>
      <ol class="month-rule-list"><li><strong>先整理词义：</strong>从 Title、Description、H1 原文中提炼可搜索的产品、功能或需求词，去掉品牌口号、整句广告和无关词。</li><li><strong>固定美国、网页搜索：</strong>保存实际查询词、日期范围、地区、搜索类型和原始数列，才能重复核查。</li><li><strong>近30天看持续起量：</strong>比较最后7天、此前7天和更早16天的同图水平，同时记录非零日期分布、峰值贡献及末段是否回落；不把单个尖峰当成持续增长。</li><li><strong>必要时补查背景：</strong>用半年或更长记录排除旧词回潮、季节性和短暂事件；是否“新出现”另行判断。</li></ol>
      <p class="tld-boundary">Trends 的 0 可能表示低于报告阈值。低搜索量的孤立尖峰也可能来自统计噪声，需要原始数列和重复查询复核。“第一次非零”只是在所查窗口中首次可见，不是这个词诞生的日期。不同查询窗口的 0–100 分别归一化，不能直接相除比较，更不能用 0 作分母计算增长。${link('https://support.google.com/trends/answer/4365533?hl=zh-Hans', 'Google 对趋势数据的说明')}</p>
      <p class="tld-boundary">研究范围内域名的“完整证据”中提供原文片段对应的两个查询入口；它们用于手动检查，点击链接不代表本工作台已经取得结果。本轮整理后的词及查询状态在 <a href="#trends30">近30天趋势</a>；旧的 32 个已查词仍在 <a href="#keywords">已查趋势词</a> 中。</p>
    </section>`;
  }
  window.renderTldIntro = function renderTldIntro(data) {
    const s = data?.summary || {};
    const old = window.FINDKEYWORDS_MONTH?.summary || {};
    const screening = data?.screening || {};
    const groups = list(screening.tldGroups).length ? screening.tldGroups : defaultGroups;
    const nameRules = list(screening.nameRules);
    const tldCounts = list(screening.tldCounts);
    const exclusions = Object.entries(screening.exclusions || {});
    return `<section class="panel tld-comparison"><div class="section-heading"><div><h2>两种方法并行，补充不同线索</h2><p>共用同一份月度名单，新增方法排除先前已核验域名，再走相同的网页和注册时间核验。</p></div></div>
      <div class="table-wrap"><table class="mini-table tld-comparison-table"><thead><tr><th>方法</th><th>如何选样</th><th>核验进度</th><th>保留域名</th></tr></thead><tbody><tr><td><a href="#month">原四通道方法</a></td><td>原词表、扩展词表、名称探索、无词表探索；其中后两类不要求命中词表。</td><td>${num(old.probed)} / ${num(old.probeSelected)}</td><td>${num(old.candidates)}</td></tr><tr><td>后缀与名称</td><td>后缀分组抽样＋名称形态判断；所有通道均不要求命中原词表。</td><td>${num(s.probed)} / ${num(s.probeSelected)}</td><td>${num(s.candidates)}</td></tr></tbody></table></div>
      <div class="notice tld-research-scope"><strong>内容规则保留 ${num(s.candidates)} → 本轮研究候选 ${num(s.researchCandidates)}</strong><p>在内容保留项中，暂跳过成人／博彩相关的 ${num(s.researchExcluded)} 条记录，研究范围内去重原文片段 ${num(s.researchUniqueKeywordPhrases)} 条。这是暂定研究偏好，不是网站质量或违法与否的结论。范围外记录仅展示中性别名与核验摘要，不提供原文、外链或趋势入口。另有 ${num(s.noncandidateDisplayReview)} 条未进入候选的原始页面命中展示隔离规则，暂保留中性摘要，等待进一步复核。</p></div><div class="tld-stat-line"><span>名称规则保留 <strong>${num(s.eligibleNames)}</strong></span><span>其中此前已探测 <strong>${num(s.previousProbeOverlap)}</strong>，本轮不重复</span><span>新样本未命中原 43 词 <strong>${num(s.selectedWithoutLegacyTerms)}</strong></span><span>两份词表均未命中 <strong>${num(s.selectedWithoutAnyTerms)}</strong></span></div>
      <p class="tld-boundary">这些数字用于查看增量覆盖，不是方法优劣的实验结论。未抽中的域名尚未判断页面质量；“名称规则保留”也不等于名称有意义或网站有价值。</p>
      <details class="tld-priorities"><summary>后缀优先级和名称规则</summary><p class="source-text">后缀是本轮的抽样偏好，不是“权威认证”，也不直接代表搜索排名、流量或网站质量。<code>.cc</code> 已纳入优先探索，同时给其他后缀保留入口。${link('https://developers.google.com/search/help/site-position-in-search-faq', 'Google 搜索说明')}</p>
      <div class="table-wrap"><table class="mini-table"><thead><tr><th>抽样组</th><th>后缀</th><th>计划占比</th></tr></thead><tbody>${groups.map(g => `<tr><td>${esc(g.label || g.id)}</td><td>${list(g.tlds).length ? list(g.tlds).map(t => '<code>.' + esc(String(t).replace(/^\./, '')) + '</code>').join(' ') : '其余有效后缀'}</td><td>${esc(g.quota || g.share || '见完整规则')}</td></tr>`).join('')}</tbody></table></div>
      ${nameRules.length ? `<ul class="month-rule-list">${nameRules.map(rule => `<li>${typeof rule === 'string' ? esc(rule) : `${rule.label ? `<strong>${esc(nameLabels[rule.label] || rule.label)}：</strong>` : ''}${esc(rule.rule || rule.description || '')}`}</li>`).join('')}</ul>` : '<p class="source-text">名称规则会随选样结果保存。只按名称特征估计可读性，不能确定词义；逐条通过原因将在域名证据中列出。</p>'}
      ${tldCounts.length ? `<details class="data-disclosure"><summary>逐后缀的输入、名称初筛及抽样数量（${num(tldCounts.length)} 个后缀）</summary><div class="table-wrap"><table class="mini-table"><thead><tr><th>后缀</th><th>输入域名</th><th>名称初筛通过</th><th>其中此前已探测</th><th>未探测待选池</th><th>实际选入</th></tr></thead><tbody>${tldCounts.map(t => `<tr><td><code>.${esc(String(t.tld).replace(/^\./, ''))}</code></td><td>${num(t.input)}</td><td>${num(t.eligible)}</td><td>${num(t.previously_probed)}</td><td>${num(t.unprobed_eligible)}</td><td>${num(t.selected)}</td></tr>`).join('')}</tbody></table></div></details>` : ''}
      ${exclusions.length ? `<details class="data-disclosure"><summary>未通过名称初筛的原因</summary><p class="tld-boundary">按规则先后记录首个不通过原因。这些域名只是未进入本方法的待选池，未据此认定为垃圾站或无价值网站。</p><div class="table-wrap"><table class="mini-table"><thead><tr><th>原因</th><th>域名数</th></tr></thead><tbody>${exclusions.map(([reason, count]) => `<tr><td>${esc(exclusionLabels[reason] || reason)}</td><td>${num(count)}</td></tr>`).join('')}</tbody></table></div></details>` : ''}
      <p class="tld-boundary">后续仍按实际页面处理停放、出售、默认页、待发布页、内容不足和跨域跳转。抓取失败单独记录，不直接称为“垃圾站”。完整数量、配额调剂和排除理由见下面的规则与原始文件。</p></details>
    </section>${trendsWorkflow()}`;
  };
  window.renderTldTrendsLinks = function renderTldTrendsLinks(words) {
    return `<div class="tld-phrase-queries"><strong>网页原文片段 / 手动查询入口</strong><p>以下直接查询保存的原文片段；长标题通常还需提炼。整理后的词和实际查询状态请看 <a href="#trends30">近30天趋势</a>。近30天为主，半年供背景参考。</p>${list(words).filter(k => k.phrase).map(k => `<div><span>${esc(k.phrase)}</span><nav aria-label="${esc(k.phrase)} 的趋势查询">${link(trendURL(k.phrase, '2026-08-27 2026-09-25'), '近30天 · 主要')}${link(trendURL(k.phrase, '2026-03-26 2026-09-25'), '半年 · 背景')}</nav></div>`).join('')}</div>`;
  };
  window.renderTldNameEvidence = function renderTldNameEvidence(row) {
    const segments = list(row.dictionarySegments);
    const diagnostics = (value, label) => `<p><strong>${label}：</strong>${list(value).length ? `${num(list(value).length)} 个命中（${list(value).map(esc).join('、')}）` : '0 个命中'}</p>`;
    return `<dt>名称通过路径</dt><dd>${esc(nameLabels[row.namePath] || row.namePath || '未记录')}<br><span class="subtle">名称形态只是初筛线索，不是含义确认。</span></dd><dt>词典分词</dt><dd>${segments.length ? segments.map(part => `<code>${esc(part)}</code>`).join(' + ') : '未取得词典分词；按上列名称路径进入。'}</dd><dt>词表命中诊断</dt><dd>${diagnostics(row.legacyMatches, '原 43 词表')}${diagnostics(row.expandedMatches, '扩展词表')}<p class="subtle">此处仅做覆盖对照，不参与本方法的准入；0 表示未命中。</p></dd>`;
  };
  window.renderTld = function renderTld(data) {
    if (!data) return `<section class="month-page"><div class="page-header"><div><div class="eyebrow">NAME DISCOVERY</div><h1>从名称，发现另一批网站。</h1><p>后缀与名称规则正在准备，逐域名结果尚未生成。</p></div></div>${window.renderTldIntro(null)}</section>`;
    return window.renderMonth(data, {variant: 'tld'});
  };
})();
