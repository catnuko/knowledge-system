# knowledge-engine Web 端

Web 端与桌面端共用同一份静态面板（`knowledge_engine/web/static/`）。两种交付方式：

## 方式一：零配置 Web 模式（推荐）

后端直接托管面板，一条命令启动：

```bash
python3 -m knowledge_engine.web --port 8000
# 浏览器打开 http://127.0.0.1:8000
```

## 方式二：静态打包部署

把面板打成纯静态产物，交给 Nginx / 对象存储 / CDN 托管：

```bash
bash web/build.sh          # → web/dist/（index.html + lib/）
```

静态部署时 `/api/*` 需反向代理到后端，Nginx 示例见 `deploy.example.conf`。

```
web/
├── build.sh               # 组装静态产物到 web/dist/
├── deploy.example.conf    # Nginx 反代示例
└── dist/                  # 构建产物（不入库）
```
