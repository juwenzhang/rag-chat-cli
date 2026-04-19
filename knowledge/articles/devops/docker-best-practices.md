# Docker 容器化部署最佳实践

## 前言

容器化已成为现代应用部署的标准方式。本文将从镜像优化、网络配置、数据管理、安全加固等多个维度，深入探讨 Docker 生产环境部署的最佳实践。

## 一、镜像优化

### 1.1 多阶段构建

```dockerfile
# Stage 1: Build
FROM node:18-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

COPY . .
RUN npm run build

# Stage 2: Production
FROM node:18-alpine AS production

# 创建非 root 用户
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nextjs -u 1001

WORKDIR /app

# 复制构建产物
COPY --from=builder --chown=nextjs:nodejs /app/dist ./dist
COPY --from=builder --chown=nextjs:nodejs /app/node_modules ./node_modules

USER nextjs

EXPOSE 3000

ENV NODE_ENV=production

CMD ["node", "dist/server.js"]
```

### 1.2 镜像大小优化

```dockerfile
# 避免使用
FROM python:3.11  # 完整镜像，约 1GB

# 推荐使用
FROM python:3.11-slim  # 精简版，约 150MB
FROM python:3.11-alpine  # Alpine 版，约 50MB

# 合并 RUN 指令减少层数
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# .dockerignore 示例
node_modules
.git
.env*
*.log
dist
coverage
```

## 二、网络配置

### 2.1 Docker Network

```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build: .
    networks:
      - frontend
      - backend
    depends_on:
      db:
        condition: service_healthy
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/mydb
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  db:
    image: postgres:15-alpine
    networks:
      - backend
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: mydb
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d mydb"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    networks:
      - backend
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
```

### 2.2 Nginx 反向代理

```nginx
# nginx/Dockerfile
FROM nginx:1.25-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/ /etc/nginx/conf.d/

EXPOSE 80 443
```

```nginx
# nginx/nginx.conf
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # 日志格式
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log warn;

    # Gzip 压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;
    gzip_min_length 1000;

    # 上游服务
    upstream backend {
        server app:3000;
        keepalive 32;
    }

    server {
        listen 80;
        server_name localhost;

        location / {
            proxy_pass http://backend;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # 超时配置
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
        }

        location /api {
            proxy_pass http://backend;
            # API 特定配置
        }

        location /health {
            access_log off;
            return 200 "healthy\n";
            add_header Content-Type text/plain;
        }
    }
}
```

## 三、数据管理

### 3.1 卷挂载策略

```yaml
# 生产环境数据管理
services:
  db:
    image: postgres:15-alpine
    volumes:
      # 命名卷 - 生产推荐
      - db_data:/var/lib/postgresql/data
      # 绑定挂载 - 仅开发环境
      # - ./data:/var/lib/postgresql/data

volumes:
  db_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /host/data/postgres
```

### 3.2 数据备份

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
CONTAINER_NAME="myapp_db_1"

# 创建备份目录
mkdir -p ${BACKUP_DIR}

# 执行备份
docker exec ${CONTAINER_NAME} pg_dump -U user mydb | gzip > ${BACKUP_DIR}/backup_${TIMESTAMP}.sql.gz

# 保留最近 7 天的备份
find ${BACKUP_DIR} -name "backup_*.sql.gz" -mtime +7 -delete

# 列出备份
ls -lh ${BACKUP_DIR}
```

## 四、安全加固

### 4.1 非 Root 用户

```dockerfile
# 创建应用用户
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# 复制文件并设置权限
COPY --from=builder --chown=appuser:appgroup /app/dist /app

USER appuser

# 使用 exit 限制后续命令
```

### 4.2 密钥管理

```yaml
# docker-compose.prod.yml
services:
  app:
    image: myapp:latest
    environment:
      # 使用 Docker Secrets（Swarm 模式）
      # secrets:
      #   - db_password
      # 或使用 K8s Secrets
      - DATABASE_PASSWORD_FILE=/run/secrets/db_password
    secrets:
      - db_password

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

### 4.3 安全扫描

```dockerfile
# 使用安全的基础镜像
FROM scratch

# 添加 CA 证书
COPY --from=ca-certificates:latest /usr/share/ca-certificates /etc/ssl/certs

# 添加非 root 用户
ADD --chown=1000:1000 app /app

USER 1000
CMD ["/app"]
```

## 五、资源限制

### 5.1 内存和 CPU

```yaml
services:
  app:
    build: .
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
    # 或使用 compose v2 语法
    mem_limit: 512m
    mem_reservation: 256m
    cpus: 0.5
    cpu_reservation: 0.25
```

### 5.2 健康检查

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1
```

## 总结

Docker 生产环境部署要点：
1. **镜像优化**：多阶段构建、精简基础镜像、减少层数
2. **网络配置**：合理划分子网、使用反向代理
3. **数据管理**：使用命名卷、定期备份
4. **安全加固**：非 root 运行、密钥管理、安全扫描
5. **资源限制**：合理配置内存 CPU、健康检查