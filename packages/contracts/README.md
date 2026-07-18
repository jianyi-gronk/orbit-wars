# Shared Contracts

跨进程契约只有一条生成路径：

```text
orbit_contracts/models.py → schemas/contracts-v1.json → src/generated/contracts-v1.ts
```

修改 Pydantic 模型后执行：

```bash
pnpm contracts:generate
pnpm check
```

JSON Schema 和 TypeScript 文件必须提交；Python 快照测试与 TypeScript 生成检查会阻止源模型和产物漂移。`src/validation.ts` 使用同一 JSON Schema 提供浏览器/Node 运行时校验。
