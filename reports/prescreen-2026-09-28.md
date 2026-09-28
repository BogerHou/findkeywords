# 网页轻量预筛：规则与 Lightsail 试跑

> 历史v1准备记录。后续已改为另一台macOS运行、80优先＋20探索的100条队列，以及首页128 KiB / robots32 KiB上限。请使用[更新后的运行说明](low-cost-plan-2026-09-28.md)和v2脚本。此文其余原始描述用于追溯，旧试跑包没有部署或执行。

状态：**程序和 100 个域名试跑队列已准备，未部署、未执行网络预筛。** 16,090 是历史域名名称命中数，不是可访问网站数；目前没有新增淘汰数、合格网站数或关键词机会数。

## 先做什么

处理顺序：域名名单 → 51 词根离线筛选 → DNS / HTTPS / HTML 预筛 → 网页关键词提取 → 近30天起量核验。预筛仍需联网，节省的是无效网站后面的浏览器渲染、深度抓取、RDAP 和 Trends 查询，不能让所有网络请求消失。

HTTPS 请求同时验证证书并读取 HTML，不额外发送 HEAD 或单独握手。先读取 robots.txt；正常无跳转时通常为 robots.txt 和首页各一次请求，加 DNS 查询。重定向可能增加请求，DNS / TLS 失败则提前结束。robots.txt 的 404/410 不代表首页不存在。

## 三种结果，均保留证据

| 情况 | 本轮处理 | 判定依据 |
| --- | --- | --- |
| 无法解析、连接失败、超时 | 待复查，不继续提词 | dns_error / connect_error / timeout；不直接认定未注册或永久无法访问 |
| 证书校验失败、TLS 握手失败 | 待复查，不继续提词 | tls_certificate_error / tls_handshake_error；不能据此断言没有证书 |
| 首页 HTTP 404 / 410 | 本轮跳过 | homepage_missing；保留检查时间，不永久删除 |
| 标题 / H1 明确出售或停放，且可见文字少于 1,200 字符 | 本轮跳过 | parking_page；规则命中仍可能需要人工纠正 |
| 标题 / H1 完整匹配 Coming soon、Under construction、Nginx 默认页等，且可见文字少于 800 字符 | 本轮跳过 | placeholder_page；文章提到 coming soon 不构成此规则 |
| 标题 / H1 完整匹配 404 / Page not found 等 | 本轮跳过 | soft_404；启发式判断 |
| 非 HTML 内容类型 | 本轮跳过 | non_html；本轮只从网页 HTML 提词，不代表 PDF 等内容没有价值 |
| 可见文字少于 160 字符 | 待复查 | 含 script 为 javascript_or_thin，否则 thin_or_empty；短小但有效的工具也可能落入此类 |
| 403 / 401、人机验证、禁止抓取、跨站跳转或 HTTPS 降级 | 待复查 | 分别记录，不当作空站或垃圾站 |
| HTML 有至少 160 字符可见文字，且标题 / H1 / description 至少一个有值，未命中前述规则 | 进入后续关键词提取 | html_with_content；仅技术及内容初筛通过，不是商业价值认证 |

description 缺失不会单独淘汰。不执行 JavaScript，不下载图片、CSS、脚本资源，也不查询 RDAP、Google 或 Trends。已有 HTML 同时保留 title、description、H1 和可见文字节选；下一步据网页内容确定关键词，不能仅据域名猜词。具体正则见包内 `scripts/probe_prescreen.py`。

## 试跑范围与速率

