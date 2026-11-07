# 生产部署结构

生产环境在 `192.168.2.10` 上，容器和目录分离：

```text
/data/docker/nginx/www              # 个人主页，不是 OmniAide
/data/docker/omniaide/frontend      # OmniAide 前端静态文件
/data/docker/omniaide/frontend-nginx/default.conf
```

容器：

```text
nginx-web          # 主机入口，个人主页 + /ominaide/ 反向代理
omniaide-frontend  # 独立 Nginx 容器，监听 127.0.0.1:8082
omniaide-backend   # FastAPI
postgres / redis / minio / gitea / homeassistant / samba
```

Nginx `nginx-web` 的关键配置：

```nginx
location /ominaide/ {
    proxy_pass http://127.0.0.1:8082/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
}
```

## 前端发布

不要把 OmniAide 解压到 `/data/docker/nginx/www/`。正确流程：

```bash
# 本地构建
cd frontend
npm run build

# 上传 dist 到服务器
scp dist.tgz jmq@192.168.2.10:/tmp/

# 服务器
sudo rm -rf /data/docker/omniaide/frontend/*
sudo tar xzf /tmp/dist.tgz -C /data/docker/omniaide/frontend
sudo chown -R root:root /data/docker/omniaide/frontend
docker restart omniaide-frontend
```

验证：

```bash
curl -I https://mqgeek.com/
curl -I https://mqgeek.com/ominaide/
curl -I https://mqgeek.com/ominaide/assets/index-*.js
```

根路径必须返回个人主页；`/ominaide/` 必须返回 OmniAide 的 `index.html`，JS 必须是 `application/javascript`，不能是 HTML。

## 个人主页

个人主页位于：

```text
/data/docker/nginx/www/index.html
```

发布前端时不要删除或覆盖这个目录。
