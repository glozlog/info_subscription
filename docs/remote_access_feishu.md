# 用飞书在移动端远程访问本地控制台（安全方案）

本项目控制台默认只在本机 `http://localhost:8501` 提供服务。如果你希望在非本地网络（蜂窝网络/外网）用手机访问，必须解决两件事：

1. **网络可达**：手机能访问到你家/公司这台 Windows 电脑上的 8501 服务
2. **访问控制**：避免把控制台裸露在公网（强烈不建议）

推荐优先选择 “VPN（零暴露）”，其次选择 “隧道（可暴露但有安全层）”。

---

## 方案 A（推荐）：Tailscale / ZeroTier（零暴露，最省心）

- 在 Windows 电脑安装并登录 Tailscale（或 ZeroTier）
- 在手机安装并登录同一个网络
- 用手机浏览器访问：`http://<电脑的虚拟网卡IP>:8501`
- 把这个链接发到飞书里，手机点开即可

优点：不暴露公网，安全；缺点：手机需要开 VPN。

---

## 方案 B：Cloudflare Tunnel（可外网访问，配合飞书登录）

### 1) 开通隧道

- 在 Cloudflare Zero Trust 创建 Tunnel，把一个公网域名（如 `console.example.com`）指向本机 `http://localhost:8501`

### 2) 给控制台加飞书登录（OAuth）

控制台已内置“飞书 OAuth 登录门禁”。启用方式：

1. 在飞书开放平台创建 **企业自建应用**，开启“网页应用”能力
2. 在应用“安全设置”里添加重定向 URL：`https://console.example.com/`（以你的实际域名为准）
3. 在本机配置以下三项（环境变量或 `./.streamlit/secrets.toml`）

`./.streamlit/secrets.toml` 示例：

```toml
[feishu]
app_id = "cli_xxx"
app_secret = "xxx"
redirect_uri = "https://console.example.com/"
```

说明：
- 授权入口使用飞书标准 OAuth 授权码流程：`https://accounts.feishu.cn/open-apis/authen/v1/authorize`（获取 code）与 `https://open.feishu.cn/open-apis/authen/v2/oauth/token`（兑换 token）
- 用户信息接口：`https://open.feishu.cn/open-apis/authen/v1/user_info`

---

## 安全提醒

- 不建议把 `http://localhost:8501` 直接端口映射到公网
- 无论使用哪种外网方案，都应该先启用飞书登录门禁或额外网关鉴权
