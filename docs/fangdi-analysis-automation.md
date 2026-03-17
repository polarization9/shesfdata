# Fangdi 数据分析与自动化方案

这份文档基于当前已经跑通的链路来设计：

- 腾讯云服务器上的真人浏览器会话
- Fangdi 查询页 userscript
- 本地 OCR 服务 `scripts/ocr_http_service.py`
- 结果落盘 `fangdi-count-results.jsonl`
- 区 / 板块字典导出与全量查询计划生成

目标不是只做一个 PoC，而是把它整理成一条可以持续产出内容的日常流水线。

## 1. 当前已经能拿到什么数据

当前这条链路每跑完一条查询，至少能拿到：

- `task_id`
- `district`
- `plate`
- `listing_age`
- `count`
- `status`
- `captcha_guess`
- `captcha_attempt`
- `page_url`
- `recorded_at`

如果查询成功，`page_url` 里通常还能拿到：

- `RecordCount`
- `PageCount`

因此，当前可稳定沉淀的数据本质上是：

- 日期
- 区
- 板块
- 挂牌时间分桶
- 对应挂牌总量
- 查询是否成功

这是一套“挂牌供给观察”数据，不是成交价、成交量或去化周期的完整数据。

## 2. 第一天没有历史数据时，能做什么分析

即使今天是第一天，没有环比和趋势，也已经足够做一批有价值的内容。

### 2.1 绝对量分析

可直接算：

- 各区挂牌总量
- 各板块挂牌总量
- 各区各挂牌时间分桶总量
- 各板块各挂牌时间分桶总量

最直接的内容形式：

- “上海哪些区当前挂牌量最多”
- “各区挂牌库存分布图”
- “哪些板块目前库存盘子最大”

### 2.2 结构分析

把 4 个挂牌时间桶看成库存年龄结构：

- `15天`
- `1个月`
- `3个月`
- `3个月以上`

可直接计算：

- `total_count`
- `fresh_ratio = 15天 / total_count`
- `mid_ratio = (1个月 + 3个月) / total_count`
- `stale_ratio = 3个月以上 / total_count`

最直接的内容形式：

- “哪些板块长挂盘压力最大”
- “哪些区新挂牌占比更高”
- “哪些地方库存结构更偏老”

### 2.3 风险提示型内容

第一天就可以做：

- 数据覆盖度说明
- 哪些区 / 板块有效样本多
- 哪些区 / 板块存在失败查询或异常值

这类内容不一定直接发帖，但适合做数据质量注释，避免后面误读。

## 3. 有历史数据之后，分析如何升级

从第 2 天开始，就可以做变化类指标。

### 3.1 日变化

按 `district / plate / listing_age` 维度计算：

- `delta_1d = 今日 - 昨日`
- `delta_1d_pct = (今日 - 昨日) / 昨日`

对应内容：

- “今天哪些板块挂牌突然增加”
- “哪些区新上盘明显增多”

### 3.2 7 日变化

从累计到第 7 天开始，可以做：

- `delta_7d`
- `delta_7d_pct`

对应内容：

- “一周库存增长最快板块”
- “一周长挂盘增幅最大的区域”

### 3.3 结构变化

重点看比例，不只看总量：

- `fresh_ratio_delta_1d`
- `stale_ratio_delta_1d`
- `fresh_ratio_delta_7d`
- `stale_ratio_delta_7d`

对应内容：

- “哪些板块短期新增挂牌正在增加”
- “哪些板块长挂盘堆积在加重”

### 3.4 异常波动

随着历史数据积累，可以做简单异常检测：

- 同板块日变化超过过去 7 日平均波动 2 倍
- 同区多个板块同日同步上升
- 某个挂牌时间桶单独异常跳增

对应内容：

- “今天最异常的 5 个板块”
- “供给突然松动的板块有哪些”

## 4. 建议采用的数据表结构

建议把数据拆成 4 层，不要只保留原始 JSONL。

### 4.1 原始采集表

