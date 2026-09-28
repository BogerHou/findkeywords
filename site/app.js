(() => {
  'use strict';
  const D = window.FINDKEYWORDS_DATA;
  const view = document.getElementById('view');
  if (!D) { view.innerHTML = '<p class="error-state">数据尚未加载，请刷新页面，或先运行数据构建脚本。</p>'; return; }
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const n = (value, digits = 0) => Number.isFinite(Number(value)) ? Number(value).toLocaleString('zh-CN', {maximumFractionDigits:digits}) : '—';
  const safeURL = value => { try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) ? esc(u.href) : '#'; } catch { return '#'; } };
  const ext = (url, label, cls = '') => `<a class="${cls}" href="${safeURL(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`;
  const K = new Map(D.keywords.map(k => [k.id, k]));
  const byWord = new Map(D.keywords.map(k => [k.keyword.toLowerCase(), k]));
  const C = new Map(D.captures.map(c => [c.id, c]));
  const B = new Map(D.domains.map(d => [d.domain, d]));
  const statusLabels = Object.fromEntries(['review','cooling','insufficient','pending'].map(status => [status,D.keywords.find(k => k.status === status)?.statusLabel || status]));
  const regLabels = {verified_recent:'近期注册',verified_old:'较早注册',unknown:'时间未核实'};
  const decisionLabels = {candidate:'保留线索',reject:'不保留',watch:'继续观察',uncertain:'待判断'};
  const colors = ['#166957','#557aa2','#ba7a39','#886496','#859d43'];
  const keywordState = {q:'',group:'all',status:'all',saved:false};
  const domainState = {q:'',registration:'all'};
  let starred = new Set();
  let storageOK = true;
  try { const stored = JSON.parse(localStorage.getItem('findkeywords.starred.v1') || '[]'); if (Array.isArray(stored)) starred = new Set(stored.filter(id => K.has(id))); } catch { storageOK = false; }
  let toastTimer;
  const toast = message => { const el = document.getElementById('toast'); el.textContent = message; el.classList.add('visible'); clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('visible'), 2600); };
  const tag = k => `<span class="tag tag-${esc(k.status)}">${esc(k.statusLabel)}</span>`;
  const star = k => `<button class="star-button${starred.has(k.id) ? ' saved' : ''}" data-star="${k.id}" aria-pressed="${starred.has(k.id)}" aria-label="${starred.has(k.id) ? '取消关注' : '关注'} ${esc(k.keyword)}">${starred.has(k.id) ? '★' : '☆'}</button>`;
  const detailLink = (k, label = k.keyword) => `<a class="keyword-link" href="#keyword/${k.id}">${esc(label)}</a>`;
  const range = k => k.estimateRange ? `${n(k.estimateRange.min)}–${n(k.estimateRange.max)}` : '未估算';
  const seriesFor = (k, c) => c?.series?.[c.terms.findIndex(t => t.toLowerCase() === k.keyword.toLowerCase())] || [];
  const primary = k => C.get(k.primaryCaptureId);
  const avg = a => a.length ? a.reduce((sum, v) => sum + v, 0) / a.length : 0;
  const periodLabel = c => c.period === 'Past 90 days' ? '过去 90 天' : '过去 12 个月';
  const linePoints = (values, w, h, padding = 2, max = 100) => values.map((v, i) => `${(padding + i / Math.max(1, values.length - 1) * (w - 2 * padding)).toFixed(2)},${(h - padding - v / max * (h - 2 * padding)).toFixed(2)}`).join(' ');
  function spark(k, annual = false, cls = 'row-spark') {
    const c = annual ? k.captureIds.map(id => C.get(id)).find(c => c.period === 'Past 12 months' && c.status === 'chart') || primary(k) : primary(k);
    const values = seriesFor(k, c);
    if (!values.length) return '<span class="subtle">整组数据不足</span>';
    return `<svg class="${cls}" viewBox="0 0 260 60" role="img" aria-label="${esc(k.keyword)}，${periodLabel(c)}，相对热度趋势"><line x1="2" y1="58" x2="258" y2="58" stroke="#e1e7e9"/><polyline points="${linePoints(values, 260, 60)}" fill="none" stroke="${k.status === 'cooling' ? '#a5783a' : '#166957'}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
  }
  function header(title, subtitle, action = '') { return `<div class="page-header"><div><div class="eyebrow">RESEARCH / ${esc(D.meta.runDate)}</div><h1>${title}</h1><p class="subtle">${subtitle}</p></div>${action}</div>`; }
  function overview() {
    const sprite = byWord.get('sprite sheet maker');
    const gif = byWord.get('gif to sprite sheet');
    view.innerHTML = header('把线索，变成有依据的判断。','这是一份可核查的研究快照。先看候选，再打开数据和来源。', '<a class="btn" href="#keywords">浏览关键词 <span>→</span></a>') +
    `<div class="metric-strip"><div class="metric-item"><span>原始域名名单</span><strong>${n(D.summary.rawDomains)}</strong><small>两批名单，非已访问网站数</small></div><div class="metric-item"><span>待研究关键词</span><strong>${D.summary.keywords}</strong><small>来自 ${D.summary.candidateDomains} 个来源域名</small></div><div class="metric-item"><span>已保存的趋势对比</span><strong>${D.summary.comparisons}</strong><small>美国 · 网页搜索</small></div><div class="metric-item"><span>条件性量级试算</span><strong>${D.summary.estimatedKeywords}</strong><small>有公开基准，仍需交叉验证</small></div></div>
    <div class="section-heading"><h2>本轮值得先看的线索</h2><a href="#methods">怎么看这些结果 →</a></div>
    <div class="overview-grid"><article class="panel feature-panel"><div class="feature-title"><span class="eyebrow">图像与游戏素材工具</span>${tag(sprite)}</div><h2>${detailLink(sprite)}</h2><p class="subtle">可以进一步检查搜索结果和具体工具需求，尚未完成竞争度验证。</p><div class="feature-number">${range(sprite)}<span>条件性月均量级</span></div>${spark(sprite,true,'feature-chart')}<div class="feature-bottom"><span>12 个月相对趋势 · 不同基准的试算范围</span><a href="#keyword/${sprite.id}" aria-label="查看 sprite sheet maker 详情">查看证据 →</a></div><div class="overview-note">相关方向：${detailLink(gif)}。可用数据较稀疏，本轮未估算搜索量。</div></article>
    <article class="panel feature-panel"><div class="feature-title"><span class="eyebrow">智能体治理相关词</span><span class="tag tag-cooling">走势回落</span></div><h2>有搜索信号，但近期在降温</h2><p class="subtle">最近 4 个完整周，相比此前 13 周的同图均值。</p>${D.calibration.agentRecentComparison.map(r => { const k=byWord.get(r.keyword.toLowerCase()); const drop=(1-r.recent_complete_4week_mean/r.preceding_13week_mean)*100; return `<div class="cooling-item">${detailLink(k)}${spark(k,true)}<span class="decline">↓ ${n(drop,1)}%</span></div>`; }).join('')}<div class="overview-note">比较区间：8 月 23 日–9 月 13 日的周标签，对照 5 月 24 日–8 月 16 日。年度量级不能代表当前月。</div></article></div>
    <div class="notice"><strong>目前还没有“已确认建站机会”。</strong> 趋势和量级提供研究线索；SEO 竞争度、搜索意图与可获得点击量仍待验证。</div>
    <div class="section-heading"><h2>这些关键词是怎么来的</h2><a href="#methods">查看完整筛选规则 →</a></div>
    <div class="flow"><div class="flow-step"><span>01 · 原始输入</span><strong>140,000</strong><p>域名名单，两批各 7 万</p></div><div class="flow-step"><span>02 · 名称规则初筛</span><strong>1,210</strong><p>43 个词根＋长度＋数字规则</p></div><div class="flow-step"><span>03 · AI 主观选样</span><strong>52</strong><p>逐个查注册时间和页面</p></div><div class="flow-step"><span>04 · 页面证据提词</span><strong>32</strong><p>关键词，来自 16 个来源域名</p></div></div>
    <p class="export-note">1,210 → 52 不是算法排名。没有完整的逐域名淘汰理由，未入选不代表没有价值。当前入口是 WhoisDS 名单，尚未接入 SSL 证书日志。</p>`;
  }
  function filteredKeywords() { const q=keywordState.q.toLowerCase().trim(); return D.keywords.filter(k => (!q || [k.keyword,k.domain,k.evidenceQuote].some(v=>v.toLowerCase().includes(q))) && (keywordState.group==='all'||k.groupId===keywordState.group) && (keywordState.status==='all'||k.status===keywordState.status) && (!keywordState.saved||starred.has(k.id))); }
  function keywords() {
    const groups = [...new Map(D.keywords.map(k=>[k.groupId,k.group])).entries()];
    view.innerHTML = header('关键词库','点开一个词，查看趋势、页面原文和量级依据。', '<button class="btn btn-secondary" id="export-keywords">导出当前列表 ↓</button>') +
    `<div class="toolbar"><div class="search-field"><span class="search-symbol">⌕</span><input type="search" class="search-input" id="keyword-search" value="${esc(keywordState.q)}" placeholder="搜索关键词、域名或网页原文" aria-label="搜索关键词、域名或网页原文"></div><label class="field"><span class="sr-only">关键词分组</span><select class="control" id="keyword-group"><option value="all">全部分组</option>${groups.map(([id,name])=>`<option value="${id}"${keywordState.group===id?' selected':''}>${esc(name)}</option>`).join('')}</select></label><button class="btn btn-secondary" id="only-saved" aria-pressed="${keywordState.saved}">${keywordState.saved?'★':'☆'} 只看关注</button></div>
    <div class="filter-tabs" aria-label="按研究状态筛选"><button class="filter-tab${keywordState.status==='all'?' active':''}" data-status="all" aria-pressed="${keywordState.status==='all'}">全部 <span>32</span></button>${Object.entries(statusLabels).map(([id,label])=>`<button class="filter-tab${keywordState.status===id?' active':''}" data-status="${id}" aria-pressed="${keywordState.status===id}">${label} <span>${D.keywords.filter(k=>k.status===id).length}</span></button>`).join('')}</div>
    <div class="table-meta"><span id="keyword-count" aria-live="polite"></span><span>曲线仅表示各自对比组内的相对热度</span></div><div class="table-wrap"><table class="keyword-table"><thead><tr><th><span class="sr-only">关注</span></th><th>关键词 / 分组</th><th>研究状态</th><th>90 天趋势</th><th>条件性月均量级</th><th>来源域名</th></tr></thead><tbody id="keyword-rows"></tbody></table></div><p class="export-note">状态是本轮分析判断；“待判断”不代表无数据。量级范围是基准情景差异，不是置信区间或网站流量预测。关注仅保存在当前浏览器。</p>`;
    updateKeywordRows();
    document.getElementById('keyword-search').addEventListener('input', e=>{keywordState.q=e.target.value;updateKeywordRows();});
    document.getElementById('keyword-group').addEventListener('change', e=>{keywordState.group=e.target.value;updateKeywordRows();});
    document.querySelectorAll('[data-status]').forEach(el=>el.addEventListener('click',()=>{keywordState.status=el.dataset.status;document.querySelectorAll('[data-status]').forEach(b=>{b.classList.toggle('active',b.dataset.status===keywordState.status);b.setAttribute('aria-pressed',b.dataset.status===keywordState.status);});updateKeywordRows();}));
    document.getElementById('only-saved').addEventListener('click',e=>{keywordState.saved=!keywordState.saved;e.currentTarget.setAttribute('aria-pressed',keywordState.saved);e.currentTarget.textContent=`${keywordState.saved?'★':'☆'} 只看关注`;updateKeywordRows();});
    document.getElementById('export-keywords').addEventListener('click',exportKeywords);
  }
  function updateKeywordRows() {
    const rows=filteredKeywords();document.getElementById('keyword-count').textContent=`显示 ${rows.length} / ${D.keywords.length} 个关键词`;
    document.getElementById('keyword-rows').innerHTML=rows.length?rows.map(k=>`<tr class="row-hover"><td>${star(k)}</td><td>${detailLink(k)}<span class="keyword-group">${esc(k.group)}</span></td><td>${tag(k)}</td><td>${spark(k)}</td><td><span class="row-estimate">${range(k)}</span>${k.estimateRange?'<small class="keyword-group">公开基准情景范围</small>':''}</td><td><a class="domain-small" href="#domains/${encodeURIComponent(k.domain)}">${esc(k.domain)}</a></td></tr>`).join(''):'<tr><td colspan="6"><div class="empty-state"><h2>没有匹配的关键词</h2><p>试试其他关键词，或清除分组与状态筛选。</p><button class="btn btn-secondary" id="clear-keyword-filters">清除筛选</button></div></td></tr>';
    document.getElementById('clear-keyword-filters')?.addEventListener('click',()=>{Object.assign(keywordState,{q:'',group:'all',status:'all',saved:false});keywords();});
  }
  function exportKeywords() {
    const rows=filteredKeywords(); if(!rows.length){toast('当前没有可导出的关键词');return;}
    if (location.protocol === 'http:' || location.protocol === 'https:') {
      const url = new URL('export.csv', location.href);
      url.searchParams.set('ids', rows.map(k => k.id).join(','));
      url.hash = '';
      const link = document.createElement('a');
      link.href = url.href;
      link.download = `findkeywords-${D.meta.runDate}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast(`已请求下载 ${rows.length} 个关键词`);
      return;
    }
    const fields=['关键词','来源域名','分组','研究状态','基准情景下限（非实测）','基准情景上限（非实测）','证据字段','页面原文','口径'];
    const csvcell = v => '"'+String(v??'').replace(/^[=+@\-\t\r]/,x=>"'"+x).replace(/"/g,'""')+'"';
    const csv=[fields,...rows.map(k=>[k.keyword,k.domain,k.group,k.statusLabel,k.estimateRange?.min??'',k.estimateRange?.max??'',k.sourceField,k.evidenceQuote,'美国／网页搜索；年度条件性月均量级；非当前月实测或网站流量'])].map(row=>row.map(csvcell).join(',')).join('\r\n');
    const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`findkeywords-${D.meta.runDate}-${rows.length}词.csv`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);toast(`已请求下载 ${rows.length} 个关键词`);
  }
  function keywordDetail(k) {
    if(!k){view.innerHTML=header('找不到这个关键词','请返回关键词库选择已保存的记录。','<a class="btn" href="#keywords">返回关键词库</a>');return;}
    const d=B.get(k.domain);
    view.innerHTML=`<a class="back-link" href="#keywords">← 返回关键词库</a><div class="detail-title"><div><h1>${esc(k.keyword)}</h1><div class="detail-meta">${tag(k)}<span>${esc(k.group)}</span><a href="#domains/${encodeURIComponent(k.domain)}">${esc(k.domain)}</a></div></div>${star(k)}</div><div class="notice">${esc(k.statusReason)}</div><div class="detail-grid"><div><section class="panel chart-panel"><div class="chart-heading"><div><h2>Google Trends 相对热度</h2><p class="subtle">美国 · 网页搜索 · 全部类别 · 搜索字词</p></div><label class="field"><span class="sr-only">选择已保存的趋势对比</span><select class="control" id="capture-select">${k.captureIds.map(id=>{const c=C.get(id);return `<option value="${id}"${id===k.primaryCaptureId?' selected':''}>${periodLabel(c)} · ${esc(c.id)}</option>`;}).join('')}</select></label></div><div id="trend-content"></div></section><section class="panel detail-section"><div class="section-heading"><h2>关键词来自哪里</h2><a href="#domains/${encodeURIComponent(k.domain)}">完整域名记录 →</a></div><span class="eyebrow">网页 ${esc(k.sourceField)} 原文</span><blockquote class="source-quote">${esc(k.evidenceQuote)}</blockquote><dl class="evidence-list"><dt>来源域名</dt><dd>${esc(k.domain)}</dd><dt>最终页面</dt><dd>${d?.finalUrl?ext(d.finalUrl,d.finalUrl):'未取得'}</dd><dt>注册时间</dt><dd>${d?.registrationDate?esc(d.registrationDate.slice(0,10)):'未核实'} · ${esc(regLabels[d?.registrationStatus]||'未知')}</dd><dt>网页判断</dt><dd>${esc(k.sourceSummary)}</dd></dl></section></div><aside class="detail-side"><section class="panel"><span class="eyebrow">探索量级</span><h2>条件性月均估算</h2>${k.estimateRange?`<div class="estimate-big">${range(k)}</div><p class="subtle">过去 12 个月数据 × 公开基准月均量级</p><div class="notice">这是不同基准的情景范围，不是置信区间，也不是当前月搜索量。</div><a class="btn btn-secondary" href="#methods">打开估算演算器 →</a>`:'<p class="source-text">这个词本轮没有可靠的绝对量级估算。请先结合完整序列和数据口径判断，再选择适合的公开基准。</p><a href="#methods">查看估算方法 →</a>'}</section><section class="panel"><h2>核查时注意</h2><p class="source-text">热度指数在同一张对比图内归一化。跨图的 20 和 40 不能直接比较搜索规模。</p><p class="source-text">零值或“数据不足”不等于零搜索。单独尖峰也不足以证明持续需求。</p><a href="../reports/trends-audit-2026-09-26.md" target="_blank" rel="noopener">查看趋势争议复核记录 ↗</a></section></aside></div>${estimateEvidence(k)}`;
    const select=document.getElementById('capture-select');select.addEventListener('change',()=>renderTrend(k,C.get(select.value)));renderTrend(k,C.get(select.value));
  }
  function estimateEvidence(k) {
    if(!k.estimates.length)return '';
    return `<section class="panel detail-section"><div class="section-heading"><h2>每一个估算值的依据</h2><a href="#methods">公式与校准局限 →</a></div><p class="subtle">公开基准月均估算 × 目标词同图均值 ÷ 基准词同图均值。下表使用保存的 53 周完整序列，显示值保留小数，计算使用原精度。</p><div class="table-wrap"><table class="mini-table"><thead><tr><th>公开基准</th><th>基准月均估算</th><th>报告月份</th><th>目标 / 基准均值</th><th>条件性月均结果</th><th>核查</th></tr></thead><tbody>${k.estimates.map(r=>`<tr><td>${esc(r.anchor_keyword)}</td><td>${n(r.anchor_volume)}</td><td>${esc(r.anchor_report_month)}</td><td>${n(r.target_mean,4)} / ${n(r.anchor_mean,4)}</td><td>${n(r.conditional_monthly_estimate,2)}</td><td>${ext(r.anchor_source_url,'基准来源')} · ${ext(r.query_url,'同图对比')}</td></tr>`).join('')}</tbody></table></div><p class="export-note">基准来源为供应商模型估算；时间窗口和搜索变体口径未完全对齐。同供应商两个基准互相还原也出现约 75% 偏差，结果只适合探索量级。</p></section>`;
  }
  function renderTrend(k,c) {
    const el=document.getElementById('trend-content');if(!c){el.innerHTML='<div class="empty-state">没有已保存的趋势记录。</div>';return;}
    const index=c.terms.findIndex(t=>t.toLowerCase()===k.keyword.toLowerCase());const values=c.series[index]||[];
    const captured=new Date(c.captured_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
    const notes=`<div class="chart-capture-meta"><span>记录：${esc(c.id)} · ${esc(captured)}（北京时间）</span>${ext(c.url,'在 Google Trends 查看')}</div><p class="chart-context">比较词：${c.terms.map(esc).join(' · ')}<br>本图来自保存的页面表格，不是官方 CSV。链接为相对日期，重新打开时可能变化；本页保留采集时的数列。</p>`;
    if(!values.length){el.innerHTML=`<div class="empty-state"><h2>这组对比数据不足</h2><p>Google Trends 当时没有提供可用曲线，不能据此认定没有搜索需求。</p></div>${notes}`;return;}
    const daily=c.period==='Past 90 days';const used=daily?values.slice(0,-1):values;
    el.innerHTML=`<div class="chart-tools"><label class="checkbox-label"><input type="checkbox" id="show-comparison">显示同组其他词</label><span class="subtle">指数 0–100 · ${daily?'日':'周'}数据</span></div><div class="chart-canvas" id="chart-canvas"></div><div class="chart-readout" id="chart-readout" aria-live="polite"></div><input class="date-slider" id="date-slider" type="range" min="0" max="${values.length-1}" value="${values.length-1}" aria-label="查看趋势日期"><div class="small-metrics"><div><span>${daily?'完整日':'全序列周'}均值</span><strong>${n(avg(used),2)}</strong></div><div><span>非零${daily?'天':'周'}数</span><strong>${used.filter(v=>v>0).length} / ${used.length}</strong></div><div><span>最高指数</span><strong>${Math.max(...used)}</strong></div><div><span>统计口径</span><strong>${daily?'去掉最后日':'包含首尾周'}</strong></div></div>${notes}<details class="data-disclosure"><summary>展开原始逐${daily?'日':'周'}数值 · ${c.dates.length} 行</summary><div class="raw-data"><table class="mini-table"><thead><tr><th>日期标签</th>${c.terms.map(t=>`<th>${esc(t)}</th>`).join('')}</tr></thead><tbody>${c.dates.map((date,i)=>`<tr><td>${esc(date)}</td>${c.series.map(s=>`<td>${s[i]}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`;
    let showAll=false;let selected=values.length-1;
    const W=840,H=265,left=43,right=17,top=17,bottom=38;
    const x=i=>left+i/Math.max(1,values.length-1)*(W-left-right);const y=v=>H-bottom-v/100*(H-top-bottom);
    const draw=()=>{
      const indices=showAll?c.terms.map((_,i)=>i):[index];
      document.getElementById('chart-canvas').innerHTML=`<svg id="trend-svg" class="chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(k.keyword)} ${periodLabel(c)}趋势图"><title>${esc(k.keyword)}：${periodLabel(c)}的真实相对热度数列</title>${[0,25,50,75,100].map(v=>`<line class="gridline" x1="${left}" y1="${y(v)}" x2="${W-right}" y2="${y(v)}"/><text x="${left-12}" y="${y(v)+4}" text-anchor="end">${v}</text>`).join('')}${[0,Math.floor((values.length-1)/2),values.length-1].map((i,j)=>`<text x="${x(i)}" y="${H-9}" text-anchor="${j===0?'start':j===2?'end':'middle'}">${esc(c.dates[i])}</text>`).join('')}${indices.filter(i=>i!==index).concat([index]).map(i=>`<polyline fill="none" stroke="${colors[i%colors.length]}" stroke-opacity="${i===index?1:.7}" stroke-width="${i===index?2.5:1.5}" points="${c.series[i].map((v,j)=>`${x(j).toFixed(2)},${y(v).toFixed(2)}`).join(' ')}" vector-effect="non-scaling-stroke"/>`).join('')}<line id="chart-crosshair" class="crosshair" x1="${x(selected)}" x2="${x(selected)}" y1="${top}" y2="${H-bottom}"/><circle id="chart-dot" cx="${x(selected)}" cy="${y(values[selected])}" r="4" fill="${colors[index%colors.length]}" stroke="#fff" stroke-width="2"/></svg>`;
      document.getElementById('trend-svg').addEventListener('pointermove',e=>{const box=e.currentTarget.getBoundingClientRect(); const pointerX=(e.clientX-box.left)/box.width*W;selected=Math.max(0,Math.min(values.length-1,Math.round((pointerX-left)/(W-left-right)*(values.length-1))));document.getElementById('date-slider').value=selected;readout();});readout();
    };
    const readout=()=>{
      const indices=showAll?c.terms.map((_,i)=>i):[index];
      document.getElementById('chart-readout').innerHTML=`<strong>${esc(c.dates[selected])}</strong>${indices.map(i=>`<span class="legend-item"><svg width="16" height="10" aria-hidden="true"><line x1="0" x2="16" y1="5" y2="5" stroke="${colors[i%colors.length]}" stroke-width="3"/></svg>${esc(c.terms[i])} <b>${c.series[i][selected]}</b></span>`).join('')}`;
      const line=document.getElementById('chart-crosshair');line.setAttribute('x1',x(selected));line.setAttribute('x2',x(selected));document.getElementById('chart-dot').setAttribute('cx',x(selected));document.getElementById('chart-dot').setAttribute('cy',y(values[selected]));document.getElementById('date-slider').setAttribute('aria-valuetext',`${c.dates[selected]}，${k.keyword} 指数 ${values[selected]}`);
    };
    document.getElementById('show-comparison').addEventListener('change',e=>{showAll=e.target.checked;draw();});document.getElementById('date-slider').addEventListener('input',e=>{selected=Number(e.target.value);readout();});draw();
  }
  function domains(prefill) {
    if(prefill){domainState.q=prefill;domainState.registration='all';}
    view.innerHTML=header('域名样本','52 个实际查验的域名。查看为什么选中、注册日期、页面标签和提取出的词。')+`<div class="toolbar"><div class="search-field"><span class="search-symbol">⌕</span><input class="search-input" type="search" id="domain-search" value="${esc(domainState.q)}" placeholder="搜索域名、页面标题或关键词" aria-label="搜索域名、页面标题或关键词"></div><label class="field"><span class="sr-only">注册时间筛选</span><select class="control" id="domain-registration"><option value="all">全部注册状态</option>${Object.entries(regLabels).map(([id,label])=>`<option value="${id}"${domainState.registration===id?' selected':''}>${label}</option>`).join('')}</select></label></div><div class="table-meta"><span id="domain-count" aria-live="polite"></span><span>近期注册 42 · 较早注册 1 · 未核实 9</span></div><div class="table-wrap"><table class="domain-table"><thead><tr><th>域名 / 页面判断</th><th>注册日期</th><th>选中原因</th><th>提取关键词</th></tr></thead><tbody id="domain-rows"></tbody></table></div><p class="export-note">注册日期核验针对来源域名。跳转到其他站点时，不能据此推断目标站也刚成立；证书签发也不等于域名注册或网站上线。</p>`;
    document.getElementById('domain-search').addEventListener('input',e=>{domainState.q=e.target.value;updateDomainRows();});document.getElementById('domain-registration').addEventListener('change',e=>{domainState.registration=e.target.value;updateDomainRows();});updateDomainRows();
  }
  function updateDomainRows() {
    const q=domainState.q.trim().toLowerCase();const rows=D.domains.filter(d=>(!q||[d.domain,d.title,...d.keywords].some(v=>(v||'').toLowerCase().includes(q)))&&(domainState.registration==='all'||d.registrationStatus===domainState.registration));
    document.getElementById('domain-count').textContent=`显示 ${rows.length} / ${D.domains.length} 个域名`;
    document.getElementById('domain-rows').innerHTML=rows.length?rows.map(d=>`<tr><td><strong class="domain-name">${esc(d.domain)}</strong><p class="domain-info">${esc(d.summary||d.title||'没有足够的页面内容作判断')}</p><details><summary>查看页面与核验记录</summary><dl class="evidence-list"><dt>页面状态</dt><dd>${esc(d.fetchStatus)}</dd><dt>最终地址</dt><dd>${d.finalUrl?ext(d.finalUrl,d.finalUrl):'未取得'}</dd><dt>Title</dt><dd>${esc(d.title||'未取得')}</dd><dt>Description</dt><dd>${esc(d.description||'未取得')}</dd><dt>H1</dt><dd>${esc(Array.isArray(d.h1)?d.h1.join(' / '):d.h1||'未取得')}</dd><dt>核验来源</dt><dd>${d.registrationSource?ext(d.registrationSource,'注册信息来源'):'未取得'}</dd><dt>页面处理</dt><dd>${esc(decisionLabels[d.decision]||d.decision||'待判断')}</dd></dl></details></td><td><strong>${d.registrationDate?esc(d.registrationDate.slice(0,10)):'—'}</strong><span class="keyword-group">${esc(regLabels[d.registrationStatus]||d.registrationStatus)}</span></td><td><span class="tag">${d.selectionGroup==='readable_task'?'任务名称':'概念线索'}</span><p class="domain-info">${esc(d.selectionReason)}</p><small class="subtle">命中词根：${esc(d.nameMatches.join('、'))} · 名单 ${esc(d.sourceDate)}</small></td><td><div class="domain-keywords">${d.keywords.length?d.keywords.map(word=>{const k=byWord.get(word.toLowerCase());return k&&k.domain===d.domain?detailLink(k):`<span>${esc(word)}</span>`;}).join(''):'<span class="subtle">未保留关键词</span>'}</div></td></tr>`).join(''):'<tr><td colspan="4"><div class="empty-state"><h2>没有匹配的域名</h2><button class="btn btn-secondary" id="clear-domain-filters">清除筛选</button></div></td></tr>';
    document.getElementById('clear-domain-filters')?.addEventListener('click',()=>{Object.assign(domainState,{q:'',registration:'all'});domains();});
  }
  function resources() {
    const types={report:'研究报告',audit:'复核记录',data:'数据文件',raw:'原始记录',evidence:'原始证据',method:'方法文档'};
    view.innerHTML=header('数据与报告','保留方法、来源与数列。页面上的数字都可以回到这些文件核查。')+`<div class="notice"><strong>研究快照 · ${esc(D.meta.runDate)}</strong> 当前网站使用已保存数据，不会自动访问 Google Trends 或更新搜索量。基准来自公开页面；未核查 SEO 竞争度。</div><div class="resource-grid">${[...(window.FINDKEYWORDS_TRENDS30?.resources||[]),...(window.FINDKEYWORDS_TLD?.resources||[]),...(window.FINDKEYWORDS_MONTH?.resources||[]),...D.resources].filter(r=>/^(\.\.\/)?(reports|data|scripts)\//.test(r.path)||['data.json','trends30-data.json'].includes(r.path)).map(r=>`<a class="panel resource-card" href="${esc(r.path)}" target="_blank" rel="noopener"><span class="resource-type">${esc(types[r.type]||r.type)}</span><h2>${esc(r.title)} <span>↗</span></h2><p>${esc(r.description)}</p><span class="source-meta">${esc(r.path.replace(/^\.\.\//,''))}</span></a>`).join('')}</div><section class="panel detail-section"><h2>记录口径</h2><p class="source-text">${esc(D.meta.captureMethod)}</p><p class="source-text">公开基准分别出自 Semrush 2026 年 7 月 / 8 月页面，属于供应商的月均模型估算。Google Trends 采样、整数取整、日期窗口与搜索变体都会影响换算。</p><a href="data.json" target="_blank" rel="noopener">查看网站完整数据包 JSON ↗</a></section>`;
  }
  const pageNames={roots:'词根筛选',trends30:'历史近30天趋势',tld:'后缀与名称筛选',month:'近30天域名扩量',overview:'研究概览',keywords:'关键词库',keyword:'关键词详情',domains:'域名样本',methods:'分析方法',sources:'数据与报告'};
  function route() {
    const hash=location.hash.slice(1)||(window.FINDKEYWORDS_ROOTS?'roots':window.FINDKEYWORDS_MONTH?'month':'overview');const [page,rawId]=hash.split('/');if(page==='view'){document.getElementById('view').focus();return;}
    let id='';try{id=rawId?decodeURIComponent(rawId):'';}catch{location.hash='overview';return;}
    const navPage=page==='keyword'?'keywords':page;
    document.querySelectorAll('[data-nav]').forEach(el=>{el.classList.toggle('active',el.dataset.nav===navPage);if(el.dataset.nav===navPage)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
    document.getElementById('page-name').textContent=pageNames[page]||'研究概览';document.querySelector('.market').textContent=page==='roots'?'51 词根 · 趋势待核验':['month','tld'].includes(page)?'全球域名 · 近30天名单':'美国 · 网页搜索';document.getElementById('quick-search').innerHTML=page==='roots'?'搜索命中结果 <kbd>/</kbd>':['month','tld'].includes(page)?'搜索本轮域名 <kbd>/</kbd>':'搜索关键词 <kbd>/</kbd>';
    document.title=`${page==='keyword'&&K.has(id)?K.get(id).keyword:pageNames[page]||'研究概览'} · FindKeywords`;
    if(page==='roots'){view.innerHTML=window.renderRoots(window.FINDKEYWORDS_ROOTS);window.bindRoots();}else if(page==='trends30'){view.innerHTML=window.renderTrends30(window.FINDKEYWORDS_TRENDS30,id);window.bindTrends30(window.FINDKEYWORDS_TRENDS30);}else if(page==='tld'){view.innerHTML=window.renderTld(window.FINDKEYWORDS_TLD);if(window.FINDKEYWORDS_TLD)window.bindMonth(window.FINDKEYWORDS_TLD,{variant:'tld'});}else if(page==='month'&&window.FINDKEYWORDS_MONTH){view.innerHTML=window.renderMonth(window.FINDKEYWORDS_MONTH);window.bindMonth(window.FINDKEYWORDS_MONTH);}else if(page==='keywords')keywords();else if(page==='keyword')keywordDetail(K.get(id));else if(page==='domains')domains(id);else if(page==='methods'){view.innerHTML='<div class="notice">本页保留前两轮试跑方法（52 个域名样本）。本轮 3,000 个样本的四通道抽样与页面规则，可在 <a href="#month">近30天扩量</a> 中展开查看；新增的 <a href="#tld">后缀与名称方法</a> 单独记录。</div>'+window.renderMethods(D);window.bindMethods(D);}else if(page==='sources')resources();else overview();
    window.scrollTo(0,0);
  }
  document.addEventListener('click',e=>{
    const button=e.target.closest('[data-star]');if(!button)return;const id=button.dataset.star;const k=K.get(id);if(!k)return;starred.has(id)?starred.delete(id):starred.add(id);
    try{localStorage.setItem('findkeywords.starred.v1',JSON.stringify([...starred]));storageOK=true;}catch{storageOK=false;}
    const saved=starred.has(id);button.classList.toggle('saved',saved);button.textContent=saved?'★':'☆';button.setAttribute('aria-pressed',saved);button.setAttribute('aria-label',`${saved?'取消关注':'关注'} ${k.keyword}`);
    toast(storageOK?(saved?'已关注，保存在当前浏览器':'已取消关注'):'当前浏览器无法保存，关注仅在本次页面有效');if(keywordState.saved&&document.getElementById('keyword-rows'))updateKeywordRows();
  });
  function focusSearch(){if(document.getElementById('roots-search')){document.getElementById('roots-search').focus();return;}if(document.getElementById('trends30-search')){document.getElementById('trends30-search').focus();return;}if(document.getElementById('month-search')){document.getElementById('month-search').focus();return;}if(location.hash!=='#keywords'){location.hash='keywords';setTimeout(()=>document.getElementById('keyword-search')?.focus(),0);}else document.getElementById('keyword-search')?.focus();}
  document.getElementById('quick-search').addEventListener('click',focusSearch);
  document.addEventListener('keydown',e=>{if(e.key==='/'&&!e.metaKey&&!e.ctrlKey&&!e.altKey&&!['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)&&!e.target.isContentEditable){e.preventDefault();focusSearch();}});
  document.getElementById('sidebar-date').textContent=(window.FINDKEYWORDS_ROOTS?.meta.runDate||D.meta.runDate).replaceAll('-','.');document.getElementById('footer-date').textContent=`规则更新 ${window.FINDKEYWORDS_ROOTS?.meta.runDate||D.meta.runDate} · 数据日期见各页`;
  if(document.getElementById('nav-month')&&window.FINDKEYWORDS_MONTH)document.getElementById('nav-month').textContent=n(window.FINDKEYWORDS_MONTH.summary.probed);if(window.FINDKEYWORDS_TLD)document.getElementById('nav-tld').textContent=n(window.FINDKEYWORDS_TLD.summary.probed);document.getElementById('nav-keywords').textContent=D.keywords.length;document.getElementById('nav-domains').textContent=D.domains.length;
  if(window.FINDKEYWORDS_TRENDS30)document.getElementById('nav-trends30').textContent=n(window.FINDKEYWORDS_TRENDS30.summary.queried)+' 已查';
  window.addEventListener('hashchange',route);route();
})();
