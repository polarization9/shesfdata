# Fangdi 计数查询 PoC 操作文档

这份文档默认你当前的运行方式是：

- 直接使用腾讯云服务器
- PoC 阶段继续使用 `root` 用户
- 先在远程桌面里手工解锁 `fangdi`
- 再通过 Firefox userscript 启动一小批自动查询任务

如果你已经准备从 PoC 进入持续跑数、分析和内容生产阶段，可以继续看：

- `docs/fangdi-analysis-automation.md`

## 1. 这次新增了哪些文件

- `config/fangdi-poc.sample.json`
- `scripts/build_query_plan.py`
- `scripts/ocr_http_service.py`
- `scripts/render_fangdi_userscript.py`
- `scripts/summarize_fangdi_counts.py`

## 2. 在服务器上准备目录

先在服务器上执行：

```bash
mkdir -p /root/fangdi-data/config
mkdir -p /root/fangdi-data/var
mkdir -p /root/fangdi-data/generated
mkdir -p /root/work
```

## 3. 把项目代码放到服务器

你可以用 `git clone` 或 `scp`，例如：

```bash
cd /root/work
git clone <你的仓库地址> fangdi-data
cd /root/work/fangdi-data
```

如果你暂时还没有远程仓库，也可以先把本地目录打包上传。

## 4. 安装 Python 依赖

在服务器里执行：

```bash
cd /root/work/fangdi-data
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install ddddocr opencv-python-headless numpy
```

如果这台机器访问 PyPI 慢，可以改成国内镜像：

```bash
pip install ddddocr opencv-python-headless numpy -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 5. 准备配置文件

先复制样例配置：

```bash
cp /root/work/fangdi-data/config/fangdi-poc.sample.json /root/fangdi-data/config/fangdi-poc.json
```

然后编辑这个文件：

```bash
vi /root/fangdi-data/config/fangdi-poc.json
```

你现在最需要改的是：

- `dimensions.districts`
- `dimensions.listing_age_buckets`

第一轮 PoC 建议只填很小一批：

- `1` 个区
- `2-3` 个板块
- `4` 个挂牌时间桶

例如：

- 黄浦区
- 老西门板块、董家渡板块
- `15天`、`1个月`、`3个月`、`3个月以上`

先不要一上来就跑全量。

## 6. 生成查询计划

执行：

```bash
cd /root/work/fangdi-data
. .venv/bin/activate
python scripts/build_query_plan.py \
  /root/fangdi-data/config/fangdi-poc.json \
  /root/fangdi-data/generated/query-plan.json
```

成功后会得到：

- `/root/fangdi-data/generated/query-plan.json`

## 7. 启动本地 OCR / 结果服务

开一个 SSH 窗口，保持它一直运行：

```bash
cd /root/work/fangdi-data
. .venv/bin/activate
python scripts/ocr_http_service.py \
  --host 127.0.0.1 \
  --port 8765 \
  --results-file /root/fangdi-data/var/fangdi-count-results.jsonl
```

你可以再开一个 SSH 窗口做健康检查：

```bash
curl http://127.0.0.1:8765/healthz
```

如果返回：

```json
{"ok": true}
```

说明服务正常。

## 8. 生成跨刷新 userscript

再开一个 SSH 窗口执行：

```bash
cd /root/work/fangdi-data
. .venv/bin/activate
python scripts/render_fangdi_userscript.py \
  /root/fangdi-data/config/fangdi-poc.json \
  /root/fangdi-data/generated/query-plan.json \
  /root/fangdi-data/generated/fangdi-userscript.js
```

成功后会得到：

- `/root/fangdi-data/generated/fangdi-userscript.js`

## 9. 在远程桌面里手工解锁 Fangdi

在服务器远程桌面的浏览器里：

1. 打开 `fangdi` 查询页
2. 手工确认页面可正常使用
3. 手工成功查询 1 次
4. 保持页面停留在查询页

这一步的目标是：

- 站前 challenge 已过
- 当前页面处于“可提交查询”的状态

## 10. 安装并执行 userscript

在远程桌面的 Firefox 里，先安装一个 userscript 扩展。

推荐：

- `Violentmonkey`
- `Tampermonkey`

安装完成后：

1. 打开扩展的新脚本编辑页
2. 删除默认模板内容
3. 把这个文件的全部内容粘进去保存：

- `/root/fangdi-data/generated/fangdi-userscript.js`

然后回到 `fangdi` 查询页并刷新页面。

如果脚本安装成功，页面右下角会出现一个状态框：

- `Fangdi Userscript`
- `开始`
- `停止`
- `重置`

你手工解锁完页面后，点击：

- `开始`

这版和之前最大的区别是：

- 查询提交后即使整页刷新，脚本也会自动从 `localStorage` 里恢复进度继续跑
- 不需要每次都往 Console 里粘贴长脚本
- 右下角状态框会在新页面重新出现

## 11. 查看结果文件

runner 每跑完一条查询，都会往这个文件追加一行：

- `/root/fangdi-data/var/fangdi-count-results.jsonl`

你可以在 SSH 里查看：

```bash
tail -n 20 /root/fangdi-data/var/fangdi-count-results.jsonl
```

每一条结果里至少会有：

- `district`
- `plate`
- `listing_age`
- `count`
- `status`
- `captcha_guess`
- `captcha_attempt`

## 12. 汇总结果

当这批查询跑完后，执行：

```bash
cd /root/work/fangdi-data
. .venv/bin/activate
python scripts/summarize_fangdi_counts.py \
  /root/fangdi-data/var/fangdi-count-results.jsonl \
  /root/fangdi-data/var/fangdi-count-summary.json
