# findkeywords：关键词研究工作台

## AWS 低成本采集（2026-09-28）

采集已迁移到 AWS Lightsail，由服务器直接访问候选网站。本地电脑只展示已保存的数据。本批使用固定版本 `e5acea3` 的 100 域名队列（80 优先池＋20 探索池），没有自动遍历 16,090 条，也没有启动新的 Google Trends 查询。

部署、连接情况、运行日志和核查命令见 [AWS 运行说明](reports/aws-deployment-2026-09-28.md)。名称筛选规则与预算演算见 [低成本方案](reports/low-cost-plan-2026-09-28.md)。工作台词根页展示本批进度及逐站的实际页面字段，网页是同步后的快照，不会自动发请求。

```sh
python3 scripts/serve_site.py
```

打开 http://127.0.0.1:8878/site/#roots 。Python 需要 3.10+；采集另外需要 curl 和系统 CA 证书。服务器已通过 24 项离线测试，按每批最多100个、单并发、限速及响应体上限执行。

SSH 私钥、机器网络配置、原始采集输出不进入 Git。服务器上的任务目录为 `/home/admin/findkeywords/results/aws-pilot-01`。运行配置只在服务器初始化，本地没有初始化，避免误用本机网络。

从结果目录或服务器紧凑导出离线更新工作台：

```sh
python3 -B scripts/build_prescreen_site.py --input results/aws-pilot-01/export.json
```

域名输入仍是 2026-08-27 至 2026-09-25 的历史名单；取得实际网页内容不等于确认首次上线日期，也不等于发现最近30天迅猛增长的关键词。

## 当前入口：51 词根筛选（2026-09-28）

本轮目标明确为：**只寻找最近 30 天刚开始起量、增长迅猛的关键词**。稳定老词、温和上涨和孤立尖峰不作为目标；历史 20% 升幅分类保留供核查，不用于本轮入选。此步只完成词根筛选，迅猛增长的数值门槛及新窗口实际查询尚未执行。

