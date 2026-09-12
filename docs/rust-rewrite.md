# Rust 重写决策记录

> 决策时间：2026-09-12。结论：**暂不重写**，待功能基本完整、版本到达 1.0 且数据模型稳定后再整体切换到 Rust。

## 背景

后端当前为 Python（约 2200 行），桌面端通过 PyInstaller 把 Python 后端打成单文件二进制随
Tauri 分发。长期看不希望把 Python 运行时分发给客户，目标架构是纯 Rust 后端。

## 决策理由（为什么推迟）

1. **数据模型未稳定**：项目处于 v0.3 早期，接口与数据模型随时可能不兼容变更（README 已声明
   无迁移保证）。此阶段重写等于把所有变更成本翻倍。
2. **质量护城河依赖 Python 生态**：URL 正文提取（trafilatura）与图片 OCR（rapidocr）在 Rust
   生态没有等价物，立即重写会导致功能质量实际下降。
3. **收益目前只有部署体积**：Rust 单二进制约 15MB，vs PyInstaller 产物（本地推理已移除后
   预计 50-100MB）。有意义但非数量级改善，不构成重写的紧迫理由。
4. 后端计算密度极低（LLM/ASR 都是拼 HTTP 调用），Python 性能劣势不构成瓶颈。

## 重写触发条件（满足其一再启动）

- 数据模型与 API 稳定到 1.0，出现兼容性承诺；
- 桌面端安装包体积/启动速度成为用户反馈的高频问题；
- 需要实时图算法或节点规模超过 10⁵（图数据库迁移的同一触发条件，见 README_zh.md 数据模型一节）。

## 模块映射（届时照此执行）

| 模块 | 现状（Python） | Rust 对应 | 风险 |
|---|---|---|---|
| Web 框架 | FastAPI | axum / actix-web | 低 |
| 存储层 | sqlite-vec + FTS5 + 递归 CTE | rusqlite + 加载 sqlite-vec 扩展，SQL 可复用 | 低 |
| LLM / ASR 客户端 | requests 拼 OpenAI 兼容协议 | reqwest | 低 |
| 间隔重复 | fsrs（PyPI） | rs-fsrs（官方 Rust 实现） | 低 |
| 中文分词 | jieba | jieba-rs | 低 |
| Embedding | jieba + hashing（512 维） | 平移实现，需保持向量可复现 | 中 |
| URL 正文提取 | trafilatura | readability / trafilatura 部分移植 | **高：抽取质量可能下降** |
| 图片 OCR | rapidocr-onnxruntime | ort（ONNX Runtime 绑定）+ 自管模型 | 中 |
| 打包 | PyInstaller sidecar | cargo 交叉编译，单二进制进 Tauri | 收益项 |

## 迁移路径（渐进式，不裸重写）

1. 先把「存储 + 建链 + 回取」层用 rusqlite 写成 Tauri sidecar（或直接编进 Tauri 壳，
   走 Tauri command），Web 面板改调 command；
2. LLM / ASR / URL 提取等 I/O 型模块最后迁移，或先以独立小服务共存；
3. 全程共用同一 SQLite 文件格式（vec0 / FTS5 依赖随平台捆绑的扩展），Python 版与 Rust 版
   过渡期内可读写同一数据库；
4. 迁移完成、CI 稳定后，删除 Python 后端与 PyInstaller 打包流水线。
