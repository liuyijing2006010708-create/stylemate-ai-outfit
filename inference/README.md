# 推理与对照实验

这个目录预留给固定测试集上的 baseline / LoRA 推理脚本。GPU 训练器确定后再接入具体 pipeline；对照实验必须复用同一组 reference、prompt、seed 与输出尺寸，并将结果写到 `outputs/` 与 `experiments.csv`。
