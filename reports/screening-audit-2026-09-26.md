**2026-09-26 试跑：域名名称筛选审计说明**

本次复算确认，140,000 → 1,210 是一套固定英文词根和字符规则的结果；1,210 → 52 是 AI 的主观目的选样。前一步可以逐条复算，后一步没有足够的评分和淘汰记录来重演。此前只说“名称初筛”和“人工挑选”，没有交代这些限制，表述不够准确。

本文依据已有脚本、原始名单、入选名单和来源记录，说明实际发生的筛选，不补造当时没有记录的标准。机器可读复算结果、逐词命中数量、排除实例及证据文件 SHA-256 均在 [筛选审计数据](screening-audit-data-2026-09-26.json)。

**14 万个域名来自哪里**

两份 WhoisDS 免费每日名单分别标记为 2026-09-22 和 2026-09-25，各 70,000 行；离线复算得到 140,000 个不重复域名。这是本次下载的两份名单，不能当成全球新域名全集。原始文件为 [09-22 TXT](../data/raw/whoisds-2026-09-22.txt) 和 [09-25 TXT](../data/raw/whoisds-2026-09-25.txt)，下载来源与 ZIP 校验值记录在 [provenance.json](../data/runs/2026-09-26/provenance.json) 第 2–18 行。

这批入口是 WhoisDS 名单，不是从 SSL/证书透明度日志获得的名单。文件日期表示来源批次日期，并不证明每个域名当天注册。只有后续挑出的 52 个进行了注册时间查询和网页探测；没有先把全部 14 万个逐一核验为新注册域名，也没有先抓取这 14 万个网站。此范围在 provenance.json 第 22–34 行已有记录。

**1,210 的实际筛选条件**

脚本 [screen_names.py](../scripts/screen_names.py) 第 8–12 行定义了以下全部 43 个词根：

```text
calculator converter generator checker tracker planner invoice subtitle
transcript compress resize remove background pdf csv json markdown diagram audio
video image photo prompt agent schema recipe itinerary resume flashcard chord sheet
font palette mockup watermark screenshot timezone pronunciation worksheet timer
countdown qr barcode
```

第 24–30 行的实际操作是：去除行首尾空白并转为小写；取 `domain.split(".")[0]`，即第一个点号之前的标签；然后同时满足以下三个条件才保留：

1. 标签中包含 43 个词根中的至少一个，使用普通子串判断 `term in name`。
2. 标签长度 `< 34`，即 1–33 个字符。
3. 标签中没有连续三个数字，使用 `not re.search(r"\d{3}", name)`。

多个词根之间是 OR；三个条件之间是 AND。保留后的域名加入去重集合，后续相同域名不再重复输出；这两份名单没有重复项，因此去重对本次数字无影响。

这没有使用完整词边界、域名分词、语义模型、语言识别、网页内容、流量、竞争度或数值评分，也没有解析公共后缀。连字符仍按字符计数。规则并非禁止所有数字，例如 `3dcalculators.com` 可以通过。

43 词根、34 字符阈值和连续三位数字规则，都是本轮试跑临时采用的启发式条件。现有材料没有提供它们经统计验证的依据，也没有表明这是用户认可的筛选标准。它们偏向工具和 AI 相关名称，会直接漏掉不含这些已知词根的新词。

**逐级数量如何减少**

下表按“子串 → 长度 → 数字”顺序分解同一组 AND 条件；排除数互不重叠。

| 步骤 | 本步保留 | 本步排除 | 实际含义 |
| --- | ---: | ---: | --- |
| 原始名单合并去重 | 140,000 | 0 个重复项 | 两批各 70,000 |
| 含至少一个词根 | 1,224 | 138,776 | 其余名称不含这 43 个子串 |
| 第一个标签长度 < 34 | 1,221 | 3 | 只在上一行的 1,224 个中检查 |
| 无连续三个数字 | 1,210 | 11 | 只在上一行的 1,221 个中检查 |

最终保留率为 0.8643%。绝大部分减少发生在第一道词根白名单，不是对 14 万个名称逐一判断“有意义/无意义”的结果。因此不能把“只筛出 1,210 个”理解为“14 万个中只有 1,210 个有意义”。

| 来源批次 | 原始行数 | 词根命中 | 长度通过 | 数字检查通过 |
| --- | ---: | ---: | ---: | ---: |
| 2026-09-22 | 70,000 | 696 | 695 | 690 |
| 2026-09-25 | 70,000 | 528 | 526 | 520 |
| 合计 | 140,000 | 1,224 | 1,221 | 1,210 |

复算的 1,210 条内容和顺序，与 [name_matches.json](../data/runs/2026-09-26/name_matches.json) 完全一致。逐词根命中数量在审计 JSON 中；一个域名可以命中多个词根，不能把这些词根计数相加当作域名总数。