建议文件：

- `data/raw/fangdi/2026-03-17/results.jsonl`

字段建议：

- `run_date`
- `recorded_at`
- `task_id`
- `district`
- `plate`
- `listing_age`
- `count`
- `page_count`
- `status`
- `captcha_guess`
- `captcha_attempt`
- `page_url`
- `error`

### 4.2 日标准化明细表

建议文件：

- `data/normalized/fangdi_daily_counts_2026-03-17.csv`

每行一条：

- `date`
- `district`
- `plate`
- `listing_age`
- `count`
- `page_count`
- `status`

### 4.3 板块指标表

建议文件：

- `data/metrics/fangdi_plate_metrics_2026-03-17.csv`

每行一个 `district + plate`：

- `date`
- `district`
- `plate`
- `count_15d`
- `count_1m`
- `count_3m`
- `count_3m_plus`
- `total_count`
- `fresh_ratio`
- `mid_ratio`
- `stale_ratio`

### 4.4 区级指标表

建议文件：

- `data/metrics/fangdi_district_metrics_2026-03-17.csv`

每行一个区：

- `date`
- `district`
- `count_15d`
- `count_1m`
- `count_3m`
- `count_3m_plus`
- `total_count`
- `fresh_ratio`
- `stale_ratio`
- `plate_count`

## 5. 首批建议落地的分析指标

第一版不要一口气上很多模型，先把这几项固定好。

### 5.1 板块级指标

- `total_count`
- `count_15d`
- `count_1m`
- `count_3m`
- `count_3m_plus`
- `fresh_ratio`
- `stale_ratio`

### 5.2 区级指标

- `total_count`
- `fresh_ratio`
- `stale_ratio`
- `top_plate_by_total_count`
- `top_plate_by_stale_ratio`

### 5.3 历史积累后补充

- `delta_1d`
- `delta_7d`
- `fresh_delta_1d`
- `stale_delta_1d`
- `fresh_ratio_delta_1d`
- `stale_ratio_delta_1d`

## 6. 每天输出什么内容包

目标不是只留一堆表，而是每天自动生成一套可发内容。

建议固定输出目录：

- `output/fangdi/2026-03-17/`

里面放：

- `raw-results.jsonl`
- `daily-counts.csv`
- `plate-metrics.csv`
- `district-metrics.csv`
- `insights.json`
- `cards/01-overview.png`
- `cards/02-district-ranking.png`
- `cards/03-stale-pressure.png`
- `cards/04-fresh-activity.png`
- `caption_draft.md`
- `headline_candidates.md`

## 7. 首日适合发的内容结构

第一天没有历史对比，不代表没内容。

建议做 4 张图：

### 7.1 全市概览

内容：

- 总抓取任务数
- 成功任务数
- 覆盖区数
- 覆盖板块数
- 全市挂牌总量

### 7.2 各区挂牌总量排名

内容：

- 各区总挂牌量 Top N

### 7.3 长挂压力排名

内容：

- 按 `3个月以上占比` 排序的区或板块 Top N

### 7.4 新挂牌活跃度

内容：

- 按 `15天占比` 排序的区或板块 Top N

对应文案风格建议：

- 不说“房价涨跌”
- 聚焦“挂牌供给变化”“库存年龄结构”“买方议价环境”

## 8. 有历史数据后适合发的内容结构

### 8.1 日报

每日固定：

- 哪些区总量变化最大
- 哪些板块新增供给明显
- 哪些板块长挂压力加重
- 今日异常板块

### 8.2 周报

每周固定：

- 一周库存增长最快区
- 一周库存压力上升最快板块
- 一周新挂牌最活跃板块
- 一周长挂盘占比上升板块

## 9. 自动化总体架构

建议把整条链路拆成 5 个模块。

### 9.1 浏览器会话模块

职责：

- 腾讯云远程桌面的 Firefox 常驻
- 每天人工解锁一次 Fangdi
- userscript 自动执行全量查询

现实边界：