- 来源仍是 2026-08-27 至 2026-09-25 的历史名单，不是最新月份的新增域名。输入 `site/roots-data.json` 的 SHA-256、名单日期和原始行号随队列保存。
- 从 16,090 个名称命中中，按用户提供的 51 词根顺序轮流取样；每个词根内部按 SHA-256(domain) 排序，全局域名去重，共 100 个。是控制试跑预算的抽样，不是价值排序，其余域名没有被淘汰。
- 串行执行；请求起始时间全局至少间隔 2 秒，同一主机至少 5 秒。curl 传输最多 8 秒，含 DNS 的请求期限 15 秒；解压后响应体上限 512 KiB。最多跟随 2 次跳转，仅原域名和其 www 主机、HTTPS、默认端口，拒绝内网和保留地址。www 跳转也须核验目标主机 robots.txt。
- 不自动重试。任一 429 立即保存并暂停整批，保留 Retry-After；连续 3 个阻挡 / 验证页面或 10 个网络 / TLS 失败也暂停。再次执行同一命令不会自动恢复暂停的批次，应先检查原因。
- robots.txt 404/410 按不存在处理，其他失败暂缓。标准库仅解析普通规则；含通配符 / 末尾锚点的复杂 Allow / Disallow，或要求更慢速率的规则，暂缓人工核验，避免不完整解析后继续抓取。这是试跑版的覆盖限制。
- 这些是保守的试跑参数，不能保证任何平台都不限制 AWS IP。脚本不轮换 IP、不绕过验证。

## 本地准备（离线）

已有队列在 `data/runs/2026-09-28-prescreen/queue.json`。重建需要新的空输出目录：

```sh
python3 -B scripts/probe_prescreen.py prepare --input site/roots-data.json --output data/runs/新的预筛目录 --limit 100
```

`prepare` 和不带 `--execute` 的 `run` 都不联网。网络执行仅开放给 Linux，避免在当前 macOS 上误跑；这不是网络出口自动认证。

## 在 Lightsail Linux 上执行

下载网站提供的 `lightsail-prescreen-pilot.tar.gz`，传到服务器后解压。包内只有两个 Python 脚本、100 条候选及这份说明；无需上传 1.3 GB 名单、浏览器 Cookie 或本地代理配置。

前提是 Python 3.10+、curl 和可用的系统 CA 证书。先确认运行位置是 Lightsail，出站路由使用服务器公网出口。本地 SSH 连接经过代理，不等于远端 HTTP 请求也经过该代理。脚本拒绝 HTTP_PROXY / HTTPS_PROXY / ALL_PROXY 环境变量，curl 忽略 .curlrc 并禁用显式代理，但无法证明系统没有 TUN / VPN 路由。

先预览队列（仍不联网）：

```sh
python3 -B scripts/probe_prescreen.py run --input queue.json --output results --limit 100
```

以下命令才会实际联网，仅在 Lightsail 上运行：

```sh
python3 -B scripts/probe_prescreen.py run --input queue.json --output results --limit 100 --execute
```

每个域名完成即保存；普通中断后重复命令会跳过已完成项，同一输出目录不允许并行写入。recheck 项也算已完成检查，不自动重试。队列或规则改变须用新目录；JSONL 损坏或截断会报错，保留原文件，不悄悄丢弃行。

结果在 `results/summary.json`、`results/results.jsonl` 和 `results/evidence/`。每条包含时间、来源、各请求状态、curl 错误码、原因、HTML 字段和成功响应体 SHA-256；成功取得的响应体压缩留存用于复核。传回完整 results 目录后，可据实际结果接入工作台；当前页面不冒充已经收到服务器结果。

## 核验边界与依据

已做离线模拟测试，覆盖 TLS / DNS 失败、429 暂停、robots、跨站 / www 跳转、停放页与短页的区分、元数据提取和本地执行保护。**没有服务器实际采集结果，也未验证其真实网络环境。**

- curl 默认验证证书签名与 URL 主机名；验证失败还可能来自 CA 配置等原因：[curl TLS Certificate Verification](https://curl.se/docs/sslcerts.html)。
- robots.txt 具有主机、协议和端口范围：[Google robots.txt specification](https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec)。本脚本是保守试跑实现，不宣称完整复刻 Googlebot。

证书存在不能证明已正式上线；预筛通过不能证明最近才上线；有网页关键词也不能证明它最近30天刚起量。最终目标仍须单独用真实趋势数据核验。
