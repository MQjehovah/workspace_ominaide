# OAuth 连接器

连接器让 Bot 在用户授权后访问外部服务。当前实现 Google（Gmail / Calendar /
Drive），框架可以继续添加 Slack、Notion、Microsoft 等。

## 服务端配置

在 `/home/jmq/omniaide/.env` 中设置：

```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
APP_BASE_URL=https://mqgeek.com/ominaide
OAUTH_REDIRECT_BASE=https://mqgeek.com/ominaide/api
```

Google Cloud Console 的 OAuth 客户端需要配置回调地址：

```text
https://mqgeek.com/ominaide/api/connectors/oauth/callback
```

测试模式下只有添加为 Test user 的 Google 账号可以授权，refresh token 可能 7 天过期；
正式使用需要发布 OAuth 应用。

## 使用

1. Web → 设置 → 连接器
2. 点「连接账号」
3. 在 Google 授权页同意
4. 回调后回到设置页

账号 token 使用 `core.crypto` 加密存储，不会通过 API 返回明文。

## API

```text
GET    /api/connectors
POST   /api/connectors/oauth/start      { "provider": "google" }
GET    /api/connectors/oauth/callback
DELETE /api/connectors/{account_id}
```

## 工具

```text
google_gmail_search
google_gmail_read
google_gmail_send       # external，需要审批
google_calendar_list
google_calendar_create
google_drive_search
google_drive_read
google_drive_upload
```

未连接账号时，这些工具会返回「还没有连接 Google 账号」。
