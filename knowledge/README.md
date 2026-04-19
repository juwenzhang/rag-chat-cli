# 知识库配置

## 目录结构

```
knowledge/
├── articles/           # 技术文章
│   ├── frontend/      # 前端技术
│   ├── backend/       # 后端技术
│   ├── mobile/       # 移动开发
│   ├── devops/       # DevOps
│   └── architecture/ # 架构设计
├── categories.json    # 分类配置
└── tags.json         # 标签配置
```

## 分类配置

```json
{
  "categories": [
    { "id": "frontend", "name": "前端技术", "icon": "🎨", "description": "Web前端技术栈" },
    { "id": "backend", "name": "后端技术", "icon": "⚙️", "description": "服务端技术栈" },
    { "id": "mobile", "name": "移动开发", "icon": "📱", "description": "iOS/Android/跨平台" },
    { "id": "devops", "name": "DevOps", "icon": "🚀", "description": "运维与部署" },
    { "id": "architecture", "name": "架构设计", "icon": "🏛️", "description": "系统架构与设计" }
  ]
}
```

## 标签配置

```json
{
  "tags": [
    { "id": "rust", "name": "Rust", "category": "backend" },
    { "id": "nodejs", "name": "Node.js", "category": "backend" },
    { "id": "vue", "name": "Vue", "category": "frontend" },
    { "id": "react", "name": "React", "category": "frontend" },
    { "id": "flutter", "name": "Flutter", "category": "mobile" },
    { "id": "android", "name": "Android", "category": "mobile" },
    { "id": "ios", "name": "iOS", "category": "mobile" },
    { "id": "docker", "name": "Docker", "category": "devops" },
    { "id": "kubernetes", "name": "Kubernetes", "category": "devops" },
    { "id": "microservice", "name": "微服务", "category": "architecture" },
    { "id": "deeplink", "name": "Deeplink", "category": "mobile" },
    { "id": "h5", "name": "H5", "category": "frontend" },
    { "id": "offline", "name": "离线包", "category": "mobile" },
    { "id": "rpc", "name": "RPC", "category": "architecture" },
    { "id": "grpc", "name": "gRPC", "category": "architecture" },
    { "id": "webpack", "name": "Webpack", "category": "frontend" },
    { "id": "vite", "name": "Vite", "category": "frontend" },
    { "id": "nestjs", "name": "NestJS", "category": "backend" },
    { "id": "koa", "name": "Koa", "category": "backend" },
    { "id": "nextjs", "name": "Next.js", "category": "frontend" },
    { "id": "langchain", "name": "LangChain", "category": "ai" },
    { "id": "microfrontend", "name": "微前端", "category": "frontend" }
  ]
}
```

## 文章元数据格式

```json
{
  "id": "rust-ownership-system",
  "title": "Rust 所有权系统深度解析",
  "category": "backend",
  "tags": ["rust", "memory-management"],
  "author": "Tech Writer",
  "created_at": "2024-01-15",
  "updated_at": "2024-01-15",
  "summary": "深入理解 Rust 的所有权、借用和生命周期机制",
  "difficulty": "advanced",
  "reading_time": "15min"
}
```
