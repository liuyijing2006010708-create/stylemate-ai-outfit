# 数据放置约定

原始 Polyvore 数据不要提交到 Git。推荐结构：

```text
data/
├── raw/
│   └── polyvore/
│       ├── images/
│       │   ├── <set_id>/<index>.jpg     # Maryland 原始格式
│       │   └── <item_id>.jpg            # Polyvore Outfits 格式也支持
│       └── annotations/*.json
├── splits/                              # split_dataset.py 生成
└── processed/
    ├── train/{reference,target,metadata}/
    ├── val/{reference,target,metadata}/
    └── test/{reference,target,metadata}/
```

`target` 中每个 `.jpg` 旁边有一个同名 `.txt` caption；`metadata` 记录参考单品和目标套装的成员关系。