**能够通过但不能据此认定有意义的例子**

下表只检查名称和字符串规则，未验证这些网站的业务、真实性、流量或价值。行号对应原始 TXT 文件。

| 域名 | 命中词根 | 规则局限 | 原始来源位置 |
| --- | --- | --- | --- |
| `87wqr2a.top` | qr | 命中 qr，但名称整体像字母数字串；仅凭名称不能确认二维码需求。 | [2026-09-22 TXT](../data/raw/whoisds-2026-09-22.txt) 第 16 行 |
| `iskreldpapdf.shop` | pdf | 命中 pdf，但其余部分难辨含义；仅凭名称不能确认 PDF 工具。 | [2026-09-22 TXT](../data/raw/whoisds-2026-09-22.txt) 第 361 行 |
| `grandirafontenay.fr` | font | font 出现在 fontenay 内部，并未按完整词匹配；不能据此推断字体需求。 | [2026-09-22 TXT](../data/raw/whoisds-2026-09-22.txt) 第 10363 行 |
| `springanchordevelopment.de` | chord | chord 跨 anchor 与 development 的连接处出现；不能据此推断和弦需求。 | [2026-09-22 TXT](../data/raw/whoisds-2026-09-22.txt) 第 41621 行 |
| `magento-replatforming-agencies.com` | agent | agent 是 magento 的内部子串；名称指向 Magento 相关线索，不能据此推断 AI 智能体。 | [2026-09-25 TXT](../data/raw/whoisds-2026-09-25.txt) 第 148 行 |

**名称可读但被直接排除的例子**

以下只是名称层面的需求线索，不代表已经确认有商业机会。它们均未命中 43 个词根，没有进入 1,210 个候选池，更没有进入后续 52 个挑选的比较范围。

| 域名 | 名称层面的线索 | 排除原因 | 原始来源位置 |
| --- | --- | --- | --- |
| `personal-budget.app` | personal budget 可读作个人预算，是名称层面的需求线索。 | 没有词根命中。 | [2026-09-22 TXT](../data/raw/whoisds-2026-09-22.txt) 第 11132 行 |
| `taxriskcheck.com` | tax risk check 可读作税务风险检查，是名称层面的需求线索。 | 没有词根命中；词表有 checker，但没有 check。 | [2026-09-22 TXT](../data/raw/whoisds-2026-09-22.txt) 第 213 行 |
| `learnformalverification.com` | learn formal verification 可读作学习形式化验证，是名称层面的需求线索。 | 没有词根命中。 | [2026-09-22 TXT](../data/raw/whoisds-2026-09-22.txt) 第 3860 行 |
| `smartflowbookingai.com` | booking / AI 是可辨识名称片段，存在预约类线索。 | 没有词根命中。 | [2026-09-22 TXT](../data/raw/whoisds-2026-09-22.txt) 第 7338 行 |
| `insoft-booking.com` | booking 是可辨识名称片段，存在预约类线索。 | 没有词根命中。 | [2026-09-22 TXT](../data/raw/whoisds-2026-09-22.txt) 第 3805 行 |

另外两个字符规则也会排除可读名称。例如 `magento-platform-migration-agencies.com` 因第一个标签长 35 个字符被排除；`calculator100.com` 因 `100` 连续三位数字被排除。全部 3 个长度排除项和 11 个数字排除项见审计 JSON 的 `length_exclusions`、`numeric_exclusions`。

**52 个是怎样挑出的**

“人工挑选”应更准确地改为“AI 根据名称作主观目的选样”。不是用户或另一位人类逐条选出了这 52 个，也不是某个可复算排序算法的前 52 名。`provenance.json` 第 21 行写明 `not random or representative`，第 34 行也写明“有目的选样”。

保存名单实际分成两组：

| 原始组名 | 本次含义 | 09-22 批次 | 09-25 批次 | 合计 |
| --- | --- | ---: | ---: | ---: |
| readable_task | AI 认为名称可能指向可辨识的工具、软件或资料需求 | 20 | 20 | 40 |
| emerging_concept | AI 认为名称可能包含值得查看的新概念线索 | 4 | 8 | 12 |
| 合计 | 两组均来自相同的 1,210 个词根命中池 | 24 | 28 | 52 |

这是最终文件的实际构成，不能仅据此推断当时事先规定了 20 + 20 + 12 的严格配额。`emerging_concept` 是当时赋予的分组标签，不证明该概念确实新出现。

40 个 `readable_task` 的原始 `selection_reason` 完全相同：“人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证”。这句话只记录了一项笼统判断，没有记录每个域名与其他候选相比为何应当入选。12 个 `emerging_concept` 各有一个命名推测，原文均注明“具体业务待网页验证”。

