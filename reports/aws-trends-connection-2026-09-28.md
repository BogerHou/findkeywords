# Google Trends：原出口与 Cloudflare WARP 对照记录

2026-09-28，本轮 AWS 自动任务成功取得的关键词趋势数据仍为 **0**。按用户提出的方案，先在冷却后复测原出口，再安装官方 Cloudflare WARP 做独立通道对照。两次都在会话入口返回 HTTP 429，尚未发出关键词查询，不能把失败解释为关键词无数据。

## 三次真实请求

| 北京时间 | 通道 | 请求阶段 | HTTP | Retry-After | 已取得关键词数列 |
|---|---|---|---:|---|---:|
| 20:12:33 | AWS 直接访问，原批量任务首次请求 | 建立会话 | 429 | 未提供 | 0 |
| 20:50:34 | 相同 AWS 出口，间隔约38分钟 | 建立会话 | 429 | 未提供 | 0 |
| 20:56:10 | AWS → WARP 本机代理 → Cloudflare | 建立会话 | 429 | 未提供 | 0 |

地址均为 `https://trends.google.com/trends/explore?geo=US`，客户端均为 Python urllib、User-Agent `FindKeywordsResearch/1.0`。WARP 测试原计划随后查询网页原文支持的 `Trading Card Scanner`，但初始化立即失败，所以**这个词没有被提交查询**。域名抓取的请求次数与这三次 Google 请求是不同统计，不能混用。

这些证据只表明相同脚本在两种通道上的会话请求都被限流。不能据此断言是本任务高频访问、AWS IP 历史信誉、Cloudflare 出口、客户端特征或其他因素导致；也不能断言所有 Google Trends 访问方式均不可用。此次没有测试普通浏览器交互或已授权的官方 API。

## WARP 配置及收尾

通过 [Cloudflare 官方 Debian 软件源](https://pkg.cloudflareclient.com/)安装 `cloudflare-warp 2026.7.1377.0`。依据[官方 Linux 文档](https://developers.cloudflare.com/warp-client/get-started/linux/)和安装后的 CLI 帮助，使用免费客户端注册、本地代理模式及 MASQUE 协议，没有开通 WARP+。

- 连接前设置 `mode proxy`，代理只监听 `127.0.0.1:40000`。
- 指定此代理访问 Cloudflare 的检测地址，返回 `warp=on`、`loc=US`；确认不是仅修改 DNS。
- Trends 测试仅在该次 Python 客户端中显式配置代理，没有设置全局代理环境变量。
- 默认路由前后相同，SSH 和研究查看页正常。符合[本地代理模式只处理指定应用流量的设计](https://developers.cloudflare.com/warp-client/warp-modes/#local-proxy)。
- WARP 再次遇到429后立即停止测试，未更换节点、循环重连或重启原来的2,840词队列。
- 已执行 `warp-cli disconnect`，停止并禁用 `warp-svc.service` 自动启动。软件包及代理设置保留，当前40000端口不再监听。

所有 Google 请求均从 AWS 发起，未经过本地家宽。三次429都没有有效的关键词时间序列，所以当前无法计算增长倍数、持续非零天数或半年背景。

## 可核对的原始证据

查看页增加“Google Trends 连接诊断”，三次请求的精确 UTC 时间、URL、HTTP 状态、错误及正文 SHA256 在 `site/full-trends-connection.json`。完整日志和压缩响应同时保存在本地与 AWS：

| 记录目录 | 响应正文 SHA256 |
|---|---|
| `results/aws-full-20260928-trends/evidence/` | `4cf1330c9f91d401ba78a89b33adaf10571af6466dfd09a10923c4353d74b108` |
| `results/trends-connection-20260928/direct-after-cooldown/evidence/` | `46064345bcebcd3dd77edc760da66ee4f53d811a16bd2abb992a0719f9e7206d` |
| `results/trends-connection-20260928/warp-proxy/evidence/` | `f6ed41078ee5eb32900957b117fae7e05c66101393a0a5ccff1f3182f8ce1876` |

三个正文均为1,701字节；本次下载后重新解压并验证了校验和。`warp-proxy/summary.json`还包含 Cloudflare 的出口检测原文；它不是 Google 趋势成功证据。

下一步需要取得可用的数据来源或单独验证网页交互方式。已申请到的官方 Trends API 权限、人工导出的 Trends CSV 都可作为后续输入，但目前没有获得它们，不能声称任务恢复。离线页面语义复核仍可继续。
