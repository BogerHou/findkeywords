(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const list = value => Array.isArray(value) ? value : [];
  const num = (value, digits = 0) => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? Number(value).toLocaleString('zh-CN', {maximumFractionDigits: digits}) : '—';
  const state = {q:'', status:'all', page:1};
  const colors = ['#166957','#557aa2','#ba7a39','#886496','#859d43'];
  const priorityLabels = {specific:'具体需求词',general:'一般词',brand:'品牌词'};
  const transformLabels = {verbatim:'直接原词',normalized:'原文归一',translated:'翻译提炼'};
  const statusDefaults = {pending:'尚未查询',no_data:'本次数据不足',insufficient:'信号不足',sustained:'持续起量候选',rising:'持续起量候选',sparse:'数据稀疏',spike:'孤立尖峰',cooling:'近期回落',stable:'未见持续上升',review:'待复核'};
  let data;
  const statusLabel = term => term.statusLabel || statusDefaults[term.status] || term.status || '尚未查询';
  const queried = term => {
    const capture = captureFor(term);
    return term.status && term.status !== 'pending' && capture && ['chart','no_data'].includes(capture.status) && list(capture.terms).some(word => String(word).trim().toLocaleLowerCase() === String(term.keyword).trim().toLocaleLowerCase());
  };
  function safeURL(value) {
    try { const u = new URL(value, location.href); return ['https:', 'http:', 'file:'].includes(u.protocol) ? esc(u.href) : '#'; }
    catch { return '#'; }
  }
  const ext = (url, label) => `<a href="${safeURL(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`;
  const captureFor = term => list(data?.captures).find(c => c.id === term.primaryCaptureId) || list(data?.captures).find(c => list(term.captureIds).includes(c.id));
  const seriesFor = (term, capture) => list(capture?.series)[list(capture?.terms).findIndex(w => String(w).toLocaleLowerCase() === String(term.keyword).toLocaleLowerCase())] || [];
  function spark(term) {
    const values = seriesFor(term, captureFor(term));
    if (!values.length) return `<span class="t30-no-spark">${queried(term) ? '无可绘制数列' : '等待实际查询'}</span>`;
    const pts = values.map((v,i) => `${(3+i/Math.max(1,values.length-1)*190).toFixed(2)},${(43-Number(v)/100*40).toFixed(2)}`).join(' ');
    return `<svg class="t30-spark" viewBox="0 0 196 46" role="img" aria-label="${esc(term.keyword)}：保存的近30天相对热度"><line x1="3" y1="43" x2="193" y2="43" stroke="#e1e7e9"/><polyline points="${pts}" fill="none" stroke="#166957" stroke-width="1.8" vector-effect="non-scaling-stroke"/></svg>`;
  }
  function statusBadge(term) { const tone = ['rising','emerging','sustained'].includes(term.status) ? 'tag-review' : term.status === 'cooling' ? 'tag-cooling' : ['zero','no_data','sparse','spike','insufficient'].includes(term.status) ? 'tag-insufficient' : 'tag-pending'; return `<span class="tag ${tone}">${esc(statusLabel(term))}</span>`; }
  function summaryHTML() {
    const s = data.summary || {};
    const actualQueried = list(data.terms).filter(queried).length;
    const pending = list(data.terms).length - actualQueried;
    return `<div class="metric-strip t30-metrics"><div class="metric-item"><span>逐站阅读覆盖</span><strong>${num(s.reviewedDomains)}</strong><small>${num(s.domainsWithTerms)}站提词 · ${num(s.skippedDomains)}站未提词</small></div><div class="metric-item"><span>整理后的词</span><strong>${num(list(data.terms).length)}</strong><small>每词保留来源与提炼依据</small></div><div class="metric-item"><span>已实际查询</span><strong>${num(actualQueried)}</strong><small>${num(list(data.captures).length)} 组保存记录</small></div><div class="metric-item"><span>尚未查询</span><strong>${num(pending)}</strong><small>${pending ? '没有查询结果，不预判趋势' : '队列已查完；数据不足仍单列'}</small></div></div>`;
  }
  function coverageHTML() {
    const s = data.summary || {}, a = s.signalPatternAudit;
    if(s.multiTermCoverage === undefined) return '';
    const share = count => a?.nonzeroChartTerms ? `${num(100*count/a.nonzeroChartTerms,1)}%` : '—';
    return `<section class="panel t30-resources"><h2>查询覆盖，怎样计算？</h2><p>多词比较图覆盖 <strong>${num(s.multiTermCoverage)} 个词</strong>（${num(s.multiTermCaptures)} 组）；单词查询覆盖 <strong>${num(s.singleTermCoverage)} 个词</strong>（${num(s.singleTermCaptures)} 次）。其中在比较图之后进行的单词复查为 ${num(s.singleTermRecheckCoverage)} 个词、${num(s.singleTermRecheckCaptures)} 次。两种覆盖有重叠，不能相加。</p><p class="source-text">“已实际查询”按去重词计算，不表示逐个词单独查询。当前 ${num(s.comparisonOnlyTerms)} 个词只有多词图记录。即使队列全部查完，多词图全零或无图仍需单词独立复查；取得记录不等于取得有效信号，也不等于确认没有需求。</p>${a ? `<details class="data-disclosure"><summary>查看共同形态：${esc(a.boundaryDate)} 首次非零 ${num(a.firstNonzeroOnBoundaryTerms)} 词</summary><p>${esc(a.basis)} 当前 ${num(a.nonzeroChartTerms)} 词有非零数值、${num(a.allZeroChartTerms)} 词同图全零、${num(a.noDataTerms)} 词未取得图表。</p><div class="raw-data"><table class="mini-table"><thead><tr><th>保存数列的形态</th><th>词数</th><th>占非零词比例</th></tr></thead><tbody><tr><td>前16日全零，后段至少一次非零</td><td>${num(a.earlyZeroLateNonzeroTerms)}</td><td>${share(a.earlyZeroLateNonzeroTerms)}</td></tr><tr><td>首次非零恰在 ${esc(a.boundaryDate)}</td><td>${num(a.firstNonzeroOnBoundaryTerms)}</td><td>${share(a.firstNonzeroOnBoundaryTerms)}</td></tr><tr><td>前16日全零，后14日每天非零</td><td>${num(a.earlyZeroLateAllNonzeroTerms)}</td><td>${share(a.earlyZeroLateAllNonzeroTerms)}</td></tr></tbody></table></div><p class="source-text">三种形态有重叠，不能相加。该日期首次非零的词分布在 ${num(a.firstNonzeroOnBoundaryGroups)} 个主要查询组；这只是描述统计，不是显著性检验，也不改变逐词分类。</p><p>${esc(a.note)}</p>${list(a.boundaryFirstRecords).length ? `<p class="source-text">可核查示例：${list(a.boundaryFirstRecords).slice(0,6).map(r=>`${esc(r.keyword)}（${esc(r.captureId)}）`).join('；')}。在下方搜索词可展开原始数列。</p>` : ''}</details>` : ''}</section>`;
  }
  window.renderTrends30 = function renderTrends30(value, keywordFilter = '') {
    if (keywordFilter) {state.q = keywordFilter;state.status = 'all';state.page = 1;}
    data = value;
    if (!data) return `<section class="trends30-page"><div class="page-header"><div><div class="eyebrow">TRENDS / 30 DAYS</div><h1>近30天，是否持续起量？</h1><p>结果数据正在整理，完成后刷新此页即可查看。尚未载入数据不表示关键词没有搜索量。</p></div></div><a href="#tld">返回域名来源 →</a></section>`;
    const statuses = [...new Map(list(data.terms).map(t => [t.status || 'pending', statusLabel(t)])).entries()];
    const meta = data.meta || {};
    const pending = list(data.terms).filter(t => !queried(t)).length;
    return `<section class="trends30-page"><div class="page-header"><div><div class="eyebrow">TRENDS / 30 DAYS</div><h1>近30天，是否持续起量？</h1><p>从实际网页整理搜索词，再查看近30天的变化。保留各行业线索；“具体需求词”只描述词义，不代表新词或已有流量。</p><div class="t30-query-scope">${esc(meta.start || '未记录')} — ${esc(meta.end || '未记录')} · ${esc(meta.geo === 'US' ? '美国' : meta.geo || '地区未记录')} · ${esc(meta.searchType || '网页搜索')} · 搜索字词</div></div><a class="btn btn-secondary" href="#tld">域名与网页来源 →</a></div>
      <div class="notice"><strong>历史趋势快照。</strong> 本页保留 2026-09-26 的查询与旧规则。当前目标为“近30天刚起量、增长迅猛”，<a href="#roots">前往新的词根筛选 →</a>。旧规则的 20% 升幅候选不等于符合当前目标。</div>${summaryHTML()}
      <p class="source-text">${pending ? `已保存部分查询结果，仍有 ${num(pending)} 个词待查；未查不等于淘汰。` : '当前提词队列已全部实际查询；这表示查询覆盖完成，不表示每个词都取得了可用数列。'}${meta.latestCaptureAt ? ` 最近采集：${esc(meta.latestCaptureAt)}。` : ''}</p>
      ${data.collection?.status==='temporarily_blocked' && pending ? `<div class="notice"><strong>Google 暂时限制查询，尚未全部查完。</strong> ${esc(data.collection.message)} 当前保留 ${num(pending)} 个待查词，页面错误没有记为零值或数据不足。记录时间：${esc(data.collection.observedAt)}。</div>` : ''}
      ${list(data.collection?.pendingCandidateRechecks).length ? `<div class="notice"><strong>候选仍待单词复查。</strong> ${list(data.collection.pendingCandidateRechecks).map(esc).join('、')} 当前只有多词比较记录。即使队列已全部覆盖，这项复查仍未完成，不能将候选写成已确认机会。</div>` : ''}
      <div class="notice"><strong>这是相对趋势初筛。</strong> 起量判断来自同一张图内的完整日数列，不同图的指数不能比较规模；0 或数据不足不等于没有搜索。最近出现可见数据，也不等于一个词刚诞生。尚未核验搜索量、竞争度或建站机会。</div>
      ${coverageHTML()}
      <details class="data-disclosure t30-rules"><summary>展开本轮规则与统计口径</summary><ol>${list(data.rules).map(rule => `<li>${esc(rule)}</li>`).join('')}</ol><p class="source-text">${esc(meta.captureMethod || '来自实际查询时保存的页面数列。具体来源与采集时刻见每条记录。')} 这些阈值用于整理研究顺序，不是显著性检验或趋势保证。需要时另查半年背景并重复采样。</p></details>
      <div class="toolbar t30-toolbar"><div class="search-field"><span class="search-symbol">⌕</span><input type="search" class="search-input" id="trends30-search" value="${esc(state.q)}" placeholder="搜索关键词、行业或来源域名" aria-label="搜索关键词、行业或来源域名"></div><label class="field"><span class="sr-only">按查询状态筛选</span><select class="control" id="trends30-status"><option value="all">全部状态</option>${statuses.map(([id,label]) => `<option value="${esc(id)}"${state.status===id?' selected':''}>${esc(label)} · ${num(list(data.terms).filter(t=>(t.status||'pending')===id).length)}</option>`).join('')}</select></label><button class="btn btn-secondary" id="trends30-reset">清除筛选</button></div>
      <div class="table-meta t30-table-meta"><span id="trends30-count" aria-live="polite"></span><span>起量候选与已查优先 · 每页50词 · 展开可核查原文与数列</span></div><div id="trends30-rows" class="t30-rows"></div><div class="t30-pagination"><span id="trends30-page-label"></span><div><button class="btn btn-secondary btn-small" id="trends30-prev">← 上一页</button><button class="btn btn-secondary btn-small" id="trends30-next">下一页 →</button></div></div>
      <section class="panel t30-resources"><h2>数据与复核文件</h2><p class="source-text">保存的快照可核查当时结果；重新打开 Google Trends 时，采样和数据可能变化。这里的链接使用明确日期范围。</p><div class="t30-resource-links">${list(data.resources).map(r => `<div>${ext(r.path,r.title)}<p>${esc(r.description || '')}</p></div>`).join('') || '<p class="subtle">原始记录将随数据构建保存。</p>'}</div></section></section>`;
  };
  function filtered() {
    const q = state.q.trim().toLocaleLowerCase();
    return list(data.terms).filter(t => (state.status==='all'||(t.status||'pending')===state.status) && (!q||[t.keyword,t.theme,...list(t.sources).flatMap(s=>[s.domain,s.evidence_quote])].some(v=>String(v||'').toLocaleLowerCase().includes(q)))).map((t,i)=>({t,i})).sort((a,b)=>Number(['rising','emerging'].includes(b.t.status))-Number(['rising','emerging'].includes(a.t.status))||Number(queried(b.t))-Number(queried(a.t))||a.i-b.i).map(x=>x.t);
  }
  function sourcesHTML(term) {
    return `<section class="t30-sources"><h3>这个词从哪里来</h3>${list(term.sources).map(s => `<article class="t30-source"><div class="t30-source-heading">${ext('https://'+s.domain,s.domain)}<span>${esc(s.source_field)} · ${esc(transformLabels[s.transformation] || s.transformation || '提炼词')}</span></div><blockquote class="source-quote">${esc(s.evidence_quote)}</blockquote><p>${esc(s.derivation)}</p></article>`).join('') || '<p class="subtle">本条来源尚未载入。</p>'}</section>`;
  }
  function backgroundHTML(term) {
    const b=term.background;if(!b)return '';
    const dates=list(b.dates),values=list(b.values);
    return `<section class="t30-background"><h3>半年背景复查</h3><p class="t30-reason">${esc(b.reason || '请结合保存的背景记录判断，不把30日窗口内首次可见当成新词诞生。')}</p><dl class="evidence-list"><dt>背景区间</dt><dd>${esc(b.start)} — ${esc(b.end)}</dd><dt>采集时刻</dt><dd>${esc(b.captured_at || '未记录')}（原始时间）</dd><dt>查询URL</dt><dd>${ext(b.url,b.url || '未记录')}</dd></dl>${dates.length && values.length ? `<details class="data-disclosure"><summary>半年背景原始数值 · ${num(dates.length)} 个日期标签</summary><div class="raw-data"><table class="mini-table"><thead><tr><th scope="col">日期（统一格式）</th><th scope="col">${esc(term.keyword)} · 相对指数</th></tr></thead><tbody>${dates.map((date,i)=>`<tr><td>${esc(date)}</td><td>${num(values[i])}</td></tr>`).join('')}</tbody></table></div></details>` : '<p class="t30-metric-footnote">本次背景查询未取得可用数列，不能据此断言更早没有搜索。</p>'}<p class="t30-metric-footnote">半年与30天图分别归一化，指数不能直接相除；日期已统一为 YYYY-MM-DD，顺序与原图一致。背景复查用于识别较早需求，不替代季节性和更长历史核查。</p></section>`;
  }
  function metricsHTML(term) {
    const m = term.metrics || {};
    return `<div class="t30-period-metrics"><div><span>最早16天均值</span><strong>${num(m.earlyMean,2)}</strong></div><div><span>此前7天均值</span><strong>${num(m.previousMean,2)}</strong></div><div><span>最近7天均值</span><strong>${num(m.recentMean,2)}</strong></div><div><span>最近7天 / 此前7天</span><strong>${m.recentRatio === null || m.recentRatio === undefined ? '不可计算' : num(m.recentRatio,2)+' 倍'}</strong></div></div><p class="t30-metric-footnote">全窗非零 ${num(m.nonzeroDays)} / 30 天 · 最近7天非零 ${num(m.recentNonzero)} / 7 · 此前7天非零 ${num(m.previousNonzero)} / 7 · 单日峰值占全窗指数总和 ${m.peakShare === null || m.peakShare === undefined ? '—' : num(Number(m.peakShare)*100,1)+'%'}。均值是本条主要查询组内的指数，不是搜索次数；分母为0时不计算增长倍数。</p>`;
  }
  function termBody(term, slot) {
    const captures = list(data.captures).filter(c => list(term.captureIds).includes(c.id));
    const main = captureFor(term);
    return `<div class="t30-term-body">${queried(term) ? `<section class="t30-analysis"><h3>本轮观察</h3><p class="subtle">判断依据：主要查询组 ${esc(term.primaryCaptureId || '未记录')}</p><p class="t30-reason">${esc(term.reason || '以保存的查询数据为准，结论待复核。')}</p>${term.metrics ? metricsHTML(term) : '<p class="t30-metric-footnote">本次未取得可用数列，三段均值和增长倍数均无法计算。</p>'}${captures.length ? `<div class="t30-capture-selector"><label for="t30-capture-${slot}">保存的查询组</label><select class="control" id="t30-capture-${slot}">${captures.map(c=>`<option value="${esc(c.id)}"${c.id===main?.id?' selected':''}>${esc(c.id)} · ${c.status==='no_data'?'本次数据不足':num(list(c.dates).length)+'个日期'}</option>`).join('')}</select></div><div class="t30-capture-body" id="t30-capture-body-${slot}"></div>` : '<p class="subtle">本条还没有载入可核查的查询记录。</p>'}</section>` : `<div class="notice"><strong>尚未实际查询。</strong> 当前只有网页提词依据，没有已取得的Trends数列。不能将它判断为上涨、下降、无搜索量或新词。</div>`}${backgroundHTML(term)}${sourcesHTML(term)}</div>`;
  }
  function updateRows() {
    const rows=filtered(), pages=Math.max(1,Math.ceil(rows.length/50)); state.page=Math.min(pages,Math.max(1,state.page));
    const page=rows.slice((state.page-1)*50,state.page*50);
    document.getElementById('trends30-count').textContent=`显示 ${num(rows.length)} / ${num(list(data.terms).length)} 个词`;
    document.getElementById('trends30-page-label').textContent=`第 ${state.page} / ${pages} 页${rows.length?' · '+num((state.page-1)*50+1)+'–'+num(Math.min(state.page*50,rows.length)):''}`;
    document.getElementById('trends30-prev').disabled=state.page===1;
    document.getElementById('trends30-next').disabled=state.page===pages;
    document.getElementById('trends30-rows').innerHTML=page.length?page.map((t,i)=>`<details class="t30-term" data-t30-slot="${i}"><summary><span class="t30-word"><strong>${esc(t.keyword)}</strong><small>${esc(t.theme || '未分类')} · ${esc(priorityLabels[t.priority] || '网页提词')} · ${num(list(t.sources).length)} 个来源</small></span><span class="t30-row-status">${statusBadge(t)}${queried(t)&&t.metrics?`<small>三段均值 ${num(t.metrics.earlyMean,1)} / ${num(t.metrics.previousMean,1)} / ${num(t.metrics.recentMean,1)}</small>`:''}</span>${spark(t)}<span class="t30-expand" aria-hidden="true">展开 ↓</span></summary><div class="t30-body-slot"></div></details>`).join(''):'<div class="panel empty-state"><h2>没有匹配的词</h2><p>更换搜索内容或清除状态筛选。</p></div>';
    document.querySelectorAll('[data-t30-slot]').forEach(el=>el.addEventListener('toggle',()=>{
      if(!el.open||el.dataset.loaded)return;
      const slot=Number(el.dataset.t30Slot), term=page[slot];el.querySelector('.t30-body-slot').innerHTML=termBody(term,slot);el.dataset.loaded='true';
      const select=document.getElementById(`t30-capture-${slot}`);
      if(select){const draw=()=>renderCapture(term,list(data.captures).find(c=>c.id===select.value),slot);select.addEventListener('change',draw);draw();}
    }));
  }
  function renderCapture(term,c,slot) {
    const el=document.getElementById(`t30-capture-body-${slot}`);if(!el||!c)return;
    const dates=list(c.dates), names=list(c.terms), series=list(c.series), target=names.findIndex(w=>String(w).toLocaleLowerCase()===String(term.keyword).toLocaleLowerCase());
    const captureMeta=`${c.id!==term.primaryCaptureId ? '<p class="notice">当前展开的是较早的查询组。上方判断与三段均值仍以标明的主要查询组为准。</p>' : ''}<dl class="evidence-list t30-capture-meta"><dt>查询组</dt><dd>${esc(c.id)}</dd><dt>采集时刻</dt><dd>${esc(c.captured_at || '未记录')}（原始时间）</dd><dt>实际同图词</dt><dd>${names.map(esc).join(' · ') || '未记录'}</dd><dt>查询URL</dt><dd>${ext(c.url,c.url || '未记录')}</dd></dl><p class="chart-context">${esc(data.meta?.captureMethod || '数列来自查询时保存的页面表格。')} 同图使用共同的0–100标度；不能拿其他查询组中的数值直接比较大小。</p>`;
    if(c.status==='no_data'||!dates.length||!series.some(s=>list(s).length)){
      el.innerHTML=`<div class="t30-no-data"><strong>本次查询没有取得可绘制数列</strong><p>这不等于零搜索量。保留完整查询条件供复查。</p></div>${captureMeta}`;return;
    }
    const W=850,H=255,L=40,R=18,T=18,B=34;
    const x=i=>L+i/Math.max(1,dates.length-1)*(W-L-R),y=v=>H-B-Number(v)/100*(H-T-B);
    const paths=series.map((values,i)=>`<polyline fill="none" stroke="${colors[i%colors.length]}" stroke-width="${i===target?2.6:1.4}" stroke-opacity="${i===target?1:.62}" vector-effect="non-scaling-stroke" points="${list(values).map((v,j)=>`${x(j).toFixed(2)},${y(v).toFixed(2)}`).join(' ')}"/>`).join('');
    el.innerHTML=`<div class="t30-chart-heading"><strong>同图全部词 · 相对热度0–100</strong><span>当前词用较粗曲线标出</span></div><div class="t30-chart"><svg class="t30-chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(c.id)}：${names.map(esc).join('、')} 的近30天相对热度"><title>${esc(term.keyword)}的完整同图对比</title>${[0,25,50,75,100].map(v=>`<line class="gridline" x1="${L}" y1="${y(v)}" x2="${W-R}" y2="${y(v)}"/><text x="${L-10}" y="${y(v)+4}" text-anchor="end">${v}</text>`).join('')}${[0,Math.floor((dates.length-1)/2),dates.length-1].map((i,j)=>`<text x="${x(i)}" y="${H-7}" text-anchor="${j===0?'start':j===2?'end':'middle'}">${esc(dates[i])}</text>`).join('')}${paths}<line class="crosshair" data-t30-crosshair x1="${x(dates.length-1)}" x2="${x(dates.length-1)}" y1="${T}" y2="${H-B}"/></svg></div><div class="t30-chart-readout" aria-live="polite"></div><input type="range" class="date-slider" min="0" max="${dates.length-1}" value="${dates.length-1}" aria-label="查看 ${esc(c.id)} 的日期与同图指数"><div class="t30-chart-legend">${names.map((name,i)=>`<span${i===target?' class="t30-selected-series"':''}><svg width="17" height="10" aria-hidden="true"><line x1="0" x2="17" y1="5" y2="5" stroke="${colors[i%colors.length]}" stroke-width="3"/></svg>${esc(name)}</span>`).join('')}</div>${captureMeta}<details class="data-disclosure"><summary>原始逐日数值 · ${num(dates.length)} 行 · 所有同图词</summary><div class="raw-data"><table class="mini-table"><thead><tr><th scope="col">日期</th>${names.map(name=>`<th scope="col">${esc(name)}</th>`).join('')}</tr></thead><tbody>${dates.map((date,i)=>`<tr><th scope="row">${esc(date)}</th>${names.map((_,j)=>`<td>${num(series[j]?.[i])}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`;
    const slider=el.querySelector('input[type=range]'),readout=el.querySelector('.t30-chart-readout'),crosshair=el.querySelector('[data-t30-crosshair]');
    const show=index=>{readout.innerHTML=`<strong>${esc(dates[index])}</strong>${names.map((name,i)=>`<span${i===target?' class="t30-selected-series"':''}>${esc(name)} <b>${num(series[i]?.[index])}</b></span>`).join('')}`;crosshair.setAttribute('x1',x(index));crosshair.setAttribute('x2',x(index));slider.setAttribute('aria-valuetext',`${dates[index]}，${term.keyword} ${num(series[target]?.[index])}`);};
    slider.addEventListener('input',()=>show(Number(slider.value)));
    el.querySelector('.t30-chart-svg').addEventListener('pointermove',event=>{const box=event.currentTarget.getBoundingClientRect(),px=(event.clientX-box.left)/box.width*W,index=Math.max(0,Math.min(dates.length-1,Math.round((px-L)/(W-L-R)*(dates.length-1))));slider.value=index;show(index);});
    show(dates.length-1);
  }
  window.bindTrends30=function bindTrends30(value){
    data=value;if(!data||!document.getElementById('trends30-rows'))return;
    document.getElementById('trends30-search').addEventListener('input',event=>{state.q=event.target.value;state.page=1;updateRows();});
    document.getElementById('trends30-status').addEventListener('change',event=>{state.status=event.target.value;state.page=1;updateRows();});
    document.getElementById('trends30-reset').addEventListener('click',()=>{Object.assign(state,{q:'',status:'all',page:1});document.getElementById('trends30-search').value='';document.getElementById('trends30-status').value='all';updateRows();});
    for(const [id,step] of [['trends30-prev',-1],['trends30-next',1]])document.getElementById(id).addEventListener('click',()=>{state.page+=step;updateRows();document.querySelector('.t30-table-meta').scrollIntoView({block:'start'});});
    updateRows();
  };
})();
