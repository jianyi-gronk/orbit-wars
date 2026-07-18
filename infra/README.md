# Infrastructure

本目录承载本地依赖编排和生产容器配置。当前 Compose 环境提供 PostgreSQL、Redis 与 S3 兼容对象存储。

本地配置使用根目录 `.env`；测试环境使用独立的 `.env.test.example` 端口和 volume。所有示例密码只能用于本机开发。
