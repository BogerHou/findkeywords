# Google Trends 查询复核 · 2026-09-26

这份记录区分页面观察、自己的解释和未核实之处。原报告已备份在 [修订前报告](evidence/pilot-before-audit-2026-09-26.html)，原笔记保留在 [trends-checks-before-audit.json](evidence/trends-checks-before-audit.json)。

## 原来“孤立尖峰”的来源

原查询打开的是 [Google Trends 旧版 Explore：美国／过去90天／agent permission matrix](https://trends.google.com/trends/explore?date=today%203-m&geo=US&q=agent%20permission%20matrix&hl=en)。

| 条件 | 页面实际显示 |
| --- | --- |
| 输入内容 | agent permission matrix（普通空格） |
| 查询类型 | Search term（搜索字词） |
| 地区 | United States |
| 时间范围 | Past 90 days |
| 类别 | All categories |
| 搜索渠道 | Web Search |
| 界面语言 | English |
| 本次复核会话 | Codex 内置浏览器，未登录 |

原先通过浏览器读取的是页面无障碍树中的 “A tabular representation of the data in the chart.” 表格。本次重新打开后，表格仍显示 Jun 26 至 Sep 26 的日期：Sep 21 为 100，其余显示日期为 0；本次还直接查看了页面截图，主图可见这一尖峰。

下面是本次工具读取结果的局部转录，不是 Google 官方 CSV 导出文件。页面日期标签没有年份；2026 年来自查询当天及相对时间范围的上下文。

```text
Search field: agent permission matrix
Select time period: Past 90 days
United States / All categories / Web Search

Interest over time → A tabular representation of the data in the chart.
x       y1
Sep 19   0
Sep 20   0
Sep 21 100
Sep 22   0
Sep 23   0
Sep 24   0
Sep 25   0
Sep 26   0
```

同一查询的 Related topics 和 Related queries 两块均显示数据不足。因此“主图有一个尖峰”与“相关查询数据不足”也是不同位置的观察，不能合并描述为整页都有数据。

## 与用户链接对照

用户提供的是 [新版 Explore 链接](https://trends.google.com/explore?date=today%201-y&geo=US&q=agent%2520permission%2520matrix)。它与原查询至少存在以下 URL 差异：

| 项目 | 原查询 | 用户提供的链接 |
| --- | --- | --- |
| 路径 | /trends/explore | /explore |
| date 参数 | today 3-m | today 1-y |
| q 参数进行一次 URL 解码后 | agent permission matrix | agent%20permission%20matrix |

本次直接打开用户链接，当前未登录会话只显示新版 Explore 的登录入口与“继续使用传统版”入口，没有展示查询输入框或图表。因此没有证据断言新版页面如何进一步解码 q，也不能断言百分号编码就是用户看到“没有数据”的原因。

随后做了更直接的对照：在已经显示结果的旧版页面中保持字词、地区、类别和搜索渠道不变，只通过时间下拉菜单把 Past 90 days 改为 Past 12 months。加载后主图 Interest over time 显示：

> Hmm, your search doesn't have enough data to show here.

此提示已经通过无障碍文字和页面截图两种方式确认。页面地址变为 [旧版同词查询，当前默认显示过去12个月](https://trends.google.com/trends/explore?geo=US&q=agent%20permission%20matrix&hl=en)。复查时应以页面时间控件为准。

| 对照 | 主图观察 | 能得出的结论 |
| --- | --- | --- |
| 旧版／普通空格／美国／过去90天 | Sep 21 为100，其余显示日期为0 | 此会话下90天主图显示孤立尖峰 |
| 同一页面仅改过去12个月 | 数据不足，无主图曲线 | 一年范围确实可以显示数据不足，无需改变字词编码或界面版本 |
| 用户原始新版链接 | 当前会话停留在登录入口 | 未直接核验用户所见的新版图表 |

时间范围改变足以在本次对照中复现“没有数据”。Google 在这个字词上为何给出两种显示，涉及其采样、聚合或展示门槛的具体内部原因，本次没有证据确定。不能把某一种内部机制写成已证实原因，也不能保证其他会话或后续日期的结果完全相同。

## 证据保留情况与结论边界

原 `trends_checks.json` 是 AI 写下的观察笔记，不是 Google 原始数据。其 `checked_at` 为 `2026-09-26T01:39:30.346811+00:00`（北京时间09:39:30），表示当时两条查询笔记写入的时间，不是每次查询的精确请求时间。原查询当时没有保存官方 CSV 或截图文件；本次截图在任务的浏览器工具输出中，本地也没有成功导出官方 CSV。这里提供的是页面链接、条件、直接读取的局部转录和复查方法，不能把笔记包装成原始导出证据。

Google 说明 Trends 是抽样数据，并按地区与时间对相对热度归一化到 0–100。因此 100 不是100次搜索，更不能直接证明搜索规模值得做站。[Google 官方数据说明](https://support.google.com/trends/answer/4365533?hl=zh-Hans)

对这个词的正确状态仍是“待观察”：90天孤立尖峰及一年数据不足，都不能证明持续增长、稳定搜索需求、低竞争或明确商业机会。

## 第二个词的原记录

原笔记中另一个词为 [sprite sheet maker，美国过去90天](https://trends.google.com/trends/explore?date=today%203-m&geo=US&q=sprite%20sheet%20maker&hl=en)。当时记录：Jul 25 为100，9月多个非零日期，Related queries → Rising 显示 `gif to sprite sheet +80%`、`fnf sprite sheet maker +70%`。

这段是原有观察笔记的复述；本次针对用户质疑复查的是 agent permission matrix，没有重新核验第二个词，也没有为第二个词保存原始 CSV。两个相关查询的涨幅不是整个 sprite sheet maker 主词的涨幅，更不证明这些词是新词或低竞争词。

## 自行复查

1. 打开上面的旧版90天查询链接，确认输入框为带普通空格的 `agent permission matrix`，类型为 Search term。
2. 核对 United States、Past 90 days、All categories、Web Search，查看 Interest over time 主图；相关查询区域应另行查看。
3. 只把时间范围改为 Past 12 months，再看主图是否显示数据不足。
4. 复查时记录当天日期和实际控件；相对日期链接会随打开日期变化。若结果不同，保留当前截图或官方 CSV，不沿用旧笔记下结论。
