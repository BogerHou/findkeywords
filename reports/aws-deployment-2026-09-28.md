# AWS 运行与结果核查

本轮采集迁移到 AWS Lightsail，运行用户为 `admin`，项目目录为 `/home/admin/findkeywords`。本地电脑只控制远程终端、接收结果和展示工作台，不请求候选域名。实际出口在服务器上通过 `https://checkip.amazonaws.com` 检查；未设置 HTTP/HTTPS/ALL_PROXY 环境变量。

部署版本：GitHub 提交 `e5acea3322c3edb671afcdd14787c6d265e229d4`。服务器无 Git，使用 GitHub 的固定提交源码压缩包部署，未安装额外 Python 依赖。Python 3.11.2、系统 curl；服务器上的 19 项预筛测试和 5 项成本筛选测试全部通过。

## 实测结果

100 个全部完成，未触发整批暂停：20 个有网页内容，1 个首页不存在，79 个待复查。其中20个是自动技术判定。复核已保存字段，纠正3个明显误收：aimicroprocessor.com（售卖域名）、myaiinterpreter.com（Launching Soon）、yellowtemplate.site（Lorem ipsum模板）。余下17个仍需内容及关键词复核，不是已验证的关键词机会。原始自动判定不改写，纠正记录单独保存在 `site/prescreen-review.json`。

保存的解码后响应体合计 1,579,182 字节（约 1.51 MiB），不是网卡计费流量，不含 DNS、TLS、HTTP 响应头及被截断时额外读取的数据。部署源码压缩包另约 6.9 MiB。这些下载和候选站请求均发生在 AWS。

原始 JSONL、运行清单、完整响应体留在服务器。通过浏览器 SSH 导出紧凑快照，保留逐站字段、请求状态和原始 JSONL 的校验值；回传后再核对导出文件的 SHA-256，不把紧凑快照冒充完整原始采集文件。

## 连接方式

本次通过 Lightsail 控制台的“使用 SSH 连接”登录成功。本地 SSH（直接连接及现有代理路径）在 SSH banner/密钥交换前关闭，尚未确定具体网络原因；这不是已证实的用户名或密钥错误。未修改服务器防火墙、SSH 认证规则或本机代理设置。

私钥仅保存在本地，被 `.gitignore` 排除，未上传到 GitHub 或服务器。服务器仅存放自身的运行配置，`config/network.local.json` 不随 Git 共享。

## 本批范围

- 队列：`site/prescreen-queue.json`，100 个域名，80 优先池＋20 探索池。
- 队列 SHA-256：`baaea472f129461aede75a35ecbd409e33fa982117c91e486fef483fb5dfd33b`。
- 输出目录：`/home/admin/findkeywords/results/aws-pilot-01`。
- 单并发、全局请求起始间隔至少 2 秒、同主机至少 5 秒；首页最多读取 128 KiB、robots 最多读取 32 KiB。
- 只请求 HTTPS robots 与首页，验证证书，不执行 JavaScript，不下载图片，不查 RDAP 或 Google Trends。
- 429、连续拦截或连续网络失败会暂停；失败、超限、复杂 robots 和页面过薄保留待复查，不自动补抓。

输入仍是 2026-08-27 至 2026-09-25 的历史域名名单。本批不能证明站点最近上线，也不能证明关键词最近30天刚起量。

本地回传导出 SHA-256：`9cac6ba535c0030566689f3d2f5ee7416790eb51a9c80a97782fa87750161755`，与服务器一致。原始结果 JSONL SHA-256：`c01b9fad8ecb14e4625f56cad6a58ba7f63af2c42bc9770d89ee8da99372dde2`。队列域名及顺序逐项核对，100/100匹配，80优先＋20探索。

记录了149次HTTP尝试，另1条超时调用未记下请求次数；DNS失败可在HTTP前结束，因此域名数量不等于连接数量。

## 服务器命令

以下命令仅在服务器执行。`network-init` 已初始化一次，无需重复。`run` 不带 `--execute` 时只做离线预览。

```sh
cd /home/admin/findkeywords
python3 -B scripts/probe_prescreen.py run --input site/prescreen-queue.json --output results/aws-pilot-01 --limit 100
tail -n 12 results/aws-pilot-01/process.log
cat results/aws-pilot-01/summary.json
```

本次后台启动方式（已经启动，不要重复启动）：

```sh
nohup python3 -B scripts/probe_prescreen.py run --input site/prescreen-queue.json --output results/aws-pilot-01 --limit 100 --execute > results/aws-pilot-01/process.log 2>&1 < /dev/null &
```

程序逐条保存并同步写盘。`summary.json` 在任务正常结束或按规则暂停后生成；运行中以 `results.jsonl` 和日志为准。`run.json` 保存策略及队列校验值，`evidence/*.gz` 保存实际响应体及 SHA-256，原始页面不执行。

结果复制回本地后，可离线更新工作台：

```sh
python3 -B scripts/build_prescreen_site.py --input results/aws-pilot-01/export.json
python3 scripts/serve_site.py
```

网页只展示已保存快照，不会因打开网页而抓取。查看本批结果和逐域名证据，确认下一批策略后再启动新的批次；没有配置自动全量或定时抓取。
