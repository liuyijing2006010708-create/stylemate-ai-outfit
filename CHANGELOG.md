# Changelog

本项目采用语义化版本号；格式参考 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)。

## [Unreleased]

暂无已记录变更。

## [0.3.1] - 2026-09-15

### Added

- 增加架构、配置、Provider 与 StyleGen 训练文档。
- 增加 MIT License、贡献指南、安全政策及 GitHub Issue / Pull Request 模板。

### Changed

- 将 README 重构为面向首次访问者的项目首页，详细实现说明迁移到 `docs/`。
- 将 API 文档和通用运行时统一表述为 OpenAI-compatible endpoints。

### Removed

- 移除开发阶段使用过的个人中转服务品牌、专属域名别名和对应说明。

## [0.3.0] - 2026-09-14

### Added

- 首次访问默认使用通用 OpenAI-compatible endpoint，可选择 Responses API 或 Chat Completions。
- 增加整理后的男女完整流程示例，统一使用可读的英文文件名。

### Changed

- 默认模型改为 `gpt-4.1-mini` 与 `gpt-image-1`，兼容服务可在页面中覆盖为实际模型名。
- 将骑行与开车拆成独立通勤选项，并在搭配提示中加入对应的活动约束。
- 将百分比改称“AI 推荐度”，避免将模型候选分误解为经过标定的准确率。

### Fixed

- 修复识别确认页直接显示 HTML 标签的问题。
- 修复颜色已经包含在品类中时出现“黑色黑色”等重复名称的问题。
- 限制识别字段职责，避免把滚边、纽扣等细节塞进单品标题。
- 固定 pytest 只收集正式 `tests/`，避免本地发布副本被重复收集。

## [0.2.0-rc.1] - 2026-09-13

### Added

- 增加公开部署入口、API 首次配置、固定 Demo、会话级历史与导出。
- 增加异步图片任务续查、错误分类、请求诊断和安全 URL 校验。

### Changed

- 完成 P0-1 发布候选验收，并通过 GitHub Actions 回归与依赖审计。

[Unreleased]: https://github.com/liuyijing2006010708-create/stylemate-ai-outfit/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/liuyijing2006010708-create/stylemate-ai-outfit/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/liuyijing2006010708-create/stylemate-ai-outfit/releases/tag/v0.3.0
[0.2.0-rc.1]: https://github.com/liuyijing2006010708-create/stylemate-ai-outfit/releases/tag/v0.2.0-rc.1
