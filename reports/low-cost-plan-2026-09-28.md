# 少请求找新词：离线缩量与异机运行

本轮只准备方案、代码和队列，**没有访问候选域名或新增 Google Trends 查询**。网站 16,090 个是历史名称线索，不要求全部扫描。

## 离线复算的数量

| 步骤 | 数量 | 含义 |
| --- | ---: | --- |
| 51 词根命中 | 16,090 | 仍来自 2026-08-27 至 2026-09-25 的旧名单 |
| 有近7天历史探测记录 | 302 | 月度两轮289个，首轮另外13个；先复查旧证据，本轮不立即重抓 |
| 待新请求 | 15,788 | 不说明是否可访问 |
| 同一首标签跨后缀暂留一个 | 15,346 | 442个同名其他后缀暂缓；不宣称它们属于同一网站或所有者 |
| 请求优先池 | 5,696 | 有较明确词根位置及较简单名称，不代表有效站点 |
| 探索池 | 9,650 | 宽泛词根、词根位于词内、较长名称等仍然保留 |
| 本次实际请求预算 | **100** | 80个来自优先池，20个来自探索池；其余不自动执行 |

原始16,090条中，7,330条只命中 Online、Example、Sample、Format、Scheme、Pattern 中的一个或多个。这是下调优先级的依据，不是证明其没有价值。只有 Online 的名称达6,094条；包含 Online 及其他词根的情况另算，不能混淆。

“剩余100个”是预算选择，不是已经证明只有100个合格。纯名称方法不能保证找出有流量的站点；继续提高阈值会漏掉新词，因此保留20%探索份额，且不要求名称被旧词典收录。

## 可复算的请求顺序

1. 历史缓存：按2026-09-28核对近7天检查记录，只导出域名、时间和来源索引。旧失败也先复查记录，不立即重试；旧成功不能证明当前仍成功。缓存日期随重新构建更新。
2. 同名分组：仅将完全相同的域名首标签放在同组，例如 `example.com` 与 `example.net`。组内按固定SHA-256次序选代表，其他保留。没有把共享IP、同一个CDN或相似拼写当成同站。
3. 优先池同时满足：命中上述6个宽泛词根以外的词根；至少一个这样的词根出现在首标签开头或结尾；首标签≤24字符、数字≤2、连字符≤1且无连续连字符、没有同一字符连续4次。位于词内的偶然子串（如 information 中的 format）不会单凭它进入优先池。该规则仍然会误收和漏收，不证明语义或业务类型。
4. 优先池和探索池分别按51词根轮流取样，同池内固定SHA-256排序、域名去重；种子为 `findkeywords-cost-v1`。80/20名额每4个优先插入1个探索，以免中途暂停时全部漏掉探索项。没有按行业排除，也没有将后缀当权威或SEO质量认证。
5. 第1批结果出来后，统计两组“取得业务内容的比例”和“有网页证据的不同关键词数”，再决定是否值得继续下一批。起量机会必须经Trends复核，不能用抓到网页的比例替代。当前尚无本轮命中率。

配置：`scripts/data/cost-policy.json`。可查看的输入与队列：`site/roots-data.json`、`site/probe-cache-index.json`、`site/cost-plan.json`、`site/prescreen-queue.json`。完整逐域名分类审计保存在本地 `data/runs/2026-09-28-cost-plan/audit.json`，不纳入Git。

离线重建（不联网；在另一台电脑也可使用随仓库携带的索引复算）：

```sh
python3 -B scripts/build_cost_plan.py --as-of 2026-09-28
```

如需按实际当天计算缓存期限，省略 `--as-of`。这仅更新预算和缓存判断，不会下载新的域名名单。只在原始证据俱全的电脑上使用 `--refresh-cache` 重建历史索引；索引不是原始证据的替代品。

## 更直接的获词路径：先看搜索需求

对于“最近30天刚起量、迅猛增长”的目标，建议增加这条路径：

**词根 → Trends相关查询的Rising列表 → 候选词近30天曲线 → 半年背景 → 少量相关网站。**

优先从用户词根中选较具体的10–15个做第一批，例如 Translator、Generator、Calculator、Converter、Template、Checker、Detector、Extractor、Viewer、Planner；这些是使用场景，不限制产品所属行业。Online等宽泛词根保留作后续扩展。网站现有词根入口可以打开相关查询；这里没有声称已经采集到新词。

