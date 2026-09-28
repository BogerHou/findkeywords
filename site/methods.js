/* Methods and an evidence-preserving, in-memory calibration exercise. */
(function () {
  'use strict';

  const FALLBACK_TERMS = ('calculator converter generator checker tracker planner invoice subtitle ' +
    'transcript compress resize remove background pdf csv json markdown diagram audio video image photo ' +
    'prompt agent schema recipe itinerary resume flashcard chord sheet font palette mockup watermark ' +
    'screenshot timezone pronunciation worksheet timer countdown qr barcode').split(' ');
  const escapeHTML = value => String(value == null ? '' : value).replace(/[&<>"']/g, character =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  const whole = value => Number.isFinite(Number(value)) ? Math.round(Number(value)).toLocaleString('en-US') : '—';
  const decimal = value => Number.isFinite(Number(value)) ? Number(value).toFixed(4) : '—';
  function safeURL(value) {
    try {
      const parsed = new URL(String(value));
      return /^(https?:)$/.test(parsed.protocol) ? parsed.href : '';
    } catch (_) { return ''; }
  }
  function calibrationKeywords(data) {
    return (Array.isArray(data && data.keywords) ? data.keywords : []).filter(item =>
      Array.isArray(item.estimates) && item.estimates.length > 0);
  }
  function externalLink(url, label) {
    const allowed = safeURL(url);
    return allowed ? '<a href="' + escapeHTML(allowed) + '" target="_blank" rel="noopener noreferrer">' +
      escapeHTML(label) + '</a>' : escapeHTML(label);
  }
  function step(number, title, count, body) {
    return '<article class="method-step"><p class="eyebrow">STEP ' + number + '</p><h3>' + title +
      '</h3><strong>' + count + '</strong><p class="subtle">' + body + '</p></article>';
  }
  function nameExamples(data) {
    const source = data && data.screening && data.screening.examples || {};
    const falseMatches = Array.isArray(source.possible_substring_false_positives)
      ? source.possible_substring_false_positives : [];
    const excluded = Array.isArray(source.readable_names_excluded_for_no_dictionary_match)
      ? source.readable_names_excluded_for_no_dictionary_match : [];
    const choose = (records, domain, explanation) => {
      const record = records.find(item => item.domain === domain);
      return { domain, explanation: record && record.name_only_explanation || explanation };
    };
    const rows = [
      ['误筛', choose(falseMatches, '87wqr2a.top', '命中 qr，但整体像字母数字串；不能据此确认二维码需求。')],
      ['误筛', choose(falseMatches, 'magento-replatforming-agencies.com', 'agent 是 magento 的内部子串；不能据此推断 AI 智能体。')],
      ['漏筛', choose(excluded, 'personal-budget.app', '可读作“个人预算”，但没有命中任何词根。')],
      ['漏筛', choose(excluded, 'taxriskcheck.com', '可读作“税务风险检查”；词表有 checker，没有 check。')]
    ];
    return rows.map(([kind, item]) => '<tr><td>' + kind + '</td><td><code>' + escapeHTML(item.domain) +
      '</code></td><td>' + escapeHTML(item.explanation) + '</td></tr>').join('');
  }

  window.renderMethods = function (data) {
    const keywords = calibrationKeywords(data);
    const selectedIndex = Math.max(0, keywords.findIndex(item => item.keyword === 'sprite sheet maker'));
    const suppliedTerms = data && data.screening && data.screening.terms;
    const terms = Array.isArray(suppliedTerms) && suppliedTerms.length ? suppliedTerms : FALLBACK_TERMS;
    const options = keywords.map((item, index) => '<option value="' + index + '"' +
      (index === selectedIndex ? ' selected' : '') + '>' + escapeHTML(item.keyword) + '</option>').join('');

    return '<div id="method-root">' +
      '<div class="section-heading"><div><p class="eyebrow">RESEARCH METHOD</p><h1>分析方法</h1>' +
      '<p class="subtle">从域名名单到关键词判断，每一步都说明依据、损失和仍未完成的验证。</p></div></div>' +
      '<section class="panel" aria-labelledby="method-process-title"><h2 id="method-process-title">本次研究走到了哪一步</h2>' +
      '<div class="method-grid">' +
      step('01', '取得域名名单', '140,000 个域名', 'WhoisDS 的 9 月 22 日和 25 日批次，各 70,000 个。入口是域名名单，尚未接入 SSL 证书日志；批次日期不等于注册日期。') +
      step('02', '按名称规则筛选', '1,210 个命中', '43 个预设词根 + 长度限制 + 数字限制。只判断字符串，不代表这些名称都有意义，也不是全部新词。') +
      step('03', 'AI 主观选样', '52 个样本', '40 个可辨识任务名称 + 12 个概念线索。没有完整评分或排名；没有逐项记录其余 1,158 个为什么未选。') +
      step('04', '核验注册与网页', '42 近期 · 1 旧 · 9 未知', '仅对 52 个样本查询 RDAP 并探测网页。“近期”为注册不超过 30 天；新域名也可能跳转至已有产品。') +
      step('05', '提取有依据的词', '16 个来源 · 32 个原词', '依据 title、description、H1 等页面内容。原始证据与扩展猜想分开保存；页面使用某个词，不等于已靠它获得流量。') +
      step('06', '检查搜索趋势', '32 个词 · 12 组对比', '美国、网页搜索、全部类别，使用 Search term。记录查询条件及完整序列；90 天与 12 个月的结果分别解释。') +
      step('07', '参照已知词试算', '5 个词有条件估算', '用同一张图的期间均值与公开基准相除。结果只用于探索量级，公开报告月份与 Trends 期间未严格对齐。') +
      step('08', '核验竞争与机会', '尚未完成', '还没有完整检查搜索结果、竞争对手、排名难度和可获得点击。没有确认“起势且低竞争”的建站机会。') +
      '</div></section>' +

      '<section class="panel" aria-labelledby="method-rules-title"><div class="section-heading"><div><h2 id="method-rules-title">名称筛选：实际执行的规则</h2>' +
      '<p class="subtle">临时试跑规则，未经过效果验证。命中预设词表才有机会进入后续样本，这会漏掉未知新概念。</p></div>' +
      '<a class="btn btn-secondary" href="../reports/screening-audit-2026-09-26.md" target="_blank" rel="noopener">查看完整筛选审计 ↗</a></div>' +
      '<div class="formula-box"><code>名称 = 域名去空白、转小写后，第一个点之前的部分<br>' +
      '保留 = 包含任意词根 AND 名称长度 &lt; 34 AND 没有连续 3 个数字</code></div>' +
      '<p class="subtle">不做分词、词边界识别或语义判断；允许单个或两个连续数字。长度上限为 33 个字符。</p>' +
      '<details><summary>展开全部 ' + escapeHTML(terms.length) + ' 个词根</summary><p>' + terms.map(term =>
        '<span class="tag">' + escapeHTML(term) + '</span>').join(' ') + '</p></details>' +
      '<div class="table-wrap"><table class="mini-table"><caption>筛选数量复算</caption><thead><tr><th scope="col">条件</th><th scope="col">剩余域名</th><th scope="col">本步排除</th></tr></thead><tbody>' +
      '<tr><td>原始名单去重</td><td>140,000</td><td>0</td></tr>' +
      '<tr><td>包含至少一个词根</td><td>1,224</td><td>138,776</td></tr>' +
      '<tr><td>名称长度小于 34</td><td>1,221</td><td>3</td></tr>' +
      '<tr><td>没有连续三个数字</td><td>1,210</td><td>11</td></tr></tbody></table></div>' +
      '<div class="table-wrap"><table class="mini-table"><caption>误筛与漏筛：每类两个例子</caption><thead><tr><th scope="col">类型</th><th scope="col">域名</th><th scope="col">说明</th></tr></thead><tbody>' +
      nameExamples(data) + '</tbody></table></div>' +
      '<p class="subtle">上述解释只针对名称，没有据此确认网站业务、搜索量或商业价值。52 个样本是 AI 主观选取，不能当作“最好的 52 个”。</p></section>' +

      '<section class="panel" aria-labelledby="method-calculator-title"><div class="section-heading"><div><p class="eyebrow">TRY THE CALCULATION</p>' +
      '<h2 id="method-calculator-title">用已知词演算量级</h2><p class="subtle">选择一组已有证据，查看完整公式；修改基准量可比较不同假设，不会改变研究记录。</p></div></div>' +
      (keywords.length ? '<div class="method-grid"><label class="field" for="method-target">目标关键词<select id="method-target">' + options +
      '</select></label><label class="field" for="method-anchor">同图参照关键词<select id="method-anchor"></select></label>' +
      '<label class="field" for="method-volume">基准月均搜索量<input id="method-volume" type="number" min="1" max="1000000000" step="any" inputmode="decimal" aria-describedby="method-volume-note method-error"></label></div>' +
      '<p id="method-volume-note" class="subtle">允许 1 至 1,000,000,000。自填数值仅为假设；该数字是关键词搜索量，不是某网站获得的访问量。</p>' +
      '<p id="method-error" class="notice" role="alert" hidden></p>' +
      '<div class="formula-box" aria-live="polite" aria-atomic="true"><p id="method-scenario" class="eyebrow"></p>' +
      '<p id="method-formula"></p><p><strong id="method-result"></strong></p><p id="method-comparison" class="subtle"></p></div>' +
      '<div class="table-wrap"><table class="mini-table"><caption>本组计算的原始依据</caption><tbody>' +
      '<tr><th scope="row">目标词同图均值</th><td id="method-target-mean"></td></tr>' +
      '<tr><th scope="row">参照词同图均值</th><td id="method-anchor-mean"></td></tr>' +
      '<tr><th scope="row">公开基准量</th><td id="method-original-volume"></td></tr>' +
      '<tr><th scope="row">基准报告月份</th><td id="method-report-month"></td></tr>' +
      '<tr><th scope="row">来源</th><td><a id="method-source" target="_blank" rel="noopener noreferrer"></a><span id="method-source-unavailable" hidden>来源链接不可用</span></td></tr>' +
      '<tr><th scope="row">原始对比图</th><td><a id="method-chart" target="_blank" rel="noopener noreferrer">在 Google Trends 查看 ↗</a><span id="method-chart-unavailable" hidden>查询链接不可用</span> <span id="method-capture" class="subtle"></span></td></tr>' +
      '<tr><th scope="row">研究记录中的估算</th><td id="method-recorded-result"></td></tr></tbody></table></div>' +
      '<button id="method-reset" class="btn btn-secondary" type="button">重置为公开基准量</button>' :
      '<p class="notice">当前数据没有可演算的估算记录。</p>') +
      '<p class="subtle">均值显示到小数点后 4 位，计算使用原始精度。已有记录采用同图 53 周的算术均值，量级按整数显示。</p>' +
      '<div class="notice"><strong>为什么不能把试算当作精确搜索量？</strong><p>两项发票关键词交叉校准：以 22,200 为基准，另一词试算约 25,880，而供应商对该词给出的月均估算为 14,800，相差约 74.9%。不同基准产生的跨度只是敏感性结果，不是置信区间。</p>' +
      '<p>基准来自 2026 年 7 月、8 月公开报告，具体统计起止日期及近似词合并口径未核实；年度均量也不能代表本月或建站后的访问量。</p></div></section>' +

      '<section class="panel" aria-labelledby="method-trends-title"><div class="section-heading"><div><h2 id="method-trends-title">读 Trends 时保留这些边界</h2>' +
      '<p class="subtle">同一个词，在不同时间范围和对比组合下，可能显示不同结果。</p></div></div>' +
      '<div class="method-grid"><article class="method-step"><h3>指数不是搜索次数</h3><p>100 是该查询范围内的相对热度峰值，不能读成 100 次搜索。0 可能与低量、抽样和取整有关，不等于完全无人搜索。</p></article>' +
      '<article class="method-step"><h3>只能用同图比值</h3><p>目标词与参照词必须进入同一次对比，统一地区、时间、类别、搜索渠道与字词类型。两张独立图各自的 100 不能直接相除。</p></article>' +
      '<article class="method-step"><h3>90 天与 12 个月不同</h3><p>agent permission matrix 在本次复核中，90 天主图出现单日尖峰，切换 12 个月则提示数据不足。它没有因此被确认有持续需求。</p></article>' +
      '<article class="method-step"><h3>孤峰还不能确认机会</h3><p>低量词偶发尖峰可能来自统计噪声。需要连续证据、其他来源与竞争调查，才能进一步决定是否值得做。</p></article></div>' +
      '<p>' + externalLink('https://support.google.com/trends/answer/4365533?hl=zh-Hans', 'Google 官方：Trends 数据与常见问题 ↗') +
      ' · <a href="../reports/trends-audit-2026-09-26.md" target="_blank" rel="noopener">本次 Trends 差异核验 ↗</a></p></section></div>';
  };

  window.bindMethods = function (data) {
    const root = document.getElementById('method-root');
    if (!root) return;
    const get = id => root.querySelector('#method-' + id);
    const targetSelect = get('target');
    const anchorSelect = get('anchor');
    const volumeInput = get('volume');
    const reset = get('reset');
    const keywords = calibrationKeywords(data);
    if (!targetSelect || !anchorSelect || !volumeInput || !reset || !keywords.length) return;
    const write = (id, value) => { const element = get(id); if (element) element.textContent = value; };
    const currentKeyword = () => keywords[Number(targetSelect.value)];
    const currentEstimate = () => {
      const keyword = currentKeyword();
      return keyword && keyword.estimates[Number(anchorSelect.value)];
    };
    function setLink(id, value, label) {
      const link = get(id);
      const fallback = get(id + '-unavailable');
      if (!link) return;
      const url = safeURL(value);
      link.hidden = !url;
      if (fallback) fallback.hidden = Boolean(url);
      if (url) link.href = url;
      else link.removeAttribute('href');
      if (label) link.textContent = label;
    }
    function updateCalculation() {
      const record = currentEstimate();
      if (!record) return;
      const volume = Number(volumeInput.value);
      const targetMean = Number(record.target_mean);
      const anchorMean = Number(record.anchor_mean);
      const validInput = volumeInput.value.trim() !== '' && Number.isFinite(volume) && volume >= 1 && volume <= 1000000000;
      const validMeans = Number.isFinite(targetMean) && targetMean >= 0 && Number.isFinite(anchorMean) && anchorMean > 0;
      const error = get('error');
      if (error) {
        error.hidden = validInput && validMeans;
        error.textContent = !validInput ? '请输入 1 至 1,000,000,000 之间的有效数字。' :
          !validMeans ? '该记录缺少有效的同图均值，暂不能计算。' : '';
      }
      volumeInput.setAttribute('aria-invalid', String(!validInput));
      if (!validInput || !validMeans) {
        write('scenario', '等待有效输入');
        write('formula', '基准月均搜索量 × 目标词同图均值 ÷ 参照词同图均值');
        write('result', '—');
        write('comparison', '原始研究记录保持不变。');
        return;
      }
      const result = volume * targetMean / anchorMean;
      const original = Number(record.conditional_monthly_estimate);
      const changed = volume !== Number(record.anchor_volume);
      write('scenario', changed ? '自填假设 · 未改动原始记录' : '复现记录中的条件性估算');
      write('formula', volume.toLocaleString('en-US', { maximumFractionDigits: 6 }) + ' × ' + decimal(targetMean) +
        ' ÷ ' + decimal(anchorMean) + ' ≈ ' + whole(result));
      write('result', '约 ' + whole(result) + ' 次 / 月（条件性量级）');
      if (!changed) write('comparison', '使用公开基准量，与当前研究记录一致；这仍是量级试算。');
      else if (Number.isFinite(original) && original > 0) {
        const difference = (result - original) / original * 100;
        const percent = (difference > 0 ? '+' : '') + difference.toFixed(1) + '%';
        write('comparison', '原记录约 ' + whole(original) + ' 次 / 月；当前假设相对原记录 ' + percent + '。');
      } else write('comparison', '这是自填基准产生的假设结果，不写入原始研究记录。');
    }
    function chooseAnchor() {
      const record = currentEstimate();
      if (!record) return;
      volumeInput.value = String(record.anchor_volume);
      write('target-mean', decimal(record.target_mean));
      write('anchor-mean', decimal(record.anchor_mean));
      write('original-volume', whole(record.anchor_volume) + ' 次 / 月（供应商估算）');
      write('report-month', String(record.anchor_report_month || '未提供'));
      write('recorded-result', '约 ' + whole(record.conditional_monthly_estimate) + ' 次 / 月（条件性估算）');
      write('capture', record.capture_id ? '记录：' + record.capture_id : '');
      const sourceURL = safeURL(record.anchor_source_url);
      let sourceLabel = '公开基准来源 ↗';
      if (sourceURL) sourceLabel = new URL(sourceURL).hostname + ' ↗';
      setLink('source', record.anchor_source_url, sourceLabel);
      setLink('chart', record.query_url);
      updateCalculation();
    }
    function chooseTarget() {
      const keyword = currentKeyword();
      if (!keyword) return;
      anchorSelect.replaceChildren();
      keyword.estimates.forEach((record, index) => {
        const option = document.createElement('option');
        option.value = String(index);
        option.textContent = record.anchor_keyword;
        anchorSelect.appendChild(option);
      });
      chooseAnchor();
    }
    targetSelect.addEventListener('change', chooseTarget);
    anchorSelect.addEventListener('change', chooseAnchor);
    volumeInput.addEventListener('input', updateCalculation);
    reset.addEventListener('click', chooseAnchor);
    chooseTarget();
  };
}());