```

会生成：

- `/root/fangdi-data/var/fangdi-count-summary.json`

这个文件就是后面做日报内容包的基础输入。

## 13. 第一轮你要重点验证什么

第一轮 PoC 不要追求“跑很多”，只验证这 4 件事：

1. 浏览器能否成功请求 `http://127.0.0.1:8765/ocr`
2. userscript 能否自动填写：
   - 区
   - 板块
   - 挂牌时间
3. 成功查询是否会正确写入 `jsonl`
4. 失败查询是否也会写入 `jsonl`

只要这 4 件事成立，这条链路就已经打通了。

## 14. 第一版最可能卡住的地方

这版 userscript 现在默认假设：

- 页面控件要么是原生 `select`
- 要么是点开后按可见文本点击选项

如果页面实际是更复杂的自定义组件，第一版最容易卡在：

- 区没有正确选上
- 板块没有正确选上
- 挂牌时间没有正确选上
- 查询按钮没有定位到

如果出现这些问题，不用推翻整套方案，只需要回到配置文件里补这些选择器：

- `runner.selectors.district_control`
- `runner.selectors.plate_control`
- `runner.selectors.listing_age_control`
- `runner.selectors.captcha_input`
- `runner.selectors.query_button`

这会是下一步校准工作。

## 15. 你现在最推荐的执行顺序

1. 启动 `ocr_http_service.py`
2. 生成 `query-plan.json`
3. 生成 `fangdi-userscript.js`
4. 在 Firefox 里安装 userscript 扩展
5. 把 `fangdi-userscript.js` 粘进去保存
6. 打开 `fangdi` 页面并手工解锁一次
7. 点击右下角的 `开始`
8. 在 SSH 里用 `tail -f` 盯住结果文件

## 16. 导出全量“区 -> 板块”字典

如果你准备试全量运行，不要手工维护板块名。先从网站当前下拉框导出一份字典。

先在服务器上生成导出脚本：

```bash
cd /root/work/fangdi-data
. .venv/bin/activate
python scripts/render_fangdi_dimensions_exporter.py \
  /root/fangdi-data/generated/fangdi-dimensions-exporter.js
```

然后在远程桌面的浏览器里：

1. 打开 `fangdi` 查询页
2. 手工完成一次解锁
3. 打开 DevTools Console
4. 把 `/root/fangdi-data/generated/fangdi-dimensions-exporter.js` 的内容粘进去执行
5. 右下角会出现 `Fangdi Dimensions Exporter`
6. 点击 `开始导出`

跑完后，浏览器会自动下载：

- `fangdi-dimensions.json`

这份文件里会包含：

- 全部区
- 每个区当前网站里真实存在的板块
- 当前网站里的挂牌时间选项

## 17. 把导出的字典转成可跑配置

假设你把导出的文件放到了服务器上的：

- `/root/fangdi-data/input/fangdi-dimensions.json`

可以执行：

```bash
mkdir -p /root/fangdi-data/input

cd /root/work/fangdi-data
. .venv/bin/activate
python scripts/build_fangdi_config_from_dimensions.py \
  /root/work/fangdi-data/config/fangdi-poc.sample.json \
  /root/fangdi-data/input/fangdi-dimensions.json \
  /root/fangdi-data/config/fangdi-full.json
```

会生成：

- `/root/fangdi-data/config/fangdi-full.json`

这份配置会：

- 继承现有 runner / OCR / 结果文件配置
- 使用导出得到的全量区板块字典
- 默认只保留 `15天`、`1个月`、`3个月`、`3个月以上` 这 4 个挂牌时间桶

## 18. 用全量配置生成查询计划

```bash
cd /root/work/fangdi-data
. .venv/bin/activate
python scripts/build_query_plan.py \
  /root/fangdi-data/config/fangdi-full.json \
  /root/fangdi-data/generated/query-plan-full.json

python scripts/render_fangdi_userscript.py \
  /root/fangdi-data/config/fangdi-full.json \
  /root/fangdi-data/generated/query-plan-full.json \
  /root/fangdi-data/generated/fangdi-userscript-full.js
```

然后把 `fangdi-userscript-full.js` 更新到 Firefox 里的 userscript 扩展里，就可以开始跑全量查询。

就按下面顺序做：

1. 复制并编辑配置文件
2. 生成查询计划
3. 启动 OCR 服务
4. 生成浏览器 runner
5. 在远程桌面里手工解锁 Fangdi
6. 执行 runner
7. 看 `jsonl` 是否开始写结果

只要你走到第 7 步，我们就可以开始调页面选择器了。