现有保存材料没有 1,210 个候选的统一评分、完整排序、截止阈值、随机种子，也没有其余 1,158 个未入选域名的逐条淘汰理由。因此，可以确认这 52 个确实来自候选池、没有重复，并核对保存的理由；不能复算出“为什么恰好这 52 个、为什么优于另外 1,158 个”。不能据此声称剩余域名没有价值，或这 52 个是最佳机会。

**完整 52 条原始选择记录**

以下按 [selected_domains.json](../data/runs/2026-09-26/selected_domains.json) 原顺序列出，理由逐字保留。表中“人工复核”是原始字段用语；实际执行者是 AI。第一组 40 条共用理由，不具有个别域名之间的区别。原始行号指向每条记录的 `domain` 字段，组别及理由在紧随其后的同一对象中。

| 序号 | 域名 | 来源日期 | 组别 | 命中词根 | 原始 selection_reason | 原始 JSON 行号 |
| ---: | --- | --- | --- | --- | --- | ---: |
| 1 | `thetimezonemap.com` | 2026-09-22 | readable_task | timezone | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 3 |
| 2 | `getkitchenconverter.com` | 2026-09-22 | readable_task | converter | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 13 |
| 3 | `colorpaletteextractor.com` | 2026-09-22 | readable_task | palette | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 23 |
| 4 | `pdfconverter.dev` | 2026-09-22 | readable_task | converter, pdf | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 33 |
| 5 | `photoimageresizer.net` | 2026-09-22 | readable_task | resize, image, photo | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 44 |
| 6 | `chordhunter.ai` | 2026-09-22 | readable_task | chord | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 56 |
| 7 | `recipereel.app` | 2026-09-22 | readable_task | recipe | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 66 |
| 8 | `promptgenerator.fyi` | 2026-09-22 | readable_task | generator, prompt | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 76 |
| 9 | `movieshotplanner.tools` | 2026-09-22 | readable_task | planner | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 87 |
| 10 | `aestheticpomodorotimer.com` | 2026-09-22 | readable_task | timer | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 97 |
| 11 | `myphotoeditor.app` | 2026-09-22 | readable_task | photo | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 107 |
| 12 | `reelsplanner.com` | 2026-09-22 | readable_task | planner | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 117 |
| 13 | `freeinvoicegenerator.info` | 2026-09-22 | readable_task | generator, invoice | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 127 |
| 14 | `barcodescanning.net` | 2026-09-22 | readable_task | barcode | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 138 |
| 15 | `3dcalculators.com` | 2026-09-22 | readable_task | calculator | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 148 |
| 16 | `socialimagekit.com` | 2026-09-22 | readable_task | image | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 158 |
| 17 | `pdf-doctor-lab.com` | 2026-09-22 | readable_task | pdf | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 168 |
| 18 | `qrswitcher.com` | 2026-09-22 | readable_task | qr | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 178 |
| 19 | `resumereef.com` | 2026-09-22 | readable_task | resume | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 188 |
| 20 | `imageremodeler.com` | 2026-09-22 | readable_task | image | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 198 |
| 21 | `spritesheetmaker.net` | 2026-09-25 | readable_task | sheet | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 208 |
| 22 | `ai-translate-video.com` | 2026-09-25 | readable_task | video | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 218 |
| 23 | `ceilingfanplanner.com` | 2026-09-25 | readable_task | planner | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 228 |
| 24 | `petpetgenerator.app` | 2026-09-25 | readable_task | generator | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 238 |
| 25 | `imagescanai.com` | 2026-09-25 | readable_task | image | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 248 |
| 26 | `heicpngconverter.website` | 2026-09-25 | readable_task | converter | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 258 |
| 27 | `image-to-3d.art` | 2026-09-25 | readable_task | image | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 268 |
| 28 | `seedlingspaceplanner.com` | 2026-09-25 | readable_task | planner | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 278 |
| 29 | `mockupmagicstudio.net` | 2026-09-25 | readable_task | mockup | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 288 |
| 30 | `sparktranscript.com` | 2026-09-25 | readable_task | transcript | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 298 |
| 31 | `videoassembler.io` | 2026-09-25 | readable_task | video | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 308 |
| 32 | `shopbuildplanner.com` | 2026-09-25 | readable_task | planner | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 318 |
| 33 | `imagefixkit.com` | 2026-09-25 | readable_task | image | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 328 |
| 34 | `mdtopdf.co` | 2026-09-25 | readable_task | pdf | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 338 |
| 35 | `numberfontsgenerator.com` | 2026-09-25 | readable_task | generator, font | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 348 |
| 36 | `imagecompactor.com` | 2026-09-25 | readable_task | image | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 359 |
| 37 | `imagecompressed.com` | 2026-09-25 | readable_task | compress, image | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 369 |
| 38 | `promptfirst.app` | 2026-09-25 | readable_task | prompt | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 380 |
| 39 | `resumealgo.com` | 2026-09-25 | readable_task | resume | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 390 |
| 40 | `friendlypdf.com` | 2026-09-25 | readable_task | pdf | 人工复核域名名称：可辨识的工具、软件或资料需求；具体业务待页面验证 | 400 |
| 41 | `agentpermissionmatrix.com` | 2026-09-25 | emerging_concept | agent | 智能体权限矩阵；仅域名命名推测，具体业务待网页验证 | 410 |
| 42 | `agentaccessguard.com` | 2026-09-25 | emerging_concept | agent | 智能体访问控制；仅域名命名推测，具体业务待网页验证 | 420 |
| 43 | `agentgovernancecloud.com` | 2026-09-25 | emerging_concept | agent | 智能体治理；仅域名命名推测，具体业务待网页验证 | 430 |
| 44 | `agentconfinement.co` | 2026-09-22 | emerging_concept | agent | 智能体隔离/限制含义待查；仅域名命名推测，具体业务待网页验证 | 440 |
| 45 | `agentcounterparty.com` | 2026-09-25 | emerging_concept | agent | 智能体交易对手含义待查；仅域名命名推测，具体业务待网页验证 | 450 |
| 46 | `museagenticpayments.com` | 2026-09-25 | emerging_concept | agent | 智能体支付；仅域名命名推测，具体业务待网页验证 | 460 |
| 47 | `emailforagents.ai` | 2026-09-22 | emerging_concept | agent | 面向智能体的邮箱；仅域名命名推测，具体业务待网页验证 | 470 |
| 48 | `agentopsdispatch.com` | 2026-09-25 | emerging_concept | agent | 智能体运维调度；仅域名命名推测，具体业务待网页验证 | 480 |
| 49 | `claudeskillsagent.com` | 2026-09-25 | emerging_concept | agent | 模型生态skills相关线索；仅域名命名推测，具体业务待网页验证 | 490 |
| 50 | `mcpaudio.com` | 2026-09-25 | emerging_concept | audio | MCP与音频，缩写含义待查；仅域名命名推测，具体业务待网页验证 | 500 |
| 51 | `qwenimage.com.cn` | 2026-09-22 | emerging_concept | image | 模型与图片相关线索；仅域名命名推测，具体业务待网页验证 | 510 |
| 52 | `agent-mpp.io` | 2026-09-22 | emerging_concept | agent | 陌生缩写MPP，含义待查；仅域名命名推测，具体业务待网页验证 | 520 |

