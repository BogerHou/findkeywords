(() => {
  'use strict';
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n = x => Number(x || 0).toLocaleString('zh-CN');
  const statusNames = {screening:'正在筛选域名',domains_complete:'域名技术筛选完成',paused:'已暂停，需要检查原因',interrupted:'已中断',pausing:'正在保存并暂停',waiting_for_domain_screening:'等待域名全部筛选完毕',querying_trends:'正在查询 Google Trends',needs_final_review:'趋势自动筛选完成，等待最终复核',complete:'本轮已完成'};
  const reasons = {html_with_content:'取得页面内容',javascript_or_thin:'依赖脚本或文本过少',thin_or_empty:'页面空白或文本过少',dns_error:'DNS 未解析成功',timeout:'请求超时',tls_handshake_error:'TLS 握手失败',tls_certificate_error:'证书验证失败',external_or_unsupported_redirect:'跳转到其他域名或不支持的地址',robots_disallowed:'robots.txt 禁止抓取',homepage_too_large:'首页达到文本大小上限',robots_returned_html:'robots.txt 返回 HTML',http_blocked:'站点拒绝访问',historical_http_blocked:'复用旧访问限制记录',connect_error:'连接失败',robots_too_large:'robots.txt 超过大小上限',robots_http_error:'robots.txt HTTP 错误',robots_complex_rules:'robots.txt 含尚未支持的复杂规则',homepage_missing:'首页不存在',parking_page:'域名售卖或停放页',placeholder_page:'尚未上线的占位页',template_placeholder:'模板占位内容',reviewed_placeholder_or_parking:'旧记录已复核为售卖或占位页',https_downgrade:'跳转至非 HTTPS 地址',rate_limited:'站点限流，已停止该站请求',non_html:'非 HTML 页面',challenge:'验证或拦截页面',missing_keyword_evidence:'缺少页面标签证据',target_error:'解析目标不符合公网地址规则',homepage_http_error:'首页 HTTP 错误',transport_error:'传输异常',robots_slower_schedule_required:'站点要求更长抓取间隔',soft_404:'页面内容显示不存在',redirect_limit_or_missing_location:'跳转次数超限或缺少目标',redirect_loop:'循环跳转',missing_content_type:'未提供内容类型',parse_or_url_error:'页面或地址解析错误',local_ca_error:'服务器本地证书环境异常'};
  let rows = [], kind = 'domains';
  async function json(path) { const r = await fetch(path, {cache:'no-store'}); if(!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }
  async function refresh() {
    try {
      const d = await json('full-run-status.json');
      const t = await json('full-trends-status.json').catch(() => null);
      const age = (Date.now() - Date.parse(d.updated_at))/1000;
      const stale = d.status === 'screening' && age > 90;
      document.getElementById('live-state').textContent = `${statusNames[d.status] || d.status} · 最近更新 ${new Date(d.updated_at).toLocaleString('zh-CN')}${stale?' · 记录已超过90秒未更新，请检查连接或服务器状态。':' · 每30秒读取一次已保存进度。'}`;
      document.getElementById('run-stats').innerHTML = [[d.covered,'已有判定记录',`总计 ${n(d.universe)} 个`],[d.pending,'等待探测',`本轮新完成 ${n(d.newly_completed)} 个`],[d.decisions.pass,'有页面内容','尚待关键词与趋势验证'],[t?.automatic_matches ?? '—','趋势规则候选','尚未经最终复核']].map(([value,label,note])=>`<div class="run-stat"><span>${esc(label)}</span><strong>${typeof value==='number'?n(value):esc(value)}</strong><small>${esc(note)}</small></div>`).join('');
      const pct = (d.covered/d.universe*100).toFixed(1);
      document.getElementById('run-stage').innerHTML = `<p><strong>1. 域名筛选 ${pct}%</strong> · 复用 ${n(d.reused)} 条，本轮已完成 ${n(d.newly_completed)} 条。</p><progress class="run-progress" value="${d.covered}" max="${d.universe}">${pct}%</progress><p>2. 趋势统计：${esc(t?statusNames[t.status]||t.status:'等待任务状态')}${t?.candidates!=null?`；已查 ${n(t.queried)} / ${n(t.candidates)} 个候选词`:''}。</p>${t?.current_keyword?`<p>当前查询：<strong>${esc(t.current_keyword)}</strong></p>`:''}${t?.window?`<p>固定日期：${esc(t.window.start)} 至 ${esc(t.window.end)} · 美国 / 网页搜索</p>`:''}${t?.error?`<p class="run-error">${esc(t.error)}</p>`:''}${d.stop_reason?`<p class="run-error">${esc(d.stop_reason)}</p>`:''}<p class="run-mini">本轮已保存的解压文本约 ${(d.saved_decoded_bytes/1048576).toFixed(2)} MiB；这是正文体积，不是完整网络流量。已知 HTTP 尝试 ${n(d.known_http_attempts)} 次，另有 ${n(d.requests_with_unknown_count)} 条请求数不确定的记录。</p>`;
      document.getElementById('run-reasons').innerHTML = `<div class="run-reason-list">${Object.entries(d.reasons).sort((a,b)=>b[1]-a[1]).map(([key,value])=>`<div class="run-reason"><span>${esc(reasons[key]||key)}</span><strong>${n(value)}</strong></div>`).join('')}</div>`;
      document.getElementById('run-results').innerHTML = d.pending ? '<p>域名仍在检查，当前没有最终关键词名单。后续阶段会在全部域名取得判定记录后开始。</p>' : `<p>全部域名已有判定记录，其中“证据不足”仍不是通过。<a href="full-domain-results.json" target="_blank" rel="noopener">下载逐域名证据</a> · <a href="full-keyword-candidates.json" target="_blank" rel="noopener">下载关键词候选及页面原文</a></p>${t?.queried?'<p><a href="full-trends-results.json" target="_blank" rel="noopener">查看已查询的趋势数列与判定</a></p>':''}<p>${t?.status==='needs_final_review'?'自动规则筛出的词还需复核语义、网页质量和完整趋势证据。':'趋势阶段尚未完成。'}</p>`;
    } catch(e) {
      document.getElementById('live-state').textContent = `暂时读不到本轮进度（${e.message}）。这不代表任务已停止；请检查服务器连接或 SSH 隧道。`;
      if(location.hostname==='127.0.0.1' && location.port==='8878') {
        const link = document.createElement('a'); link.href='http://127.0.0.1:8879/site/full-run.html'; link.textContent=' 打开 AWS 实时进度页 →';
        document.getElementById('live-state').append(link);
      }
    }
  }
  function renderRows() {
    const query = document.getElementById('detail-search').value.trim().toLowerCase();
    const selected = rows.filter(r => !query || JSON.stringify(r).toLowerCase().includes(query));
    document.getElementById('details-output').innerHTML = `<p>匹配 ${n(selected.length)} / ${n(rows.length)} 条，当前显示前 100 条；输入名称可精确查找。</p>${selected.slice(0,100).map(r=>`<details><summary><strong>${esc(kind==='domains'?r.domain:r.keyword)}</strong> · ${esc(kind==='domains'?(reasons[r.reason]||r.reason):(r.assessment?.status||'待查'))}</summary><pre>${esc(JSON.stringify(r,null,2))}</pre></details>`).join('')}`;
  }
  async function load(kindName,path) {
    try { rows = await json(path); kind = kindName; renderRows(); }
    catch(e) { document.getElementById('details-output').textContent = `结果文件尚未生成或暂时无法读取（${e.message}）。`; }
  }
  document.getElementById('load-details').onclick = ()=>load('domains','full-domain-results.json');
  document.getElementById('load-trends').onclick = ()=>load('trends','full-trends-results.json');
  document.getElementById('detail-search').oninput = renderRows;
  refresh(); setInterval(refresh,30000);
})();
