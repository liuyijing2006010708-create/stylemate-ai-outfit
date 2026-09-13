# StyleGen M1 数据里程碑

## 目标

在租用 GPU 前，把 Polyvore 套装数据转换为可复现、可检查的“单件参考图 → 含该单件的整套 flat-lay”训练对，并准备 FLUX.2 [klein] 4B Base 的 LoRA 实验配置。

## 验收条件

- 数据拆分固定随机种子，train / val / test 之间无重复套装或源单品。优先使用 Polyvore 官方 disjoint split。
- 每个 pair 都有同名的参考图、目标图、caption 与 metadata。
- 图片可由 Pillow 完整解码，首轮统一为 512×512。
- metadata 的 `reference_item_id` 必须存在于 `target_item_ids`。
- 首轮建议 320 / 40 / 40，共约 400 对；不够时保持 80% / 10% / 10%。
- `check_dataset.py` 零错误后，人工查看至少 50 对 QA 图。
- 基线与 LoRA 使用相同参考图、prompt、seed 和尺寸，并记录到 `experiments.csv`。

## 非目标

本里程碑不下载来源不明的图片、不开始付费 GPU 训练，也不把数据集或模型权重提交到 Git。
