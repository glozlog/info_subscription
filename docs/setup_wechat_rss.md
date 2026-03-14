# Wechat2RSS 部署与接入指南

本项目已统一使用 Wechat2RSS 将微信公众号内容转换为 RSS，然后由本程序定时抓取、摘要与归档。

## 1. 前置条件

- Windows 已安装并启动 Docker Desktop
- 已获得 Wechat2RSS 授权邮箱与激活码

## 2. 本地启动 Wechat2RSS

本仓库已提供本地部署目录：`D:\TRAE\信息订阅\wechat2rss\`

1. 双击运行 [启动Wechat2RSS.bat](file:///D:/TRAE/%E4%BF%A1%E6%81%AF%E8%AE%A2%E9%98%85/%E5%90%AF%E5%8A%A8Wechat2RSS.bat)  
2. 首次启动会自动创建 `wechat2rss/.env` 并打开编辑器，填入：
   - `LIC_EMAIL=...`
   - `LIC_CODE=...`
   - `RSS_HOST=localhost:8080`
3. 再次双击启动即可打开控制台：`http://localhost:8080`

## 3. 获取控制台 Token（服务密码）

Wechat2RSS 会在容器日志里打印 Token。启动脚本会自动读取并复制到剪贴板，你也可以手动查看：

```powershell
docker logs wechat2rss | Select-String "Token:"
```

## 4. 添加公众号订阅并获取 BID

1. 在 `http://localhost:8080` 登录并添加公众号（一般通过文章链接添加）
2. 添加完成后，会得到该公众号的 BID（纯数字）

## 5. 接入本项目（config.yaml）

在 `D:\TRAE\信息订阅\config.yaml` 添加一条订阅：

```yaml
- category: 金融
  name: 投资聚义厅
  platform: wechat2rss
  url: '3279420503'
```

抓取时会自动请求：

- `http://localhost:8080/feed/<BID>.xml`

也可以在控制台侧边栏直接输入 BID 添加（会自动读取 RSS 标题作为名称）。