- 完全无人值守不现实
- 但可以把人工压缩到每天 1 次解锁

### 9.2 OCR / 结果服务模块

现有脚本：

- `scripts/ocr_http_service.py`
- `scripts/fangdi_ocr_lib.py`

职责：

- 识别验证码
- 记录查询结果

### 9.3 数据标准化模块

建议新增脚本：

- `scripts/normalize_fangdi_results.py`

职责：

- 把原始 JSONL 转成标准化日明细表
- 把成功记录与失败记录拆开
- 从 `page_url` 里提取 `RecordCount / PageCount`

### 9.4 指标计算模块

建议新增脚本：

- `scripts/analyze_fangdi_daily.py`
- `scripts/analyze_fangdi_history.py`

职责：

- 生成区级和板块级指标表
- 产出 `insights.json`
- 后续加入历史对比

历史对比脚本建议额外负责：

- 自动扫描历史 `fangdi_plate_metrics_*.csv`
- 自动扫描历史 `fangdi_district_metrics_*.csv`
- 自动找到最近一次可用快照做 `1日对比`
- 自动找到可用的 `7日前` 快照做 `7日对比`
- 输出增强后的历史对比表和 `history_summary.json`

### 9.5 内容包生成模块

建议新增脚本：

- `scripts/render_fangdi_cards.py`
- `scripts/render_fangdi_caption.py`

职责：

- 生成图表 PNG
- 输出标题候选
- 输出小红书文案草稿

## 10. OpenClaw 在这条链路里的角色

OpenClaw 更适合当调度器，而不是爬虫本体。

建议由 OpenClaw 负责：

- 检查 OCR 服务是否存活
- 检查浏览器会话是否可用
- 每天定时提醒你人工解锁
- 解锁后触发跑数
- 跑数完成后触发标准化与分析
- 最后通知你内容包已生成

不建议让 OpenClaw 直接承担：

- 页面内控件点击
- 验证码识别细节
- 浏览器内状态恢复

这些已经由 userscript 和 OCR 服务承担。

## 11. 每天的自动化运行流程

建议固定为下面这条链路。

### 11.1 开始前检查

由 OpenClaw 定时执行：

- OCR 服务健康检查
- 浏览器进程检查
- userscript 文件是否为最新
- 输出目录是否已准备好

### 11.2 人工解锁

你每天只做一次：

- 远程连接腾讯云
- 打开 Fangdi 查询页
- 完成 challenge / 解锁
- 确认可查
- 点 userscript 的 `重置`
- 点 `开始`

### 11.3 自动跑数

userscript 执行：

- 按 `district x plate x listing_age` 计划跑
- 失败时按验证码策略重试
- 结果写入 JSONL

### 11.4 自动收尾

OpenClaw 轮询判断：

- 结果文件是否停止增长
- 计划中的任务是否完成

完成后自动调用：

- `normalize_fangdi_results.py`
- `analyze_fangdi_daily.py`
- `render_fangdi_cards.py`
- `render_fangdi_caption.py`

### 11.5 产出通知

OpenClaw 最后通知：

- 今日跑数是否完成
- 成功率
- 内容包输出目录

## 12. 建议的目录结构

建议统一成下面这种结构：

```text
data/
  raw/
    fangdi/
      2026-03-17/
        results.jsonl
  normalized/
    fangdi_daily_counts_2026-03-17.csv
  metrics/
    fangdi_plate_metrics_2026-03-17.csv
    fangdi_district_metrics_2026-03-17.csv
output/
  fangdi/
    2026-03-17/
      insights.json
      caption_draft.md
      headline_candidates.md
      cards/
scripts/
  normalize_fangdi_results.py
  analyze_fangdi_daily.py
  render_fangdi_cards.py
  render_fangdi_caption.py
```

## 13. 建议优先实现的自动化脚本

如果按交付优先级排，我建议顺序是：

### 13.1 第一优先级

