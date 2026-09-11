# 发布到 Streamlit Community Cloud

当前部署方式：网站公开访问，源码使用自己的 GitHub 仓库；访客自行填写 API Key。
云端入口是 `cloud_app.py`。它复用现有页面、文本 API、生图 API 和异步绘图流程，
但不会把服务器环境中的 OPENAI_API_KEY 自动交给所有访客使用。
Key、上传图片和结果仍保存在各自 Streamlit 会话中；刷新、会话过期或云服务重启可能丢失。
无需在云平台 Secrets 中配置个人 API Key。

## 首次部署

1. 登录 GitHub，创建用于此项目的仓库（优先选择 Private，以免公开源码）。
2. 上传部署包解压后的文件，保留 `stylemate/`、`assets/` 和 `.streamlit/` 的目录结构。
   不要上传 `.env`、`.venv`、`.streamlit/secrets.toml` 或自己的图片/训练数据。
3. 登录 https://share.streamlit.io/ 并连接 GitHub。
4. 选择 Create app → Yup, I have an app，选择仓库和分支。
5. Main file path 填 `cloud_app.py`。Advanced settings 的 Python 选择 3.12。
   依赖由根目录 `requirements.txt` 安装。
6. 选择可用的 App URL，然后 Deploy。以平台实际显示的网址为准。
7. 在应用分享/访问设置中开启公开访问；用未登录窗口确认可以进入配置页及 Demo。
   公开应用与公开仓库是不同设置。

本地验证的启动命令：

```bash
.venv/bin/python -m streamlit run cloud_app.py
```

## 验收和更新

- 未登录访客可以打开配置页、查看固定 Demo。
- 两个浏览器会话的 API Key 和结果相互独立。
- 用自己的 Key 和一张测试图片验证文本识别、三套搭配和真实平铺图。
  真实生成会由中转站按其规则计费；本地模拟测试不能证明账户余额或模型权限。
- 修改 GitHub 中的源码后平台会重新部署；如果新版本异常，在 GitHub 恢复上一版本。
- 若启动失败，在平台管理页检查日志；如果域名可开但 API 报错，检查云端网络与模型权限。

官方部署说明：https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

## 本次八项加固

- 所有服务地址只接受 HTTPS 公网地址。DNS 任一结果为内网/保留地址时拒绝；建立连接使用已检查的数字 IP，TLS 仍校验原域名。禁止重定向和环境代理。
- 关闭第三方 SDK 的请求/响应调试日志；页面只展示固定的错误分类；配置对象的 repr 不包含 Key。
- 单进程最多 3 个操作；会话及 Key 哈希分别限制为至少间隔 10 秒、每 10 分钟最多 8 个操作。一次完整穿搭最多串行提交 3 张图片。多实例需改为共享限流存储。
- 文本和生图支持独立 Key、地址与检查按钮；可关闭生图只使用文字。文本检测直接请求选中的协议，不依赖 /models。
- 生图模型列表检查不会创建收费任务，也不会声称生图已成功；真实生图仍取决于服务商模型、余额、编辑协议支持。
- 异步任务立即保存在当前 Streamlit 会话中；轮询最多 180 秒预算，最多 90 次；查询瞬时错误最多连续重试 2 次。提交 POST 不自动重试。
- 超时/查询失败可继续查询原任务；提交结果未知或任务失败时，需勾选确认后才重新提交该图片，避免重复费用。其他图片和文字结果保留。
- 刷新导致会话销毁或服务重启时，任务状态仍可能丢失。可复制任务编号去服务商后台核对；没有新增数据库持久化。
- requirements.txt 固定核心依赖版本；.python-version 记录 3.12。Community Cloud 的实际 Python 版本必须在平台设置中选择，单独添加该文件不能改变已部署的解释器。

验证：`.venv/bin/python -m pytest -q`。使用 MockTransport 覆盖失败、限流、超时续查；未消耗真实生图额度。
