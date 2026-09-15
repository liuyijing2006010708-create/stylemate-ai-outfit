# StyleGen 数据与训练准备

StyleGen 是 StyleMate 的后续生成模型实验模块。本阶段只准备可复现的数据对、质量检查和 Base / LoRA 对照契约，不改变当前线上应用的模型调用或推荐流程。

## 数据来源与边界

数据流水线兼容 Polyvore 常见的两种本地图片布局：

```text
images/<set_id>/<index>.jpg
images/<item_id>.jpg
```

原始数据需要根据数据集授权自行下载到 `data/raw/polyvore/`。脚本不会从失效或来源不明的图片 URL 自动抓取内容，原始数据、处理后数据、模型权重和输出均不提交到 Git。

优先使用 Polyvore 数据发布方提供的 train / valid / test 拆分。只有拿到单一合集时，才使用固定随机种子的 `split_dataset.py`。

## 数据流水线

先检查标注与图片布局：

```bash
python scripts/inspect_dataset.py \
  --annotations data/raw/polyvore/annotations/outfits.json \
  --images-root data/raw/polyvore/images \
  --show 5 \
  --preview-dir outputs/source-preview
```

单一合集可按套装拆分：

```bash
python scripts/split_dataset.py \
  --annotations data/raw/polyvore/annotations/outfits.json \
  --images-root data/raw/polyvore/images \
  --output-dir data/splits \
  --seed 42
```

分别构建训练、验证和测试数据对：

```bash
python scripts/build_pairs.py \
  --annotations data/splits/train.json \
  --images-root data/raw/polyvore/images \
  --output-root data/processed \
  --split train \
  --limit 320 \
  --size 512

python scripts/build_pairs.py \
  --annotations data/splits/val.json \
  --images-root data/raw/polyvore/images \
  --output-root data/processed \
  --split val \
  --limit 40 \
  --size 512

python scripts/build_pairs.py \
  --annotations data/splits/test.json \
  --images-root data/raw/polyvore/images \
  --output-root data/processed \
  --split test \
  --limit 40 \
  --size 512
```

执行完整性检查、生成 QA 图并打包：

```bash
python scripts/check_dataset.py \
  --root data/processed \
  --splits train val test \
  --size 512 \
  --sample 50 \
  --qa-dir outputs/dataset-qa

python scripts/package_dataset.py \
  --root data/processed \
  --output outputs/stylegen-dataset.zip
```

检查器验证参考图、目标图、caption 和 metadata 是否一一对应，图片能否完整解码，分辨率是否正确，以及 `reference_item_id` 是否存在于 `target_item_ids`。自动检查通过后仍需人工查看至少 50 对 QA 图。

## 实验约定

- `configs/stylegen_m1.yaml` 记录数据、模型和训练参数，是训练器无关的实验契约。
- `experiments.csv` 记录相同 reference、prompt、seed 和尺寸下的 Base / LoRA 对照结果。
- `requirements-train.txt` 只在确定 GPU 镜像和 CUDA 版本后安装；正式实验前应冻结已验证版本。
- `inference/` 预留固定测试集上的 Base / LoRA 推理脚本。

当前 M1 目标和验收条件见 [`../STYLEGEN_SPEC.md`](../STYLEGEN_SPEC.md)，数据目录约定见 [`../data/README.md`](../data/README.md)。

## 参考资料

- [Polyvore dataset repository](https://github.com/xthan/polyvore-dataset)
- [MMFashion compatibility dataset format](https://github.com/open-mmlab/mmfashion/blob/master/docs/dataset/FASHION_COMPATIBILITY_DATASET.md)
- [Black Forest Labs model documentation](https://bfl.ai/models/flux-2-klein)