- `scripts/normalize_fangdi_results.py`
- `scripts/analyze_fangdi_daily.py`
- `scripts/analyze_fangdi_history.py`

原因：

- 没有这两层，就只有原始 JSONL，没法稳定做后续内容

### 13.2 第二优先级

- `scripts/render_fangdi_cards.py`

原因：

- 先把图稳定生成出来，内容包就能规模化

### 13.3 第三优先级

- `scripts/render_fangdi_caption.py`

原因：

- 文案草稿重要，但优先级低于“数据正确”和“图表稳定”

## 14. 首轮实施建议

现在最合理的推进顺序不是继续折腾采集，而是：

1. 先让全量跑数稳定 2 到 3 天
2. 同时补标准化脚本
3. 再补首日版指标脚本
4. 再补首批 3 到 4 张固定图
5. 最后再把 OpenClaw 调度接上

这样做的原因是：

- 首日没有历史，先把“绝对量 + 结构”做扎实
- 等历史积累到第 2 天、第 7 天，再自然升级成变化分析

## 15. 当前可以直接执行的自动化清单

现在这条链路里，已经可以自动化的部分有：

- OCR 服务启动
- 区 / 板块字典导出
- 全量配置生成
- 查询计划生成
- userscript 全量跑数
- 原始 JSONL 汇总

下一步最值得补的是：

- 日标准化
- 区 / 板块指标表
- 首日内容包输出

## 16. 后续建议

当跑数稳定后，建议再补 3 个增强项：

- 失败任务自动回补队列
- 会话掉线检测与告警
- 每日自动生成简报与卡片

这样这条链路就会从“可跑”变成“可日更”。

## 17. 自动化实现蓝图

如果把自动化真的落到工程实现上，我建议按下面这组脚本和职责拆分。

### 17.1 `scripts/normalize_fangdi_results.py`

输入：

- `data/raw/fangdi/YYYY-MM-DD/results.jsonl`

输出：

- `data/normalized/fangdi_daily_counts_YYYY-MM-DD.csv`
- `data/normalized/fangdi_daily_failures_YYYY-MM-DD.csv`

核心逻辑：

- 只保留每个 `district + plate + listing_age` 最后一条有效成功记录
- 从 `page_url` 补提 `RecordCount / PageCount`
- 保留失败记录供质量分析
- 输出当日成功率摘要

### 17.2 `scripts/analyze_fangdi_daily.py`

输入：

- `data/normalized/fangdi_daily_counts_YYYY-MM-DD.csv`
- 可选历史文件：
  - 昨日标准化表
  - 7 日前标准化表

输出：

- `data/metrics/fangdi_plate_metrics_YYYY-MM-DD.csv`
- `data/metrics/fangdi_district_metrics_YYYY-MM-DD.csv`
- `output/fangdi/YYYY-MM-DD/insights.json`

核心逻辑：

- 聚合出板块级总量与结构
- 聚合出区级总量与结构
- 若有历史，则补 `delta_1d / delta_7d`
- 生成一批可直接用于文案的结论候选

### 17.3 `scripts/analyze_fangdi_history.py`

输入：

- `data/metrics/fangdi_plate_metrics_YYYY-MM-DD.csv`
- `data/metrics/fangdi_district_metrics_YYYY-MM-DD.csv`
- 历史目录中的旧版 `plate_metrics / district_metrics`

输出：

- `data/metrics/fangdi_plate_history_YYYY-MM-DD.csv`
- `data/metrics/fangdi_district_history_YYYY-MM-DD.csv`
- `output/fangdi/YYYY-MM-DD/history_summary.json`

核心逻辑：

- 自动定位最近一日可用快照
- 自动定位最近可用的 7 日前快照
- 输出 `delta_1d / delta_7d`
- 输出 `delta_1d_pct / delta_7d_pct`
- 输出 `fresh_ratio_delta / stale_ratio_delta`
- 输出适合做日报与周报的变化榜单

### 17.4 `scripts/render_fangdi_cards.py`

输入：

