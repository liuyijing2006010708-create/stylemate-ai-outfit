# P0-1 发布与真实验收

候选版本：`0.2.0-rc.1`。本文件区分候选代码、已发布状态与真人验收，不以模拟测试代替真实效果。

## 发布目标

- 仓库：<https://github.com/liuyijing2006010708-create/stylemate-ai-outfit>
- 目标网址：<https://stylemate-ai-outfit.streamlit.app/>
- 启动入口：`cloud_app.py`；推荐 Python 3.12。
- 发布前基线提交：`19e76d20a27b1671b3f37ae74225368b2c375097`。
- 发布分支：`release/p0-1`。先在分支运行 CI，再经维护者确认合并；不要直接推送 main 绕开检查。

## 验收状态

| 项目 | 状态与证据 |
|---|---|
| 本地代码与原仓库历史对齐 | 已完成；工作文件不覆盖，历史从 origin/main 接续 |
| 本地回归、依赖检查与安全审计 | Python 3.12：167 项 pytest 通过，pip check 与 compileall 通过；pip-audit 2.10.1 审计 requirements.txt 未发现已知漏洞（2026-09-13） |
| 远程 GitHub Actions | 待推送后核实，不能以本地测试代替 |
| 线上版本与匿名 Demo | 待合并部署后核实页面版本号 |
| 真实识别、搭配与单张生图 | 待用户在页面亲自配置 Key 并验收 |
| 演示视频 | 已完成固定 Demo → 三套结果 → 收藏 → PNG 下载的隔离 Chrome 录像；无页面异常，不调用真实 API，不含 Key；文件 outputs/p0-1-demo/stylemate-fixed-demo.webm |

## 真实调用验收（由维护者操作）

1. 打开目标网址，确认显示 `版本 0.2.0-rc.1`。若不是此版本，先停止验收。
2. 选择实际服务商、模型，在密码输入框填写 Key；不要把 Key 放进聊天、截图、录像或仓库。
3. 选择一张自己有权使用的单品图片，尽量不包含人物和隐私信息。记录模型名称与日期即可。
4. 上传并执行真实识别。确认进入识别修改页，字段确实对应本次图片。
5. 确认/修改识别结果，生成三套文字搭配；检查原单品、场景和禁用条件。
6. 只生成其中一张平铺图。等待成功；若超时且已有任务编号，只继续查询，不重新提交。
7. 下载图片，确认能打开；记录是否保持原单品的主色、版型与关键图案。
8. 收藏方案，切换页面后返回核对；只承诺当前会话保留，不承诺刷新/重启恢复。
9. 记录各步成功或失败、可公开的结果截图、耗时及服务商账单中的费用（如果可见）。失败时保存本站请求编号，不复制含 Key 的日志。

验收记录：日期 ______；识别 ______；三套搭配 ______；单张生图 ______；下载 ______；费用（可选）______；结论 ______。

费用边界：文本测试也可能计费；上述主流程有识别、搭配和一张生图请求；不自动扩展到三张图或大规模评测。

## 回滚

出现启动失败、跨用户数据问题或主流程严重退化时暂停真实调用。以本次合并前 main 的实际 SHA 为准恢复旧版本；上述基线供核对，若 main 已前进不可盲目覆盖其他提交。

- 使用 `git revert` 创建反向提交，不强推、不改写公共历史；合并提交使用 `git revert -m 1 <合并提交>`。
- 经 CI 和维护者确认后推送，等待 Community Cloud 重新部署。
- 核对旧版页面、匿名 Demo 和下载是否恢复。
- 发布/回滚均可能清空会话；不会自动取消服务商已有生图任务，重新提交前先核对。
- Python 解释器升级可能需要平台额外操作，不把 `.python-version` 文件当作已生效的运行环境证据。

## 本地复现与视频

```bash
python -m pip install -r requirements-dev.txt
python -m pip check
python -m compileall -q app.py cloud_app.py stylemate stylegen scripts
python -m pytest -q
python -m streamlit run cloud_app.py --server.port 8504
```

可选浏览器录像：使用装有 Playwright 与 Chrome 的 Node 环境执行 `node scripts/demo_recording.cjs`；非标准安装可用 `STYLEMATE_PLAYWRIGHT` 指定模块路径。需安装 Playwright 的 ffmpeg 组件。默认只访问本机 8504，不使用个人浏览器登录态；`STYLEMATE_DEMO_URL` 可指定上述已发布网址。输出位于忽略提交的 `outputs/p0-1-demo/`。