Google的Rising列表比较所选周期与前一个相等周期，Breakout代表增长超过5,000%。它可以用于发现线索，但不能证明“最近才出现”、持续迅猛增长或有足够绝对量；必须继续检查单词曲线、首次可见时间、末段持续性和半年背景。[Google官方相关查询说明](https://support.google.com/trends/answer/4355000?hl=en)、[Google数据解释](https://newsinitiative.withgoogle.com/resources/trainings/google-trends-understanding-the-data/)。

51个词根不等于51个HTTP请求，Trends页面内部会请求多个接口，也可能限流。没有在本机批量运行，也没有把非官方接口描述成稳定可用API。自动补全、搜索结果数量、域名价格不能直接证明最近30天起量。

## 流量按什么算

域名数量不等于打开完整浏览器页面的流量。本工具只请求robots.txt和首页HTML，不加载图片、CSS或执行JavaScript，不额外做一遍HEAD或逐域名证书查询。

下面仅作预算演算，假设“每域名合计收到的robots+HTML响应体”为指定均值；**不是实际测量，也不包含DNS、TLS、响应头、重定向和重试等开销**：

| 每域名响应体均值 | 100个 | 16,090个 |
| --- | ---: | ---: |
| 50 KiB | 4.9 MiB | 785.6 MiB |
| 100 KiB | 9.8 MiB | 1.53 GiB |

试跑版v2把每次首页响应的读取上限从512 KiB降到128 KiB，robots.txt上限32 KiB。完整响应超限则暂缓，取得的片段仅保存为不完整证据，不把截断误认为空站；不自动重抓。通常无跳转每域名2次HTTPS请求，100域名的合计响应体读取额度约15.6 MiB；它不是网络账单硬上限，缓冲、压缩、协议开销、重定向会改变实际流量。

串行、全局至少2秒、同主机至少5秒、429暂停、断点保存仍保留。更多内容判定原则见旧[预筛说明](prescreen-2026-09-28.md)；操作系统、队列和字节限制以本文和v2脚本为准。

## 在另一台macOS上运行

GitHub仓库：[BogerHou/findkeywords](https://github.com/BogerHou/findkeywords)。仓库用于同步代码、网站快照和小批请求队列。代码使用Python 3.10+和curl；不需要浏览器Cookie、代理账号或付费API。

在用户完成首次上传后，另一台Mac克隆：

```sh
git clone https://github.com/BogerHou/findkeywords.git
cd findkeywords
python3 scripts/serve_site.py
```

打开 `http://127.0.0.1:8878/site/#roots` 即可查看。也可运行“启动关键词工作台.command”。启动器只读取已保存的页面快照，不重建1.3GB输入，也不自动抓取。涉及未随Git携带的原始证据链接，在异机不可用；汇总、词根和历史曲线仍可查看。

只在负责发请求的另一台Mac上进行本机配置（此命令本身不联网）：

```sh
python3 -B scripts/probe_prescreen.py network-init --label other-mac
```

配置保存在 `config/network.local.json`，绑定当前主机及用户环境，已加入.gitignore；不要复制到其他电脑。它防止误运行，不认证真实出口。仍需确认该电脑未走你要保护的家宽代理；脚本拒绝常见代理环境变量，不能识别所有TUN/VPN路由。

先预览（不联网）：

```sh
python3 -B scripts/probe_prescreen.py run --input site/prescreen-queue.json --output results/pilot-01 --limit 100
```

以下命令才真正访问候选网站：

```sh
python3 -B scripts/probe_prescreen.py run --input site/prescreen-queue.json --output results/pilot-01 --limit 100 --execute
```

结果保存到 `results/pilot-01/`，不会随Git上传。普通中断可沿用同一命令继续已选队列；遇到429等触发暂停的批次不会自动继续。它不会自行扩展到16,090个域名，也不会自动查询Trends。

前批正常完成并核对内容命中率后，可以离线合并结果、准备新的100条队列，避免重抓：

```sh
python3 -B scripts/build_cost_plan.py --reuse-results results/pilot-01/results.jsonl
```

这一步不会执行新队列。若前批因429等原因暂停，脚本拒绝据此直接推进下一批，应先排查暂停原因。合并后的缓存索引仅含域名、时间、原因和来源哈希，原始HTML仍留在本机results目录。

## GitHub携带范围

`.gitignore` 排除 data/raw、data/runs、results、本机网络配置、密钥和压缩试跑包。保留scripts、site、reports文档及汇总，包含执行所需的100域名队列。原始及中间数据约1.8 GiB，最大单文件约1.2 GiB；GitHub常规Git上传阻止超过100 MiB的文件，因此不能直接把全部原始研究目录提交。[GitHub官方大文件说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)。

忽略规则不删除任何本地文件。首次上传前查看 `git status` 和文件列表；不要强制添加已忽略的网络配置或大数据目录。原始证据继续在原电脑保存，需要跨机完整复核时可另行按需传输，而不是每次git pull都搬运。