- `data/metrics/fangdi_plate_metrics_YYYY-MM-DD.csv`
- `data/metrics/fangdi_district_metrics_YYYY-MM-DD.csv`
- `output/fangdi/YYYY-MM-DD/insights.json`

输出：

- `output/fangdi/YYYY-MM-DD/cards/01-overview.png`
- `output/fangdi/YYYY-MM-DD/cards/02-district-ranking.png`
- `output/fangdi/YYYY-MM-DD/cards/03-stale-pressure.png`
- `output/fangdi/YYYY-MM-DD/cards/04-fresh-activity.png`

核心逻辑：

- 统一图表风格
- 固定导出 3 到 4 张日报卡片
- 数据不足时自动降级，不中断全流程

### 17.5 `scripts/render_fangdi_caption.py`

输入：

- `output/fangdi/YYYY-MM-DD/insights.json`
- `data/metrics/fangdi_plate_metrics_YYYY-MM-DD.csv`
- `data/metrics/fangdi_district_metrics_YYYY-MM-DD.csv`

输出：

- `output/fangdi/YYYY-MM-DD/headline_candidates.md`
- `output/fangdi/YYYY-MM-DD/caption_draft.md`

核心逻辑：

- 根据当天指标生成标题候选
- 生成首日版或历史版文案模板
- 明确写出数据边界，避免把挂牌数据误写成成交结论

## 18. OpenClaw 调度建议

如果后面接 OpenClaw，建议拆成 3 个独立任务，而不是一条超长任务。

### 18.1 任务一：采集前检查

建议执行内容：

- 检查 `ocr_http_service.py` 是否存活
- 检查浏览器进程是否存活
- 检查结果目录是否存在
- 如果 userscript 产物不存在，则直接告警

### 18.2 任务二：采集完成后收尾

触发条件建议：

- 结果文件在一段时间内不再增长
- 或任务计划数达到预期

执行内容：

- 归档原始 `jsonl`
- 调用 `normalize_fangdi_results.py`
- 调用 `analyze_fangdi_daily.py`
- 调用 `analyze_fangdi_history.py`

### 18.3 任务三：内容包生成

执行内容：

- 调用 `render_fangdi_cards.py`
- 调用 `render_fangdi_caption.py`
- 输出内容包目录
- 发通知给你

## 19. 建议的下一步实现顺序

为了最快形成闭环，我建议接下来按这个顺序继续写代码：

1. `scripts/normalize_fangdi_results.py`
2. `scripts/analyze_fangdi_daily.py`
3. `scripts/analyze_fangdi_history.py`
4. `scripts/render_fangdi_cards.py`
5. `scripts/render_fangdi_caption.py`
6. OpenClaw 调度配置

这样做的好处是：

- 先把数据资产固定下来
- 再把指标体系固定下来
- 最后才是内容层和调度层

不容易因为前端采集的小波动，反复推倒重来。

## 20. 现在就可以执行的后处理命令

假设当天原始结果文件在：

- `/root/fangdi-data/var/fangdi-count-results.jsonl`

建议每天跑完后按这个顺序执行。

### 20.1 标准化原始结果

```bash
cd /root/work/fangdi-data
. .venv/bin/activate
python scripts/normalize_fangdi_results.py \
  /root/fangdi-data/var/fangdi-count-results.jsonl \
  /root/fangdi-data/output/normalized/fangdi_daily_counts_$(date +%F).csv \
  --failures-csv /root/fangdi-data/output/normalized/fangdi_daily_failures_$(date +%F).csv \
  --summary-json /root/fangdi-data/output/normalized/fangdi_daily_summary_$(date +%F).json
```

### 20.2 生成区级 / 板块级指标

首日没有历史数据时：

```bash
cd /root/work/fangdi-data
. .venv/bin/activate
python scripts/analyze_fangdi_daily.py \
  /root/fangdi-data/output/normalized/fangdi_daily_counts_$(date +%F).csv \
  /root/fangdi-data/output/metrics/fangdi_plate_metrics_$(date +%F).csv \
  /root/fangdi-data/output/metrics/fangdi_district_metrics_$(date +%F).csv \
  /root/fangdi-data/output/fangdi/$(date +%F)/insights.json
```

