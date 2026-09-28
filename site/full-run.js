(() => {
  'use strict';
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n = x => Number(x || 0).toLocaleString('zh-CN');
  const statusNames = {screening:'正在筛选域名',domains_complete:'域名技术筛选完成',paused:'已暂停，需要检查原因',interrupted:'已中断',pausing:'正在保存并暂停',waiting_for_domain_screening:'等待域名全部筛选完毕',querying_trends:'正在查询 Google Trends',needs_final_review:'趋势自动筛选完成，等待最终复核',complete:'本轮已完成'};
  const reasons = {html_with_content:'取得页面内容',javascript_or_thin:'依赖脚本或文本过少',thin_or_empty:'页面空白或文本过少',dns_error:'DNS 未解析成功',timeout:'请求超时',tls_handshake_error:'TLS 握手失败',tls_certificate_error:'证书验证失败',external_or_unsupported_redirect:'跳转到其他域名或不支持的地址',robots_disallowed:'robots.txt 禁止抓取',homepage_too_large:'首页达到文本大小上限',robots_returned_html:'robots.txt 返回 HTML',http_blocked:'站点拒绝访问',historical_http_blocked:'复用旧访问限制记录',connect_error:'连接失败',robots_too_large:'robots.txt 超过大小上限',robots_http_error:'robots.txt HTTP 错误',robots_complex_rules:'robots.txt 含尚未支持的复杂规则',homepage_missing:'首页不存在',parking_page:'域名售卖或停放页',placeholder_page:'尚未上线的占位页',template_placeholder:'模板占位内容',reviewed_placeholder_or_parking:'旧记录已复核为售卖或占位页',https_downgrade:'跳转至非 HTTPS 地址',rate_limited:'站点限流，已停止该站请求',non_html:'非 HTML 页面',challenge:'验证或拦截页面',missing_keyword_evidence:'缺少页面标签证据',target_error:'解析目标不符合公网地址规则',homepage_http_error:'首页 HTTP 错误',transport_error:'传输异常',robots_slower_schedule_required:'站点要求更长抓取间隔',soft_404:'页面内容显示不存在',redirect_limit_or_missing_location:'跳转次数超限或缺少目标',redirect_loop:'循环跳转',missing_content_type:'未提供内容类型',parse_or_url_error:'页面或地址解析错误',local_ca_error:'服务器本地证书环境异常'};
  const reviewLabels = {ready_for_semantic_review:'完整字段支持（自动初筛）',phrase_review:'营销用语或短语需复核',metadata_only:'仅有薄页或截断标签',no_usable_source:'来源已纠正为不可用',supplement_needs_trends:'原文核对补充，趋势未查'};
  const semanticTermLabels = {meaning_checked:'用途含义已核对，趋势未查',needs_qualifier:'已复核，查询含义需澄清',entity_query:'已复核，实体或品牌词单列'};
  const semanticDomainLabels = {supplemented:'已补充字面用途词',insufficient_fields:'字段不足',entity_or_personal:'实体、机构或个人页面',conflicting_fields:'字段或来源信息矛盾',site_shell:'登录、导航或通用外壳',needs_query_formulation:'用途线索仍需形成明确查询'};
  let rows = [], kind = 'domains', hasLocalTrends = false;
  const trendLabels = {growth_rule_not_met:'未达到30天增长门槛',below_reporting_threshold:'指数均低于展示阈值',below_reporting_threshold_no_chart:'页面明确提示数据不足',rapid_growth:'30天增长达标，需检查背景与复测',zero_baseline_emerging:'零基期起量，需检查背景与复测',incomplete_or_non_daily:'日数据不完整，需复核'};
  const rowLabel = r => kind==='domains' ? reasons[r.reason]||r.reason : kind==='semantic' ? semanticDomainLabels[r.status]||r.status : kind==='trends' ? trendLabels[r.assessment?.status]||r.assessment?.status||'待查' : semanticTermLabels[r.semantic_review?.status]||reviewLabels[r.review_status]||'待查';
  async function json(path) { const r = await fetch(path, {cache:'no-store'}); if(!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }
  async function refresh() {
    try {
      const d = await json('full-run-status.json');
      const t = await json('full-trends-status.json').catch(() => null);
      const c = await json('full-curation-summary.json').catch(() => null);
      const local = await json('local-trends-status.json').catch(() => null);
      hasLocalTrends = Boolean(local);
      document.getElementById('run-local-trends').innerHTML = local ? `<p><strong>已查询 ${n(local.queried)} / ${n(local.candidates)} 条候选；完成所需筛选步骤 ${n(local.completed)} 条。</strong>剩余 ${n(local.pending)} 条，包含尚未查询或还需半年背景、复测的项目。</p><p>本地浏览器单词查询，固定 ${esc(local.window.start)} 至 ${esc(local.window.end)}，美国 / 网页搜索。共保存 ${n(local.chart_series)} 份数列；自动规则候选 ${n(local.automatic_matches)} 个，尚未作最终机会确认。</p><p>范围为全部保留的 2,917 条字面候选，先处理已核对含义的 180 条。原来的薄页、营销词及歧义标记保留；另 1 条不可用来源排除。每个词单独查询，避免比较组缩放掩盖弱信号。</p><p>正常批次不发送进度通知。浏览器遇到限流或验证时停止并保存原因，失败不会算作零指数。AWS 抓取与旧趋势服务保持停止。</p><p><a href="local-trends-status.json" target="_blank" rel="noopener">本地查询进度</a> · <a href="local-trends-results.json" target="_blank" rel="noopener">逐词数列、原始证据路径和判定</a> · <a href="../reports/local-trends-2026-09-28.md" target="_blank" rel="noopener">本地查询报告</a></p>` : '尚无本地查询记录。';
      const audit = await json('full-access-audit.json').catch(() => null);
      const a = audit?.aws_new;
      document.getElementById('run-access-audit').innerHTML = a ? `<p>以下仅统计本轮 AWS 新探测的 ${n(a.domains)} 个域名，另 ${n(audit.historical_reused.domains)} 条旧记录不混入 AWS 出口判断。分类按每个域名计一次，包含保存页面的验证标题纠正。</p><p><strong>${n(a.access_restriction_domains)} 个（${esc(a.access_restriction_percent)}%）有拒绝、认证、验证或限流迹象。</strong>这不是“因机房 IP 被封”的确诊数量；DNS、TLS、超时也不能直接判为封禁。</p><div class="run-reason-list">${a.groups.map(g=>`<div class="run-reason"><span>${esc(g.label)}</span><strong>${n(g.count)} · ${esc(g.percent)}%</strong></div>`).join('')}</div><p>有 ${n(a.no_homepage_request_recorded)} 个域名在首页请求发出前停止，涉及前置网络失败、robots 获取/规则、跳转等情况。${n(a.effective_reasons.robots_complex_rules)} 个因采集器暂不支持 robots 通配符规则而暂缓；${n(a.effective_reasons.robots_slower_schedule_required)} 个要求更慢频率。页面薄/脚本依赖和大小截断也会减少提词覆盖。</p><p class="run-mini">原采集器未保留 HTTP 错误响应的正文和全部响应头，无法把每个403归因于某个防护服务或IP策略。统计只读现有记录，无新增候选站或Google请求。</p><p><a href="full-access-audit.json" target="_blank" rel="noopener">范围、原因、比例与状态码统计</a> · <a href="full-access-cases.json" target="_blank" rel="noopener">逐域名受限证据</a> · <a href="../reports/aws-access-audit-2026-09-28.md" target="_blank" rel="noopener">完整说明与统计边界</a></p>` : '尚无访问审计文件。';
      const connection = await json('full-trends-connection.json').catch(() => null);
      document.getElementById('run-connection').innerHTML = connection ? `<p>${esc(connection.conclusion)}</p><div class="run-reason-list">${connection.attempts.map(a=>`<div class="run-reason"><span>${esc(a.label)}<br><small>${esc(a.captured_at)} · UTC</small></span><strong>HTTP ${esc(a.http_status)}</strong></div>`).join('')}</div><p>上述记录均停在建立会话这一步，关键词查询请求尚未发出；均未返回 Retry-After。${esc(connection.warp_state)}</p><p class="run-mini">相同请求地址与客户端，只对照网络通道；不能据此断言具体限流原因，也没有验证其他浏览器或官方 API 是否可用。</p><p><a href="full-trends-connection.json" target="_blank" rel="noopener">查看三次请求时间、地址及响应校验和</a> · <a href="../reports/aws-trends-connection-2026-09-28.md" target="_blank" rel="noopener">查看 WARP 测试记录</a></p>` : '尚无连接诊断文件；这不代表趋势查询成功或没有搜索数据。';
      const age = (Date.now() - Date.parse(d.updated_at))/1000;
      const stale = d.status === 'screening' && age > 90;
      document.getElementById('live-state').textContent = `${t?.status==='paused'?'域名筛选完成；Google Trends 已暂停':statusNames[d.status] || d.status} · 最近更新 ${new Date(d.updated_at).toLocaleString('zh-CN')}${stale?' · 记录已超过90秒未更新，请检查连接或服务器状态。':' · 每30秒读取一次已保存进度。'}`;
      if (local) document.getElementById('live-state').textContent = `域名筛选完成；本地 Trends 已查询 ${n(local.queried)} / ${n(local.candidates)} 条 · 数据更新 ${new Date(local.updated_at).toLocaleString('zh-CN')} · 每30秒读取一次已保存进度。`;
      if (local?.error) {
        const error = document.createElement('p'); error.className='run-error'; error.textContent=`本地查询已暂停：${local.error}`;
        document.getElementById('run-local-trends').append(error);
        document.getElementById('live-state').textContent += ' · 本地查询已暂停';
      }
      document.getElementById('run-stats').innerHTML = [[d.covered,'已有判定记录',`总计 ${n(d.universe)} 个`],[d.pending,'等待探测',`本轮新完成 ${n(d.newly_completed)} 个`],[c?.corrected_decisions?.pass ?? d.decisions.pass,c?'复核后页面候选':'初判有页面内容','仍需语义与趋势验证'],[local?.automatic_matches ?? t?.automatic_matches ?? '—','趋势规则候选','尚未经最终复核']].map(([value,label,note])=>`<div class="run-stat"><span>${esc(label)}</span><strong>${typeof value==='number'?n(value):esc(value)}</strong><small>${esc(note)}</small></div>`).join('');
      const pct = (d.covered/d.universe*100).toFixed(1);
      document.getElementById('run-stage').innerHTML = `<p><strong>1. 域名筛选 ${pct}%</strong> · 复用 ${n(d.reused)} 条，本轮已完成 ${n(d.newly_completed)} 条。</p><progress class="run-progress" value="${d.covered}" max="${d.universe}">${pct}%</progress><p>2. AWS 原趋势任务（历史）：${esc(t?statusNames[t.status]||t.status:'等待任务状态')}${t?.candidates!=null?`；已查 ${n(t.queried)} / ${n(t.candidates)} 个候选词`:''}。</p>${t?.current_keyword?`<p>当前查询：<strong>${esc(t.current_keyword)}</strong></p>`:''}${t?.window?`<p>固定日期：${esc(t.window.start)} 至 ${esc(t.window.end)} · 美国 / 网页搜索</p>`:''}${t?.error?`<p class="run-error">${esc(t.error)}</p>`:''}${d.stop_reason?`<p class="run-error">${esc(d.stop_reason)}</p>`:''}<p class="run-mini">本轮已保存的解压文本约 ${(d.saved_decoded_bytes/1048576).toFixed(2)} MiB；这是正文体积，不是完整网络流量。已知 HTTP 尝试 ${n(d.known_http_attempts)} 次，另有 ${n(d.requests_with_unknown_count)} 条请求数不确定的记录。</p>`;
      document.getElementById('run-curation').innerHTML = c ? `<p>已核对全部 ${n(c.domain_total)} 条原始记录的覆盖与校验和，并追加 ${n(c.page_annotations)} 条停放/占位/验证页标注，其中 ${n(c.changed_decisions)} 条改变了初判。原始记录保留。</p><p>纠正后的技术分类：${n(c.corrected_decisions.pass)} 个页面候选、${n(c.corrected_decisions.skip)} 个跳过、${n(c.corrected_decisions.recheck)} 个证据不足。</p><p>原提词 ${n(c.original_candidates)} 条，补充 ${n(c.supplemented_phrases)} 个有原文支持的用途短语。${Object.entries(c.phrase_statuses).map(([key,value])=>esc(reviewLabels[key]||key)+' '+n(value)).join('；')}。这些都不是已验证机会。</p><p>逐条语义复核已记录 ${n(c.semantic_domains_reviewed)} 个漏提词页面、${n(c.semantic_terms_reviewed)} 个原候选词。尚未逐条复核：${n(c.unextracted_domains_unreviewed ?? c.unextracted_domains_still_needing_review)} 个页面、${n(c.semantic_terms_pending)} 个完整字段支持的原候选词；另有 ${n(c.semantic_domains_deferred)} 个页面已看字段，但仍需更多证据或明确查询。</p><p>语义复核由助手读取已保存的 Title/H1/Description 完成；每个原候选词目前仅核对一个选定来源，不代表已检查整站或其他来源，也不证明新词、增长或搜索量。旧提词器对网页再次要求精确词根，会漏掉复数和其他实际用途，当前只纠正已核对的例子。</p><p><a href="full-semantic-reviews.json" target="_blank" rel="noopener">逐条语义判断、原文及批次进度</a></p><p><a href="full-domain-review.json" target="_blank" rel="noopener">逐条页面纠正与原文</a> · <a href="full-keyword-reviewed.json" target="_blank" rel="noopener">全部短语复核与补充词</a> · <a href="../reports/aws-full-results-2026-09-28.md" target="_blank" rel="noopener">本轮完成记录与阻塞证据</a></p>` : '复核尚未生成。';
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
    document.getElementById('details-output').innerHTML = `<p>匹配 ${n(selected.length)} / ${n(rows.length)} 条，当前显示前 100 条；输入名称可精确查找。</p>${selected.slice(0,100).map(r=>`<details><summary><strong>${esc((kind==='domains'||kind==='semantic')?r.domain:r.keyword)}</strong> · ${esc(rowLabel(r))}</summary>${kind==='trends'?Object.entries(r.charts||{}).map(([stage,chart])=>`<p>${esc(({chart30:'30天',background:'半年背景',repeat30:'30天复测'})[stage]||stage)}：<a href="${esc(chart.url)}" target="_blank" rel="noopener">Google 原查询</a> · <a href="${esc(chart.evidence)}" target="_blank" rel="noopener">保存的原始证据</a></p>`).join(''):''}<pre>${esc(JSON.stringify(r,null,2))}</pre></details>`).join('')}`;
  }
  async function load(kindName,path) {
    try { const data = await json(path); rows = kindName==='semantic' ? data.domains : data; kind = kindName; renderRows(); }
    catch(e) { document.getElementById('details-output').textContent = `结果文件尚未生成或暂时无法读取（${e.message}）。`; }
  }
  document.getElementById('load-details').onclick = ()=>load('domains','full-domain-results.json');
  document.getElementById('load-reviewed').onclick = ()=>load('reviewed','full-keyword-reviewed.json');
  document.getElementById('load-semantic').onclick = ()=>load('semantic','full-semantic-reviews.json');
  document.getElementById('load-trends').onclick = ()=>load('trends',hasLocalTrends?'local-trends-results.json':'full-trends-results.json');
  document.getElementById('detail-search').oninput = renderRows;
  refresh(); setInterval(refresh,30000);
})();
