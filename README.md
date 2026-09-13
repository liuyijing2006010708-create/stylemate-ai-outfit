# StyleMate — 多模态 AI 穿搭助手

[在线体验](https://stylemate-ai-outfit.streamlit.app/) · [发布与验收记录](RELEASE_P0_1.md)

当前整理的候选版本为 `0.2.0-rc.1`，页面顶部显示版本号。线上是否已更新、真实 API 验收是否完成，以发布记录为准。首次访问可选择「暂不配置，仅查看固定 Demo」，无需 Key；固定 Demo 不代表实时生成。

StyleMate 把“我已经有这件衣服，但不知道怎么搭”拆成一条可解释的 AI Pipeline：

```text
单品照片（可旋转/裁剪/质量提示） → 服装结构化识别 → 识别结果确认/修改 → 三套候选搭配（稳妥/进阶/突破，校验差异度）
→ 偏好排序 → 平铺效果图（可逐张生成）→ 会话历史/导出/反馈记录
```

首次打开会先进入 API 配置页，可选择服务商预设自动填写协议与路径。验证 API Key 后可识别真实图片、确认或修改识别结果、结合天气温度与通勤方式生成结构化搭配，并按需调用图像编辑 API 生成三张保持原单品的 flat-lay 效果图；不配置时仍可显式进入固定 Demo。

## 快速开始

推荐 Python 3.12，与部署和 CI 保持一致；现有 Python 3.10 本地环境也有回归测试覆盖。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

没有 API Key 时，可在首次配置页点击“暂不配置，仅查看固定 Demo”。Demo 不读取上传图片，页面会明确标记，避免把示例结果误认为真实识别。

要运行真实 AI 链路：

```bash
cp .env.example .env
# 在 .env 中填写 OPENAI_API_KEY（不要提交该文件）
streamlit run app.py
```

使用兼容 OpenAI 协议的中转站时，可以直接在首次配置页填写：

- 中转站 API Key
- API Base URL，例如 `https://example.com/v1`（选择“OpenAI 官方 / RightAPI 异步生图”预设时自动填写）
- 生图 Base URL（可选）：当生图接口的域名/路径与文本接口不同时单独填写，留空则复用文本 Base URL
- 中转站支持的视觉/文本模型名称
- 可选的图片编辑模型名称
- `Responses API` 或兼容性更广的 `Chat Completions`（预设自动选择，可在高级选项中修改）

文本验证直接发送一次最小请求，不依赖 `/models`，因此不支持模型列表的中转站也能正常保存使用。普通中转站需实现兼容的 `/images/edits` 才能生成真实平铺效果图；RightAPI 则由程序自动切换到其异步绘图协议。

### RightAPI / RightCode 配置

RightAPI（rightapi.ai）与 RightCode（right.codes）是同一中转平台，不能填写站点根路径。文本渠道应使用：

```text
# RightAPI
Base URL: https://rightapi.ai/codex/v1
# 或 RightCode
Base URL: https://www.right.codes/codex/v1

文本模型: gpt-5.6-luna
文本协议: Responses API
```

程序会把误填的根路径自动纠正为 `/codex/v1`。生成平铺图时，程序会把参考单品作为 Data URL 提交到 RightAPI `/draw/v1/images/generations`，再轮询 `/v1/tasks/{task_id}`，任务完成后下载并校验图片；任务编号会保留，超时后可继续查询而不会重复提交。整套流程可能需要几分钟。

## 功能

- JPG / PNG / WEBP 单品上传，10 MB 限制；上传前完成格式、像素与大小校验并统一转存
- 拍照小助手：上传后可旋转、按百分比裁剪主体，模糊或分辨率不足时提示重拍（可选 rembg 背景移除）
- Responses API + Pydantic Structured Outputs 服装属性识别，识别结果可编辑确认
- 三套搭配分别面向“稳妥 / 进阶 / 突破”目标，程序校验三套之间的差异度
- 场景、温度、天气与通勤方式影响面料、鞋子与外套推荐
- 轻量偏好档案：禁用单品等硬性约束逐套校验，颜色/版型/预算/备注写入提示词
- 可选性别和年龄段：由用户自填、默认不提供；不从照片推断，仅随偏好发送给配置的服务商，用于搭配规划与单套替换；清除会话数据时一并清除
- 页面、历史、导出与生图提示词使用同一份完整单品字段，减少图文冲突；实际生成图片仍需人工核对
- 可解释兼容度评分与透明的 V1 偏好加权
- 可选 GPT Image 2 参考图编辑，强调原单品特征保持；默认只生成文字，图片可逐张生成
- 支持 RightAPI 异步绘图任务提交、轮询与安全取图
- “换一套”只重新生成一套文字方案（1 次文本请求），其余两套不变，不自动生图；失败时保留原方案
- 最近 4 批历史、最多 20 套会话收藏；可查看、移除收藏，下载图片与文字清单
- 批次标识隔离历史和收藏，补生成/重试图片同步到所属批次；下载格式与图片真实格式一致
- 从 API 设置返回时保留确认编辑和原结果；上传页可“继续上次搭配”，恢复异步任务查询
- 页底可确认清除照片、结果、收藏和偏好，保留 API 设置；清除 Key 使用 API 设置页的独立按钮
- 无 Key Demo、API 失败可恢复、移动端触控与响应式布局
- 服务商预设（OpenAI 官方 / 兼容站 / RightAPI / 自定义）与分类型调用限流
- 明细化错误提示（Key、模型、余额、限流等）与页面请求编号，便于定位日志
- 地址 / DNS 独立检查：无需 Key、不调用模型；遇到 Clash Fake-IP（198.18.0.0/15）自动通过 Cloudflare 加密 DNS（https://1.1.1.1/dns-query）查询真实 A/AAAA 地址，仅发送域名，不发送 Key、照片或对话。文本、生图、异步任务查询与图片下载共用这一回退；校验全部解析结果后连接固定公网 IP，保留 HTTPS 证书校验、内网限制和禁止重定向。回退失败会明确提示，不放行 Fake-IP；正常系统 DNS 不触发外部回退。
- 首次 API Key 配置与连接验证；会话 Key 不写入项目文件；隐私与费用说明内置于配置页
- 上传图片缺少 Key 时拒绝运行，不再静默回退到黑色皮夹克 Demo

## 目录

```text
app.py                         Streamlit 产品界面与状态流
stylemate/models.py            结构化输入/输出契约
stylemate/openai_service.py    视觉理解、搭配规划、图片生成路由
stylemate/rightapi_images.py   RightAPI 异步绘图任务适配器
stylemate/ranking.py           可替换的兼容度排序接口
stylemate/demo.py              无 Key 演示数据
assets/                        Demo 平铺图与原单品图
design/                        上传态与结果态视觉设计稿
tests/                         核心数据与排序测试
```

## 模型调用策略

- `OPENAI_TEXT_MODEL` 默认 `gpt-5.6-luna`，负责图片理解与搭配规划。
- `OPENAI_IMAGE_MODEL` 默认 `gpt-image-2`，负责参考图条件下的平铺效果图。
- 真实图像生成默认关闭，避免一次体验产生三次图像生成调用。
- 上传图只在当前 Streamlit 会话内保留；项目不会自动写入 `uploads/`。

## V2 演进路径

`stylemate/ranking.py` 是刻意保留的模型替换点。下一步可将候选扩展到 10–20 套，用 FashionCLIP/CLIP 编码单品，以 Polyvore compatibility 数据训练 LightGBM 或 MLP，最终只展示 Top 3。SAM2 分割和持久化用户画像留到 V3，避免在 V1 过早增加部署负担。

## StyleGen 训练数据准备

仓库已加入 GPU 租用前的数据工程流水线。它兼容 Polyvore 常见的两种本地图片布局：`images/<set_id>/<index>.jpg` 与 `images/<item_id>.jpg`。原始数据须由你按数据集授权自行下载并放入 `data/raw/polyvore/`；流水线不会从已经失效或来源不明的图片 URL 自动抓取内容。

如果下载的是 Polyvore 作者仓库已经提供的官方 train / valid / test 文件，优先保留原拆分，分别执行构建命令。只有拿到单一合集时才运行 `split_dataset.py`：

```bash
python scripts/inspect_dataset.py \
  --annotations data/raw/polyvore/annotations/outfits.json \
  --images-root data/raw/polyvore/images \
  --show 5 --preview-dir outputs/source-preview

python scripts/split_dataset.py \
  --annotations data/raw/polyvore/annotations/outfits.json \
  --images-root data/raw/polyvore/images \
  --output-dir data/splits --seed 42

python scripts/build_pairs.py \
  --annotations data/splits/train.json \
  --images-root data/raw/polyvore/images \
  --output-root data/processed --split train --limit 320 --size 512

python scripts/build_pairs.py \
  --annotations data/splits/val.json \
  --images-root data/raw/polyvore/images \
  --output-root data/processed --split val --limit 40 --size 512

python scripts/build_pairs.py \
  --annotations data/splits/test.json \
  --images-root data/raw/polyvore/images \
  --output-root data/processed --split test --limit 40 --size 512
```

随后运行完整性检查，并人工查看生成的 50 对 QA 图：

```bash
python scripts/check_dataset.py \
  --root data/processed --splits train val test \
  --size 512 --sample 50 --qa-dir outputs/dataset-qa

python scripts/package_dataset.py \
  --root data/processed --output outputs/stylegen-dataset.zip
```

检查器会验证同名文件一一对应、图片可解码、分辨率正确、caption 非空，以及目标套装 metadata 确实包含参考单品。训练假设与参数位于 `configs/stylegen_m1.yaml`；它是训练器无关的实验契约，待 GPU 镜像与训练框架确定后再映射到具体命令，避免现在锁定错误的 CUDA / PyTorch 组合。`experiments.csv` 已预留相同条件下的 Base 与 LoRA 对照记录。

数据格式与流程的完整验收标准见 `STYLEGEN_SPEC.md`。Polyvore 原始标注说明可参考 [作者数据仓库](https://github.com/xthan/polyvore-dataset) 与 [MMFashion 数据格式说明](https://github.com/open-mmlab/mmfashion/blob/master/docs/dataset/FASHION_COMPATIBILITY_DATASET.md)；模型选择依据 [Black Forest Labs 官方模型说明](https://bfl.ai/models/flux-2-klein)，M1 使用适合微调的 `black-forest-labs/FLUX.2-klein-base-4B`。

## 测试

```bash
pip install -r requirements-dev.txt
python -m pip check
pytest -q
```

接口自动化测试使用替身或 MockTransport，不发送真实付费请求。完整验收记录和上线前待核对事项见 [P1/P2 验收记录](P1P2_ACCEPTANCE.md)。
