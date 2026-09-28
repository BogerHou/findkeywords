(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = value => Number(value).toLocaleString('zh-CN');
  const state = {root:'all', mode:'domains', q:'', page:1};
  let data;
  function highlight(text, matches) {
    let end = 0, html = '';
    for (const match of matches) {
      html += esc(text.slice(end, match.start)) + '<mark>' + esc(text.slice(match.start, match.end)) + '</mark>';
      end = match.end;
    }
    return html + esc(text.slice(end));
  }
  const rootNames = roots => roots.map(id => data.roots.find(r => r.id === id)?.term || id).join(' · ');
  function costPanel() {
    const plan = window.FINDKEYWORDS_COST_PLAN;
    if (!plan) return '<div class="notice">低成本请求计划尚未生成；查看说明后离线运行 scripts/build_cost_plan.py。</div>';
    const s = plan.summary;
    return `<section class="panel roots-prescreen"><h2>控制请求预算，先跑 ${num(s.queued)} 个</h2><p class="source-text"><strong>AWS 采集队列 · 实际结果见下方运行记录。</strong> ${num(s.inputDomains)} 是线索总数，不是必须访问的数量。当前电脑只做离线筛选。</p><div class="prescreen-steps"><div><strong>1 · 复用与同名暂缓</strong><p>${num(s.reuseHistorical)} 个先看历史记录；同名不同后缀暂缓 ${num(s.sameNameDeferred)} 个。旧失败不等于永久失效，同名也不等于同站。</p></div><div><strong>2 · 优先级与探索份额</strong><p>${num(s.priorityPool)} 个进入请求优先池，${num(s.explorationPool)} 个保留探索。首批取 ${num(s.priorityQueued)} + ${num(s.explorationQueued)} 个；这是预算，不是有效站点数量。</p></div><div><strong>3 · 只取轻量内容</strong><p>首页读取上限 128 KiB，robots.txt 32 KiB，不加载图片或执行脚本。截断和访问失败保留待查；只有实际内容才能提供关键词证据。</p></div></div><details class="data-disclosure"><summary>查看筛选规则与流量演算</summary><p class="source-text">${num(s.broadOnlyDomains)} 个只命中 Online、Example、Sample、Format、Scheme、Pattern 等宽泛词根，调低请求优先级但保留。优先池要求其他词根出现在名称开头或结尾，名称≤24字符、数字≤2、连字符≤1且无连续连字符、无四连重复字符。未要求词典收录，避免排除新造词。</p><p class="source-text">假设每域名总响应体平均 50 KiB：100 个约 4.9 MiB，全量约 786 MiB；这不是实测，不含 DNS、TLS 等开销。限速控制频率，减少队列和响应体才直接减少下载量。完整分类和抽样依据均可下载。</p><p class="source-text">串行、全局至少2秒、同主机至少5秒；遇到429暂停。网页默认只展示快照；AWS 服务器先做本机网络配置，再显式启动，才会访问候选域名。没有自动查询Google Trends。</p></details><details class="data-disclosure"><summary>查看本次 ${num(s.queued)} 个候选与入选通道</summary><div class="roots-results">${plan.queue.map(r=>`<div class="root-result"><div class="budget-candidate"><strong>${esc(r.domain)}</strong><span>${r.lane==='priority'?'优先池':'探索池'} · ${esc(rootNames([r.sampling_root]))}</span></div></div>`).join('')}</div></details><p class="source-text">更直接的补充路径：从词根的 Trends 相关上升查询找候选，再复核近30天和半年背景，最后只查看少量相关网站。当前仍无本轮已确认的新词。</p><div class="roots-files"><a href="../reports/low-cost-plan-2026-09-28.md" target="_blank" rel="noopener">完整筛选规则与预算演算 ↗</a><a href="prescreen-queue.json" download>下载100个请求候选</a><a href="cost-plan.json" target="_blank" rel="noopener">统计、规则与输入校验值 ↗</a><a href="probe-cache-index.json" target="_blank" rel="noopener">历史记录索引 ↗</a></div></section>`;
  }
  function prescreenPanel() {
    const run = window.FINDKEYWORDS_PRESCREEN_RESULTS;
    if (!run) return '<section class="panel"><h2>AWS 运行记录</h2><p>本批结果尚未同步到这个网页快照。实际运行日志保存在服务器 results/aws-pilot-01。</p></section>';
    const s = run.summary, d = s.decisions;
    const names = {html_with_content:'有网页内容，待提词复核', homepage_missing:'首页不存在', parking_page:'停放或售卖页', placeholder_page:'默认或建设中页面', soft_404:'页面提示不存在', non_html:'非 HTML 内容', tls_handshake_error:'TLS 握手失败', tls_certificate_error:'证书验证失败', timeout:'超时', dns_error:'DNS 解析失败', connect_error:'连接失败', homepage_too_large:'首页超过读取上限', robots_too_large:'robots 超过读取上限', robots_returned_html:'robots 返回 HTML', robots_complex_rules:'复杂 robots 规则，待复查', robots_disallowed:'robots 禁止抓取', external_or_unsupported_redirect:'跨站或不支持的跳转', javascript_or_thin:'依赖脚本或内容过少', thin_or_empty:'内容过少或空白', http_blocked:'网站拒绝访问', challenge:'人机验证页面', rate_limited:'触发限流', https_downgrade:'跳转到 HTTP'};
    const labels = {pass:'自动通过 · 待复核',skip:'本轮跳过',recheck:'待复查'};
    return `<section class="panel roots-prescreen" id="aws-results"><h2>${esc(run.label)}</h2><p class="source-text"><strong>已处理 ${num(s.completed)} / ${num(s.queued)} 个 · 待处理 ${num(s.pending)} 个。</strong> ${s.stop_reason ? '任务已暂停：'+esc(s.stop_reason) : '本批已结束。'} ${esc(run.note)}</p>${run.contentReview?`<p class="notice"><strong>内容复核纠正 ${num(run.contentReview.items.length)} 个明显误收；自动通过项还剩 ${num((d.pass||0)-run.contentReview.items.filter(r=>r.decision==='skip').length)} 个待进一步核查。</strong> ${esc(run.contentReview.method)}</p>`:""}<div class="prescreen-steps"><div><strong>${num(d.pass||0)} 个 · 自动判为有内容</strong><p>从实际网页取得内容；纠正明显误收后再提词。</p></div><div><strong>${num(d.skip||0)} 个 · 本轮跳过</strong><p>缺失页、停放页、默认页等，依据见逐条记录。</p></div><div><strong>${num(d.recheck||0)} 个 · 待复查</strong><p>失败、超限、访问规则等，不直接判为无价值。</p></div></div><details class="data-disclosure"><summary>逐域名查看结果、Title、Description、H1 与请求记录</summary><div class="roots-results">${run.rows.map(r=>`<details class="root-result"><summary><span><strong>${esc(r.domain)}</strong><small>${esc(names[r.reason]||r.reason)}</small></span><span>${esc(r.review?'复核：本轮跳过':labels[r.decision]||r.decision)}</span></summary><div class="root-evidence">${r.review?`<p><strong>内容复核：</strong>${esc(r.review.reason)}；依据 ${esc(r.review.field)}：${esc(r.review.quote)}</p>`:""}<p>采集时间：${esc(r.checkedAt)} · ${r.lane==='priority'?'优先池':'探索池'}${r.incomplete?' · HTML 仅前缀，证据不完整':''}</p>${r.page?`<p><strong>Title：</strong>${esc(r.page.title)}</p><p><strong>Description：</strong>${esc(r.page.description)}</p><p><strong>H1：</strong>${esc((r.page.h1||[]).join(' | '))}</p>`:'<p>本次未取得可用的完整页面字段。</p>'}<p>${r.requests.map(q=>`${esc(q.stage)} · ${esc(q.url)} · HTTP ${esc(q.http_status??'未知')} · ${esc(q.status)}`).join('<br>')}</p></div></details>`).join('')}</div></details><p class="source-text">已记录的 HTTP 尝试 ${num(run.knownHttpAttempts)} 次${run.unknownAttemptRecords?'；另有 '+num(run.unknownAttemptRecords)+' 条调用的请求次数未知':''}。${run.metrics?.saved_decoded_response_bytes!=null?`保存响应体 ${(run.metrics.saved_decoded_response_bytes/1048576).toFixed(2)} MiB（解码后）。`:""}不是完整链路流量统计。原始响应体留在 AWS，下载快照包含原始结果文件的 SHA-256，可与服务器核对。</p><div class="roots-files"><a href="prescreen-results.json" download>下载本批结果与证据字段</a><a href="../reports/aws-deployment-2026-09-28.md" target="_blank" rel="noopener">AWS 部署、运行与核查说明 ↗</a></div></section>`;
  }
  window.renderRoots = value => {
    data = value;
    if (!data) return '<div class="notice">词根数据尚未生成。运行 scripts/build_roots_site.py 后刷新。</div>';
    const s = data.summary, m = data.meta;
    return `<section class="roots-page">
      <div class="page-header"><div><div class="eyebrow">KEYWORD ROOTS / ${esc(m.runDate)}</div><h1>从词根开始，寻找刚起量的词</h1><p>${esc(m.goal)} 先用这 ${num(s.roots)} 个词根收集线索，再检查网页内容和真实趋势。</p></div><a class="btn btn-secondary" href="keyword-roots.txt" download>下载词根清单</a></div>
      <div class="metric-strip"><div class="metric-item"><span>已启用词根</span><strong>${num(s.roots)}</strong><small>按你提供的顺序，全部保留</small></div><div class="metric-item"><span>历史域名名称命中</span><strong>${num(s.matchedDomains)}</strong><small>全量 ${num(s.inputDomains)} 个域名重筛</small></div><div class="metric-item"><span>历史关键词命中</span><strong>${num(s.matchedKeywords)}</strong><small>从已有 ${num(s.inputKeywords)} 个词筛出</small></div><div class="metric-item"><span>本轮新增趋势查询</span><strong>${num(s.currentTrendQueries)}</strong><small>词根命中，尚未确认新词机会</small></div></div>
      <div class="notice"><strong>本步完成词根筛选，趋势仍待查。</strong> ${esc(m.note)} 历史词的趋势范围为 ${esc(m.historicalTrendWindow.start)} 至 ${esc(m.historicalTrendWindow.end)}。按 ${esc(m.runDate)} 计算的新窗口为 <strong>${esc(m.nextTrendWindow.start)} 至 ${esc(m.nextTrendWindow.end)}</strong>，本轮尚未查询。</div>
      <section class="panel roots-goal"><h2>本轮只找：近30天刚起量、增长迅猛</h2><p class="source-text">稳定老词、温和上涨和孤立尖峰不作为本轮目标。过去按 20% 升幅得到的候选保留在历史记录中，不视为符合新目标。</p><details class="data-disclosure"><summary>查看后续趋势复核要求</summary><ul>${data.trendReview.requirements.map(r=>`<li>${esc(r)}</li>`).join('')}</ul></details></section>
      ${costPanel()}
      ${prescreenPanel()}
      <details class="panel roots-catalog" open><summary><strong>${num(s.roots)} 个筛选词根</strong><span>点击词根查看命中 · 数量是线索数量</span></summary><div class="roots-grid">${data.roots.map(r=>`<button type="button" class="root-choice" data-root="${esc(r.id)}" aria-pressed="${state.root===r.id}"><span><strong>${esc(r.term)}</strong><small>${esc(r.meaning)}</small></span><span class="root-counts">${num(r.domainCount)} 域名 · ${num(r.keywordCount)} 词</span></button>`).join('')}</div><p class="source-text">同一域名可能命中多个词根，各词根数量不可相加。Online 等宽泛词根仍保留，后续由网页证据和趋势决定是否入选。</p></details>
      <div class="section-heading"><div><h2>命中结果</h2><p>域名名称与已有关键词分别匹配，可搜索、筛选并展开来源。</p></div></div>
      <div class="toolbar"><div class="search-field"><span class="search-symbol">⌕</span><input class="search-input" type="search" id="roots-search" aria-label="搜索词根筛选结果" placeholder="搜索域名、关键词或来源" value="${esc(state.q)}"></div><select class="control" id="roots-mode" aria-label="选择结果类型"><option value="domains"${state.mode==='domains'?' selected':''}>域名名称线索 · ${num(s.matchedDomains)}</option><option value="keywords"${state.mode==='keywords'?' selected':''}>历史关键词 · ${num(s.matchedKeywords)}</option></select><select class="control" id="roots-filter" aria-label="选择词根"><option value="all">全部 51 个词根</option>${data.roots.map(r=>`<option value="${esc(r.id)}"${state.root===r.id?' selected':''}>${esc(r.term)} · ${esc(r.meaning)}</option>`).join('')}</select><button class="btn btn-secondary" id="roots-reset">清除筛选</button></div>
      <p class="source-text" id="roots-discovery"></p>
      <div class="table-meta"><span id="roots-count" aria-live="polite"></span><span>按名称排序 · 每页 50 条</span></div><div class="roots-results" id="roots-results"></div><div class="t30-pagination"><span id="roots-page-label"></span><div><button class="btn btn-secondary" id="roots-prev">← 上一页</button><button class="btn btn-secondary" id="roots-next">下一页 →</button></div></div>
      <details class="panel roots-rules"><summary><strong>完整匹配规则与复算文件</strong></summary><ol>${data.rules.map(r=>`<li>${esc(r)}</li>`).join('')}</ol><p>例：<code>pdfconverter.com</code> 命中 Converter；<code>convert PDF online</code> 命中 Convert 和 Online；<code>viewer.online</code> 只命中 Viewer；<code>templates</code> 不自动扩展为 Template。</p><div class="roots-files"><a href="roots-config.json" target="_blank" rel="noopener">51 词根与目标配置 ↗</a><a href="roots-data.json" target="_blank" rel="noopener">完整结果与输入校验值 ↗</a><a href="../reports/roots-${esc(m.runDate)}.md" target="_blank" rel="noopener">筛选报告 ↗</a></div></details>
    </section>`;
  };
  function filtered() {
    const q = state.q.trim().toLocaleLowerCase();
    return data[state.mode].filter(r => (state.root==='all'||r.roots.includes(state.root)) && (!q || [r.domain,r.keyword,...(r.sources||[]).map(s=>s.domain)].some(v=>String(v||'').toLocaleLowerCase().includes(q))));
  }
  function renderDomain(r) {
    const file = '../data/raw/month-2026-09-26/' + encodeURIComponent(r.sourceFile);
    return `<details class="root-result"><summary><span><strong>${highlight(r.domain,r.matches)}</strong><small>${esc(rootNames(r.roots))}</small></span><span>名称线索 · 待核实网页</span></summary><div class="root-evidence"><p>名单日期：${esc(r.sourceDate)}；不是已核验的注册或上线日期。</p><p>来源：<a href="${esc(file)}" target="_blank" rel="noopener">${esc(r.sourceFile)}</a>，第 ${num(r.sourceLine)} 行。</p><p>命中位置（从 0 开始，末位不含）：${r.matches.map(m=>`${esc(m.text)} [${m.start}, ${m.end})`).join('；')}。本步未据名称推断网站业务。</p></div></details>`;
  }
  function renderKeyword(r) {
    return `<details class="root-result"><summary><span><strong>${highlight(r.keyword,r.matches)}</strong><small>${esc(rootNames(r.roots))}</small></span><span>本轮趋势待查</span></summary><div class="root-evidence"><p>历史结果：${esc(r.historicalStatus)} · 查询组 ${esc(r.historicalCaptureId)}。<a href="#trends30/${encodeURIComponent(r.keyword)}">查看历史数列 →</a></p>${r.sources.map(s=>`<div class="root-source"><p><strong>${esc(s.domain)}</strong> · ${esc(s.source_field)}</p><blockquote>${esc(s.evidence_quote)}</blockquote><p>${esc(s.derivation || '')}</p></div>`).join('')}</div></details>`;
  }
  function update() {
    const rows = filtered(), pages = Math.max(1,Math.ceil(rows.length/50));
    state.page = Math.min(Math.max(1,state.page),pages);
    document.getElementById('roots-count').textContent = `${state.mode==='domains'?'域名名称线索':'历史关键词'}：${num(rows.length)} 条${state.root==='all'?'':` · ${rootNames([state.root])}`}`;
    document.getElementById('roots-page-label').textContent = `第 ${state.page} / ${pages} 页`;
    document.getElementById('roots-prev').disabled = state.page===1;
    document.getElementById('roots-next').disabled = state.page===pages;
    document.getElementById('roots-results').innerHTML = rows.length ? rows.slice((state.page-1)*50,state.page*50).map(state.mode==='domains'?renderDomain:renderKeyword).join('') : '<div class="panel empty-state">没有匹配结果。没有命中词根不代表没有价值，可清除筛选查看全部。</div>';
    document.querySelectorAll('[data-root]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.root===state.root)));
    const period = data.meta.nextTrendWindow;
    const url = 'https://trends.google.com/trends/explore?geo=US&date='+encodeURIComponent(period.start+' '+period.end)+'&q='+encodeURIComponent(state.root);
    document.getElementById('roots-discovery').innerHTML = state.root==='all' ? '选择一个词根后，也可以直接从 Google Trends 的相关上升查询寻找新词。这里提供查询入口，尚未采集结果。' : `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">用 ${esc(rootNames([state.root]))} 查看近30天相关上升查询 ↗</a> · 美国 · ${esc(period.start)} 至 ${esc(period.end)} · 仅查询入口，尚未采集`;
  }
  window.bindRoots = () => {
    if (!data) return;
    document.getElementById('roots-search').addEventListener('input',e=>{state.q=e.target.value;state.page=1;update();});
    document.getElementById('roots-mode').addEventListener('change',e=>{state.mode=e.target.value;state.page=1;update();});
    document.getElementById('roots-filter').addEventListener('change',e=>{state.root=e.target.value;state.page=1;update();});
    document.querySelectorAll('[data-root]').forEach(el=>el.addEventListener('click',()=>{state.root=state.root===el.dataset.root?'all':el.dataset.root;state.page=1;document.getElementById('roots-filter').value=state.root;update();document.getElementById('roots-count').scrollIntoView({block:'center'});}));
    document.getElementById('roots-reset').addEventListener('click',()=>{state.root='all';state.q='';state.page=1;document.getElementById('roots-filter').value='all';document.getElementById('roots-search').value='';update();});
    for(const [id,step] of [['roots-prev',-1],['roots-next',1]])document.getElementById(id).addEventListener('click',()=>{state.page+=step;update();document.getElementById('roots-count').scrollIntoView({block:'center'});});
    update();
  };
})();