**如何独立复算名称初筛**

在项目根目录 `/Users/simon/Documents/code/findkeywords` 执行下面的命令。输出写入临时目录，不覆盖原始结果。

```bash
python3 scripts/screen_names.py \
  data/raw/whoisds-2026-09-22.txt \
  data/raw/whoisds-2026-09-25.txt \
  --output /tmp/findkeywords-name-matches-audit.json

python3 - <<'PY'
import json
from pathlib import Path
actual = json.loads(Path('/tmp/findkeywords-name-matches-audit.json').read_text())
saved = json.loads(Path('data/runs/2026-09-26/name_matches.json').read_text())
print('复算条数:', len(actual))
print('与保存结果内容和顺序完全一致:', actual == saved)
PY
```

预期为 `复算条数: 1210` 和 `与保存结果内容和顺序完全一致: True`。

若要复算逐级数量，下面代码直接读取脚本中的同一词根表：

```bash
python3 - <<'PY'
import re
import runpy
from pathlib import Path
terms = runpy.run_path('scripts/screen_names.py')['TERMS']
seen = set()
for date in ('2026-09-22', '2026-09-25'):
    rows = Path(f'data/raw/whoisds-{date}.txt').read_text(encoding='utf-8-sig').splitlines()
    domains = [x.strip().lower() for x in rows if x.strip()]
    names = [d.split('.')[0] for d in domains]
    matched = [n for n in names if any(t in n for t in terms)]
    short = [n for n in matched if len(n) < 34]
    accepted = [n for n in short if not re.search(r'\d{3}', n)]
    print(date, '原始/词根/长度/数字:', len(domains), len(matched), len(short), len(accepted))
    seen.update(domains)
print('两批不重复域名:', len(seen))
PY
```

预期分别输出 `70000 696 695 690`、`70000 528 526 520`，不重复域名数为 `140000`。这些命令可以验证固定名称规则；不能重建未记录的主观选样过程。

本文仅审计域名来源、名称初筛和 52 个样本的选择记录，不包含 Google Trends 查询核验；Trends 的实际页面条件、观察和证据另行说明。
