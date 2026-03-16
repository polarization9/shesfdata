# Fangdi 计数查询 PoC 操作文档

这份文档默认你当前的运行方式是：

- 直接使用腾讯云服务器
- PoC 阶段继续使用 `root` 用户
- 先在远程桌面里手工解锁 `fangdi`
- 再启动一小批自动查询任务

## 1. 这次新增了哪些文件

- `config/fangdi-poc.sample.json`
- `scripts/build_query_plan.py`
- `scripts/ocr_http_service.py`
- `scripts/render_fangdi_browser_runner.py`
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

## 8. 生成浏览器内 runner

再开一个 SSH 窗口执行：

```bash
cd /root/work/fangdi-data
. .venv/bin/activate
python scripts/render_fangdi_browser_runner.py \
  /root/fangdi-data/config/fangdi-poc.json \
  /root/fangdi-data/generated/query-plan.json \
  /root/fangdi-data/generated/fangdi-browser-runner.js
```

成功后会得到：

- `/root/fangdi-data/generated/fangdi-browser-runner.js`

## 9. 在远程桌面里手工解锁 Fangdi

在服务器远程桌面的浏览器里：

1. 打开 `fangdi` 查询页
2. 手工确认页面可正常使用
3. 手工成功查询 1 次
4. 保持页面停留在查询页

这一步的目标是：

- 站前 challenge 已过
- 当前页面处于“可提交查询”的状态

## 10. 执行浏览器 runner

在远程桌面的浏览器里打开 DevTools Console。

然后把这个文件内容整体复制进去执行：

- `/root/fangdi-data/generated/fangdi-browser-runner.js`

执行后，页面右下角会出现一个小状态框。

注意：

- 如果 DevTools 打开后页面又开始不稳定，你可以在 runner 启动后把 DevTools 关掉
- 页面只要不刷新，脚本通常会继续跑

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
2. runner 能否自动填写：
   - 区
   - 板块
   - 挂牌时间
3. 成功查询是否会正确写入 `jsonl`
4. 失败查询是否也会写入 `jsonl`

只要这 4 件事成立，这条链路就已经打通了。

## 14. 第一版最可能卡住的地方

这版 runner 现在默认假设：

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

就按下面顺序做：

1. 复制并编辑配置文件
2. 生成查询计划
3. 启动 OCR 服务
4. 生成浏览器 runner
5. 在远程桌面里手工解锁 Fangdi
6. 执行 runner
7. 看 `jsonl` 是否开始写结果

只要你走到第 7 步，我们就可以开始调页面选择器了。