网站默认打开 [词根筛选](http://127.0.0.1:8878/site/#roots)。用户提供的 **51 个词根**完整保存在 `scripts/data/keyword-roots.json`，全部启用，不自动增加同义词或复数。关键词采用不区分大小写的完整单词匹配；域名采用首标签子串匹配，同起点较长词优先，重叠片段不重复计数。`Convert` 和 `Converter` 分别保留。后缀不参与词根匹配，本轮不按后缀或旧抽样配额再缩减。

已对历史全量 **2,096,176 个域名**离线重筛，名称命中 **16,090 个**；历史 **520 个已提取关键词**中有 **54 个**完整单词命中。两类结果分别展示，不因域名命中就认定网页关键词也命中。页面可按词根、结果类型及文本筛选，展开命中位置、名单文件与行号或原网页引文；选定词根后提供 Google Trends 相关上升查询入口，尚未采集结果。

**数据日期边界：**域名输入仍为 2026-08-27 至 2026-09-25 的历史名单，不是 9/28 最新域名采集；已有关键词曲线也仍是旧快照。本轮新增趋势查询为 0，确认新词机会为 0。按 9/28 计算的下轮 30 个完整日为 2026-08-29 至 2026-09-27。近零历史不能证明此前无人搜索，需单词复查和半年背景核验。

```sh
python3 -B scripts/build_roots_site.py --run-date 2026-09-28
python3 -B scripts/build_roots_site.py --self-test
```

第一条命令扫描保存的全量域名并构建新页面，不访问网络。配置修改后需要重新执行；启动器保留已构建的本轮结果，不重复扫描 1.3 GB 输入。报告见 [词根筛选报告](reports/roots-2026-09-28.md)，完整结果和 SHA-256 见 `data/runs/2026-09-28-roots/`、`site/roots-data.json`，纯英文词根表见 `site/keyword-roots.txt`。

## 历史试跑说明

**2026-09-28 网页预筛准备：**新增 [DNS / HTTPS / 内容判定规则与 Lightsail 操作说明](reports/prescreen-2026-09-28.md)，词根页可下载 100 域名试跑包。`scripts/probe_prescreen.py prepare` 仅离线抽样，`run` 默认也仅预览；当前网络执行支持 Linux/macOS，需要本机运行配置和显式 `--execute`。分为进入提词、本轮跳过、待复查，失败项保留原因，不把短页或一次访问失败直接判为垃圾站。此为早期准备记录；后续 AWS 执行情况见文首运行说明，16,090 条名称线索数量不因此改写。

离线验证：`python3 -B -m unittest discover -s scripts -p 'test_prescreen.py' -v`。所有 DNS 和外部进程默认禁止，测试使用模拟响应。

项目目标：从新注册域名候选名单出发，核实注册时间，抓取首页 title、meta description、H1，保留有页面证据的候选词，再核验 Google Trends 与搜索规模。第一轮实际使用预设词根筛选加 AI 主观选样，并非完整语义筛选。

## 近30天扩量（2026-09-26）

当时网站默认打开“近30天扩量”。本轮取得 2026-08-27 至 2026-09-25 的 30 份 WhoisDS 免费日名单，共 2,100,000 行；格式核验与 IDNA 去重后为 2,096,176 个域名。免费名单是供应商子集，不代表全球全部新域名。

按四个公开通道抽取 3,000 个域名做 HTTPS 页面探测：原43词根1,500、补充任务词根750、无词根字符探索600、其余合规名称150。固定 SHA-256 次序可以复算，不是商业价值排序。未选入队列的域名不被判无价值。

仅对有实质内容的页面查询 RDAP；只使用 `registration` 日期，固定近30天窗口。工作台区分近期注册、旧域名、日期未知、未查询、跨站跳转及页面失败，并保留 AI 内容复核对默认页等误收的纠正。**近期注册且现在有页面，不等于已经确认首次上线日期。** 网页词句也尚未做本轮 Trends / 竞争分析。

- [月度审计报告](reports/month-2026-09-26.md)：最新数量、覆盖范围、规则与边界。
- [全部探测结果](reports/month-domains-2026-09-26.csv) 与 [候选网页词句](reports/month-keywords-2026-09-26.csv)。
- `data/raw/month-2026-09-26/manifest.json`：30个压缩包的日期、CRC验证结果对应的成功状态、行数和 SHA-256。
- `data/runs/2026-09-26-month/screening/`：全量合法域名、重复与非法输入、四通道完整列表、入选理由、哈希、源文件行号与复算清单。
- `data/runs/2026-09-26-month/probes.jsonl`：增量保存的原始探测结果；内容复核独立保存在 `content-audit.json`。

仅从保存的结果重建月度工作台（不访问外部网站）：

```sh
python3 -B scripts/build_month_site.py
```

实际下载和探测命令（会访问外部网站；抓取支持从 JSONL 已完成项继续）：

```sh
python3 -B scripts/download_month.py --end 2026-09-25 --days 30 --output data/raw/month-2026-09-26
python3 -B scripts/screen_month.py data/raw/month-2026-09-26/*.txt --output data/runs/新的空筛选目录 --probe-limit 3000 --start-date 2026-08-27 --end-date 2026-09-25
python3 -B scripts/probe_month.py --input data/runs/2026-09-26-month/screening/probe_candidates.json --output data/runs/2026-09-26-month --workers 16 --timeout 6
```

## 关键词研究工作台

### 独立的后缀与名称通道

工作台新增 **后缀与名称**（`#tld`），与原四通道结果并列。复用同一份月度输入，按后缀组分配名额：`.com/.net/.org` 45%，`.ai/.io/.app/.dev/.tech` 25%，`.co/.me/.cc/.tv` 20%，其余后缀10%。这是可修改的探索预算，不代表后缀权威、价格或SEO加成。

名称不要求命中业务词根。通用英语词典完整分词、可读字符形态、短缩写和少量数字是四条名称线索路径；纯数字、数字过多、连续重复、过长等按公开规则排除。本通道偏英语且有误收漏收，不把“没有名称线索”写成“垃圾站”。词根命中只作诊断。

2,096,176 个输入中，1,676,738 个通过名称规则；扣除其中2,697个此前已探测域名后，从剩余池固定哈希抽取3,000个。2,977个没有命中原43词根，2,946个两份词表都未命中。各域名仍须经过首页、注册日期和内容复核，实际结果见[新通道审计](reports/tld-2026-09-26.md)。所有旧结果保留。

本轮3,000个均已探测：540个自动候选经AI内容复核纠正111个，保留429个。暂按跳过成人/博彩的研究范围，再去掉72个，得到357个后续研究候选和1,216条网页原文片段；这些还不是已验证的新词机会。行业标签采用显性词定位后逐条复核，可能有漏标；另有38个非候选页面仅因原文展示规则被暂时隔离，不改变其技术判定。

工作台与CSV使用中性公开快照，隔离记录无原文、目标地址和Trends入口。原始采集与分段复核仍保留在本地，但该轮原始目录不由HTTP服务直接提供；网站仅提供其 `public/` 子目录。离线修改内容复核后，先执行 `python3 -B scripts/merge_tld_audit.py --require-complete`，再重建页面。

```sh
python3 -B scripts/build_tld_site.py
```

该命令只从保存的证据生成网页和CSV。筛选脚本为 `scripts/screen_tld_names.py`；分组配置、词典快照及来源位于 `scripts/data/`。`--output` 要求新的空筛选目录，`--exclude-probed` 可指定多个已探测JSONL文件。网络核验沿用 `probe_month.py`，本轮用 `--reference-time '2026-09-26T03:20:33.293265+00:00'` 复用前一月度轮的注册窗口，以免比较时移动边界。

用户明确选择**近30个完整日，判断最近是否持续起量**，美国、网页搜索、Search term；半年仅作辅助背景。“第一次非零”仅代表在查询窗口内首次可见，0可能低于展示阈值，孤峰可能是噪声；必要时补查更长历史。这里选择的是时间窗口，没有要求把行业收窄为工具、软件或新技术。后缀筛选阶段先提供原文片段和手动查询入口，当时尚未实际查询这些片段。后续已另行逐站提炼搜索词并保存浏览器实际查询，当前覆盖、数列与待查状态见[近30天趋势](http://127.0.0.1:8878/site/#trends30)及[复核方法](data/runs/2026-09-26-tld/trend-protocol.json)。原文片段不直接等同于整理后的搜索词；前两轮32词的历史记录没有覆盖或改写。

启动本地网站后，打开 **http://127.0.0.1:8878/site/**。macOS 可双击项目内的 `启动关键词工作台.command`，或在项目目录执行：

```sh
python3 scripts/build_site_data.py
python3 scripts/serve_site.py
```

保持启动窗口打开；按 Ctrl+C 停止。服务只监听本机，不会公开到互联网。不需要安装前端依赖或填写 API key。

- **研究概览**：本轮结果、关键线索和 140,000 → 1,210 → 52 → 32 的筛选过程。
- **关键词库**：32 个词，可搜索、按分组与研究状态筛选、关注和导出。关注仅保存在当前浏览器。
- **关键词详情**：同图内的趋势曲线、逐日/逐周数值、采集条件与时间、网页原文、注册记录、公开基准和完整估算公式。
- **域名样本**：52 个实际探测的来源域名，保留选择理由、注册日期、最终页面与 title/description/H1。
- **分析方法**：八步流程、完整名称筛选规则、误筛漏筛例子，以及可自填参照量的校准演算器。
- **数据与报告**：原始报告、审计、JSON 数据的集中入口。

网站显示已保存的研究快照，**不会自动更新 Google Trends 或抓取域名**。修改研究数据后重新运行 `build_site_data.py`，刷新网页即可。前端文件在 `site/`，没有第三方脚本或外部字体。

## 第二轮结果（2026-09-26）

- [第二轮报告](reports/round2-2026-09-26.html)：32 个原候选词全部完成首轮查询，共记录 12 组实际 Trends 对比（7 组近90天、5组过去12个月）。仍未确认新词机会或低竞争。
- 美国、网页搜索、全部类别、Search term。浏览器 DOM 表格转录保存在 `round2-browser-captures.json`；55条数列的点数、总和、位置加权总和已与浏览器采集结果核对。不是官方 CSV 导出。
- `round2-anchor-research.json` 保留三个公开美国滚动月均估算及来源。`round2-estimates.json` 对5个词作条件性量级试算，展示换基准产生的偏差；不是当前月搜索量或置信区间。免费查询工具遇到人机验证后停止。
- [筛选审计](reports/screening-audit-2026-09-26.md) 解释 140,000 → 1,210 → 52；[原 Trends 对照](reports/trends-audit-2026-09-26.md) 保留90天与一年显示差异。

从保存的证据离线重新生成第二轮报告（不访问网站）：

```sh
python3 -B scripts/assemble_round2.py
python3 -B scripts/estimate_round2.py
python3 -B scripts/render_round2.py
```

## 近30天趋势队列的复核与重建

`site/#trends30` 展示从网页原文提炼的全行业词。首批100词保留原来的主观选样历史；后续420词按保存的原队列、每组最多5词逐组核验。覆盖完成仅表示每个词都有实际查询记录，不代表都有可用数列或已确认机会。

全量队列按多词比较图进行初查，不等于520次单词查询。页面分别显示多词比较的去重覆盖和组数、单词查询的去重覆盖和次数，以及比较图之后的单词复查覆盖；这些集合有重叠。多词图的全零或无图词仍需单词独立复查。页面还按每词最新记录统计前段全零、同一天首次非零等共同形态；其原因未确认，不能当成新需求同步诞生的证据，校验和也只验证转录一致性。

采集结束、所有 `packed-*.json` 完整写入后，离线重建并校验：

```sh
python3 scripts/assemble_trends30.py
python3 scripts/build_trends30.py
python3 scripts/build_trends30_browser_audit.py
python3 scripts/verify_trends30.py --require-complete --check-site
```

最后一条命令只读核对原待查队列的组ID、词和顺序，拒绝重复ID、重复队列词、缺失数列、校验和数量不匹配、伪造的无图零值；还核对最新采集记录作为主要判断、页面JSON/JS及后台协议是否一致。复查同一个词可以产生多条不同ID的记录，不算重复采集错误。

查询进行中可用 `python3 scripts/verify_trends30.py` 查看已保存进度；`python3 scripts/assemble_trends30.py --check-only` 只检查原始记录而不写快照。未实际查询的词保持待查；Google明确无图提示计为已查询但数据不足，不补成30个零值。页面数字、结果资源名和完成状态均从实际保存记录计算。

外部限制单独保存在 `query-session.json`；公开的 `public/query-session.json` 自动带出剩余组、剩余词及候选单词复查清单。Google 页面错误或异常流量限制不会计为查询成功。尚有待查词时，去掉 `--require-complete` 可核验部分成果；保留该参数则应明确失败，防止把未完成写成完成。恢复查询后需更新会话状态，保留原始限制证据于对应 `audit-*.json`。

半年复查保留原 `background-packed.json`，新增记录保存为 `background-名称-packed.json`。每份记录需保存词、范围、URL、采集时间、已核对日期、数列、双校验和及针对该词的 `reason`；明确无图则使用 `status: "no_data"` 和原始提示，数列保持空。重建后汇总至 `backgrounds.json` 及公开副本；同词多次记录全部保留，词详情采用最新背景，原来的 `background.json` 入口继续对应首份历史记录。

## 第一轮范围与边界

- 这轮使用 WhoisDS 免费每日名单，没有接入 CT 实时流，也没有购买数据服务。
- 原始名单为 2026-09-22 和 2026-09-25 两批，每批 70,000 行。名单日期只是供应商批次日期，不是逐个核验后的注册时间。
- 暂定“新注册”为抓取时最近 30 天；只使用 RDAP 的 `eventAction=registration`，不使用更新时间、到期时间或证书日期。
- 查询不到注册日期的域名单独保留为 unknown，不当成已确认新域名。重新注册的旧域名可能有新的当前注册时间，本轮不核查历史用途。
- 名称粗筛是43词根子串匹配，随后由 AI 主观选样，没有全量评分排名。它会误匹配，也会漏掉陌生新词；匹配数不等于有价值的网站数。
- 本次选择 40 个名称可辨识的任务样本，加 12 个潜在新概念样本；这是有目的选样，不代表整个名单的有效率。
- 首页抓取不执行 JavaScript、不绕过验证码或访问拒绝。静态页面无正文不等于站点不存在。
- 关键词由 AI 结合网页字段复核，尚未实现独立自动运行的提词流程。推测扩展词与网页直接支持的词分开。
- 未查询绝对搜索量、KD 或流量。已用浏览器手动检查美国近90天的 `agent permission matrix` 和 `sprite sheet maker`，观察记录在 `trends_checks.json`；其余 Google Trends 链接是待人工复核入口，不代表趋势已验证。

## 文件

- `data/raw/`：原始 ZIP 及域名 TXT，仅域名名单。
- `data/runs/2026-09-26/provenance.json`：来源、日期与原始文件 SHA-256。
- `data/runs/2026-09-26/name_matches.json`：第一轮名称匹配结果。
- `data/runs/2026-09-26/selected_domains.json`：实际探测样本及选择理由。
- `data/runs/2026-09-26/probes.json`：首页与注册日期探测结果；不保存注册人联系方式。
- `data/runs/2026-09-26/reviews_tools.json` 和 `reviews_novel.json`：52个域名的内容判断、候选词、原文证据与推测扩展词。
- `data/runs/2026-09-26/trends_checks.json`：第一轮2个词的Trends观察笔记，不是原始导出数据。
- `reports/`：复核结果、审计与候选词。

## 重跑

需要 Python 3 与系统 curl，不需要 API key。

```sh
python3 scripts/screen_names.py data/raw/whoisds-2026-09-22.txt data/raw/whoisds-2026-09-25.txt --output data/runs/2026-09-26/name_matches.json
python3 scripts/probe_domains.py --input data/runs/2026-09-26/selected_domains.json --output data/runs/2026-09-26/probes.json --workers 4 --max-age-days 30
python3 scripts/render_report.py
```

第二条命令会重新访问所选域名和公开 RDAP 服务。历史报告应保留原始探测结果；后续回访请使用新的输出文件路径。

报告生成器会检查关键词引文是否确实出现在对应的原始字段中。重新抓取后，如页面内容变化，需要重新审核关键词和证据，不能机械沿用旧审核结果。

## 数据与接口资料

- 名单：[WhoisDS 免费每日域名](https://www.whoisds.com/newly-registered-domains)
- 注册信息：[ICANN RDAP](https://www.icann.org/rdap/)
- [Google Trends 官方 API](https://developers.google.com/search/apis/trends)：2026-09-26 核查仍为需申请的 alpha。
- [SerpApi Google Trends](https://serpapi.com/google-trends-api)：第三方，需要 API key。
- [DataForSEO Google Trends](https://docs.dataforseo.com/v3/keywords_data-google-trends-explore-live/)：第三方，需要账户 API 凭据；不要混用其自有的 DataForSEO Trends 数据。
