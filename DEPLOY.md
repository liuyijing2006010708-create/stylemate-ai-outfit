# 部署到 Streamlit Community Cloud

StyleMate 的公开部署入口是 `cloud_app.py`。它复用本地应用的文本 API、生图 API 和异步任务流程，但不会把服务器环境中的 `OPENAI_API_KEY` 提供给访客。每位访客需要在自己的 Streamlit 会话中配置 API Key；无需在 Community Cloud Secrets 中放入维护者的个人 Key。

## 部署前准备

- Fork 或 clone 本仓库，并确认待部署分支通过 GitHub Actions。
- 部署副本的 GitHub 仓库可以是 Public 或 Private；是否可选 Private 取决于 Streamlit Community Cloud 当前的仓库访问权限。
- 不要提交 `.env`、`.venv`、`.streamlit/secrets.toml`、API Key、私人图片、训练数据或模型权重。
- 保留 `stylemate/`、`assets/` 和 `.streamlit/` 的目录结构。

## 首次部署

1. 登录 [Streamlit Community Cloud](https://share.streamlit.io/) 并连接 GitHub。
2. 选择 **Create app**，再选择包含本项目的仓库和分支。
3. 将 Main file path 设置为 `cloud_app.py`。
4. 在 Advanced settings 中选择 Python 3.12；依赖由根目录 `requirements.txt` 安装。
5. 选择可用的 App URL 并部署，以平台实际显示的网址为准。
6. 按需要设置应用的公开访问权限；公开应用与公开仓库是两个不同设置。
7. 使用未登录窗口确认首次配置页和固定 Demo 可以访问。

本地按云端入口验证：

```bash
python -m streamlit run cloud_app.py
```

## 验收

- 未登录访客可以打开配置页并显式进入固定 Demo。
- 不同浏览器会话的 API Key、图片和结果相互独立。
- 使用自己的 Key 和非敏感测试图片验证文本识别、三套搭配和一张平铺图。
- 真实生成可能由服务商计费；自动化测试不能证明账户余额、模型权限或线上生成质量。
- API Key、上传图片和结果只在会话内存中暂存；刷新、会话过期或服务重启可能清空状态。

## 更新与回滚

Community Cloud 会跟随所选分支重新部署。建议仅通过受保护的 `main` 分支发布：Pull Request 通过 CI 后合并，再检查部署日志和线上版本。

如果新版本出现启动失败或主流程严重回归：

1. 使用 `git revert` 创建反向提交，不强推或改写公共历史。
2. 通过 Pull Request 和 CI 合并回滚提交。
3. 等待 Community Cloud 重新部署，再核对配置页、固定 Demo 和下载功能。

发布或回滚可能清空访客会话，也不会取消已经提交给第三方服务商的任务。

## 运行与安全边界

- 外部服务地址只接受可解析的 HTTPS 公网 URL；DNS、内网地址、重定向和 HTTPS 证书均受校验。
- 文本和生图可以分别配置 Key、Base URL 与模型；文本检查可能产生少量费用，生图模型列表检查不会创建图片任务。
- 请求日志只保留请求编号、阶段、模型、协议、状态和耗时等固定字段，不记录 Key、图片、提示词或服务商响应正文。
- 单进程限流只适合当前 Streamlit 部署规模；多实例部署需要改为共享限流存储。
- 上传图片在发送前完成格式、大小、像素和解码检查，并重新编码以移除 EXIF / GPS 等元数据。
- 异步任务会立即写入当前会话；超时后可继续查询原任务，但刷新或服务重启仍可能丢失任务状态。
- 第三方服务商会接触用户主动提交的 Key、图片和提示词，用户应自行核对其隐私政策、数据保留和计费规则。

详细 API 配置见 [`docs/configuration.md`](docs/configuration.md)，协议支持见 [`docs/providers.md`](docs/providers.md)，安全报告方式见 [`SECURITY.md`](SECURITY.md)。

Streamlit 官方流程以[部署文档](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)为准。