从第 2 天开始，可以补上一日数据：

```bash
cd /root/work/fangdi-data
. .venv/bin/activate
python scripts/analyze_fangdi_daily.py \
  /root/fangdi-data/output/normalized/fangdi_daily_counts_$(date +%F).csv \
  /root/fangdi-data/output/metrics/fangdi_plate_metrics_$(date +%F).csv \
  /root/fangdi-data/output/metrics/fangdi_district_metrics_$(date +%F).csv \
  /root/fangdi-data/output/fangdi/$(date +%F)/insights.json \
  --previous-daily-counts /root/fangdi-data/output/normalized/fangdi_daily_counts_<上一日>.csv
```

### 20.3 生成标题和文案草稿

```bash
cd /root/work/fangdi-data
. .venv/bin/activate
python scripts/render_fangdi_caption.py \
  /root/fangdi-data/output/fangdi/$(date +%F)/insights.json \
  /root/fangdi-data/output/metrics/fangdi_plate_metrics_$(date +%F).csv \
  /root/fangdi-data/output/metrics/fangdi_district_metrics_$(date +%F).csv \
  /root/fangdi-data/output/fangdi/$(date +%F)/headline_candidates.md \
  /root/fangdi-data/output/fangdi/$(date +%F)/caption_draft.md
```

### 20.4 生成历史对比结果

从第 2 天起，建议每天再补一层历史对比增强：

```bash
cd /root/work/fangdi-data
. .venv/bin/activate
python scripts/analyze_fangdi_history.py \
  /root/fangdi-data/output/metrics/fangdi_plate_metrics_$(date +%F).csv \
  /root/fangdi-data/output/metrics/fangdi_district_metrics_$(date +%F).csv \
  /root/fangdi-data/output/metrics/fangdi_plate_history_$(date +%F).csv \
  /root/fangdi-data/output/metrics/fangdi_district_history_$(date +%F).csv \
  /root/fangdi-data/output/fangdi/$(date +%F)/history_summary.json \
  --plate-history-dir /root/fangdi-data/output/metrics \
  --district-history-dir /root/fangdi-data/output/metrics
```

这一步会自动：

- 找到最近一次快照做 `1日对比`
- 找到最近可用的 `7日前` 快照做 `7日对比`
- 输出对比增强后的板块表与区级表
- 输出一份 `history_summary.json`

如果历史还不够，它会自动留空，不会报错中断。

### 20.5 生成卡片图片

这一步依赖 `matplotlib`。服务器首次使用前，安装：

```bash
pip install matplotlib
```

然后执行：

```bash
cd /root/work/fangdi-data
. .venv/bin/activate
python scripts/render_fangdi_cards.py \
  /root/fangdi-data/output/metrics/fangdi_plate_metrics_$(date +%F).csv \
  /root/fangdi-data/output/metrics/fangdi_district_metrics_$(date +%F).csv \
  /root/fangdi-data/output/fangdi/$(date +%F)/insights.json \
  /root/fangdi-data/output/fangdi/$(date +%F)/cards
```

### 20.6 一键后处理

如果你不想每天手动拼上面这些命令，现在也可以直接用一键脚本：

```bash
cd /root/work/fangdi-data
bash scripts/run_fangdi_postprocess.sh
```

它会自动完成：

- 归档原始 `jsonl`
- 生成标准化明细和失败表
- 生成区级 / 板块级指标
- 生成历史对比增强表
- 生成 `insights.json`
- 生成标题候选和文案草稿
- 如果安装了 `matplotlib`，再自动生成卡片 PNG

如果你只是想先验证文字链路，不想生成图片，可以：

```bash
cd /root/work/fangdi-data
bash scripts/run_fangdi_postprocess.sh --skip-cards
```
