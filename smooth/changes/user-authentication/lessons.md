# 经验沉淀

## 实现认证前先锁定首发身份提供方

- 来源：pitfalls.md#登录渠道不能从参考项目直接推断
- 适用范围：workflow | doc-generation
- Harness 改进：
  - 类型：document-rule
  - 目标：认证类 product.md
  - 方案：强制区分“参考产品支持的渠道”“首发开放渠道”“保留但关闭的渠道”，并要求验收标准只覆盖首发渠道。
- 机械方案：在进入 technical/apply 前检查 product.md 是否存在唯一明确的首发 provider 列表。
