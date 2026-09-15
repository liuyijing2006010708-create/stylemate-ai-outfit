# 参与贡献

感谢你改进 StyleMate。请保持变更聚焦，并在 Pull Request 中说明可复现的验证方式。

## 本地开发

1. Fork 本仓库并 clone 到本地。
2. 从最新 `main` 创建短期分支，例如 `feature/improve-upload-feedback`。
3. 创建虚拟环境并安装开发依赖：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Windows PowerShell 激活命令：

```powershell
.venv\Scripts\Activate.ps1
```

## 提交前检查

```bash
python -m pip check
python -m compileall -q app.py cloud_app.py stylemate stylegen scripts
python -m pytest -q
```

- 修改行为时同步增加或更新测试。
- 修改配置、接口或用户流程时同步更新相关文档。
- 不要提交 `.env`、API Key、Token、私人图片、训练数据、模型权重或生成的私有输出。
- 不要在测试中调用真实付费 API；使用 Fake client 或 `httpx.MockTransport`。

## 提交 Pull Request

Push 分支并创建 Pull Request，填写模板中的 Summary、Changes、Testing 和 Checklist。标题应简洁说明修改目的；正文应描述用户可见影响、验证命令和已知限制。

Pull Request 需要通过 GitHub Actions。请不要通过强推或直接修改受保护分支绕过检查。
