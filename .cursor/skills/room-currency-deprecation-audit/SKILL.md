---
name: room-currency-deprecation-audit
description: 分析房型/基础房型相关类中 currency 字段的定义、使用、透传链路和相关方法直接调用情况，用于以最小改动安全下线 currency。
paths:
  - "**/*.java"
  - "**/*.kt"
  - "**/*.scala"
  - "**/*.proto"
  - "**/*.avsc"
  - "**/*.xml"
  - "**/*.yml"
  - "**/*.yaml"
  - "**/*.json"
---

# 房型 currency 下线分析

当上游服务需要下线房型和基础房型相关模型中的 `currency` 字段时使用本 skill。分析范围包括但不限于数据库实体类，例如 `htlhoteldb.roomType`、`htlhoteldb.basicroomtype`，以及远程调用实体、Redis 缓存实体、QMQ 消息体、转换器和复制逻辑等。

目标是先形成有证据的审计结论，再决定是否改代码以及如何最小化改动。为了保证性能，优先使用定向搜索和局部阅读，不做大范围重构，不引入运行期反射、额外 DB 查询、重复序列化/反序列化或多余对象复制。

## 原则

- 先分析再改动。未确认定义、读取、写入/透传和直接调用之前，不删除字段。
- 对持久化数据、外部 RPC 契约、Redis 缓存载荷和消息载荷保持兼容，除非任务明确说明上下游契约已经下线。
- 优先移除生产逻辑中的使用和透传，再考虑删除公开或持久化契约中的字段。
- 将生成代码、ORM 映射、IDL/proto/thrift 文件、消息 schema 视为契约面。
- 不要因为下线 `currency` 而改动热路径循环、缓存构建、批量转换等无关逻辑。
- 有结构化工具或编译器能力时优先使用；否则使用 `rg` 做定向搜索，并配合重点文件阅读。

## 分析流程

### 1. 找出房型相关的 `currency` 定义

只搜索可能的源码和配置文件，忽略构建产物：

```bash
rg -n --hidden --glob '!{.git,target,build,out,dist,node_modules,.gradle}/**' \
  --glob '*.{java,kt,scala,proto,avsc,xml,yml,yaml,json}' \
  -i '(roomtype|room_type|basicroomtype|basic_room_type|htlhoteldb\.roomtype|htlhoteldb\.basicroomtype|currency)' .
```

整理定义清单：

| 范围 | 类/文件 | 字段或 schema 定义 | 契约类型 | 备注 |
| --- | --- | --- | --- | --- |
| DB 实体 | `...RoomType...` | `currency` 所在线 | 持久化 DB/ORM | 未确认表结构方案前不要删除 |
| RPC DTO | `...RoomType...DTO` | `currency` 所在线 | 外部接口契约 | 检查调用方和提供方 |
| Redis 缓存 | `...RoomType...Cache` | `currency` 所在线 | 序列化缓存 | 检查缓存 key 版本和重建路径 |
| QMQ/消息 | `...RoomType...Message` | `currency` 所在线 | 异步消息契约 | 检查生产者和消费者 |

定义候选包括：

- Java/Kotlin/Scala 中名为 `currency` 的字段。
- protobuf/thrift/avro 中名为 `currency` 的字段。
- JSON/XML/YAML 中的 `currency` schema key。
- ORM 映射、MyBatis resultMap、JPA 注解、代码生成元数据中与 `currency` 有关的配置。

### 2. 分类所有使用和透传

对每个定义继续搜索精确使用点：

```bash
rg -n --hidden --glob '!{.git,target,build,out,dist,node_modules,.gradle}/**' \
  '\b(getCurrency|setCurrency|currency)\b' .
```

将命中结果按以下类别归类：

1. **业务读取**：条件判断、价格/币种计算、展示决策、校验逻辑。
2. **透传写入**：`target.setCurrency(source.getCurrency())`、builder 赋值、MapStruct/手写 converter、copy/clone 逻辑。
3. **仅持久化或 schema 定义**：ORM 映射、字段定义、没有调用方的生成 getter/setter。
4. **序列化契约**：RPC 请求/响应、Redis 对象、QMQ/event body、JSON/proto/avro 字段。
5. **仅测试使用**：fixture、snapshot、断言。

通常只有第 1 类和仍被外部依赖的第 4 类会阻塞下线。第 2 类一般可以在契约判断清楚后，通过删除局部转换赋值来完成最小改动。

### 3. 分析相关方法是否被直接调用

对每个读取、写入或映射 `currency` 的方法：

1. 记录方法签名和所属类。
2. 搜索直接调用方：

   ```bash
   rg -n '\bmethodName\s*\(' .
   ```

3. 排除方法声明本身、同签名 override、生成代码、测试代码和注释。
4. 如果方法是 public/protected，或可能被框架调用，需要说明静态搜索不能证明其未使用，并额外检查：
   - controller/RPC 注解
   - 定时任务
   - QMQ/listener 注解
   - 反射/JSON 绑定
   - mapper XML 引用
   - Spring bean 方法引用

直接调用状态按以下方式记录：

- `直接调用`：生产代码中找到直接调用点。
- `未发现直接调用`：生产代码中没有直接调用点，但要说明可能存在框架/序列化调用。
- `仅测试调用`：只有测试代码调用。
- `未知/动态调用`：涉及框架、反射、生成 mapper 或外部调用入口。

### 4. 决定最小安全改动

按以下优先级决策：

1. **不改代码**：如果字段仍属于活跃外部/持久化契约，且没有明确下线指令。
2. **只停止透传**：调用方不再消费 `currency`，但 DTO/schema 还需要兼容时，只删除 `setCurrency(source.getCurrency())` 这类赋值，保留字段。
3. **删除内部字段/访问器**：仅限纯内部类，且无直接/动态调用、无序列化或持久化契约。
4. **删除契约/schema 字段**：只有在上下游 schema、缓存版本、消息生产者/消费者和迁移方案都确认后再做。

性能敏感路径要求：

- 不新增 DB 查询、缓存查询、对象复制或额外 stream 遍历。
- 优先删除赋值，不为下线字段新增条件分支。
- 如果缓存或消息结构变化，使用已有版本机制或重建机制，不在每次请求中做兼容转换。
- 保持 converter 循环单次遍历。

### 5. 必须输出的审计结论

改代码前先给出简洁报告：

```markdown
## 房型 currency 审计

### 字段定义
- `path/Class`：行号、契约类型、为什么属于房型/基础房型相关

### 使用和透传
- `path:line`：使用类型，如有透传则写明 source -> target

### 相关方法和直接调用
- `Class.method(...)`：直接调用状态、调用点样例、动态调用风险

### 推荐的最小改动
- 改/不改的决策
- 需要编辑的文件
- 兼容性和性能说明
```

改代码后总结：

- 哪些 `currency` 定义被保留，以及原因。
- 哪些使用/透传被删除。
- 验证命令和结果。

## 检查清单

- [ ] 已盘点所有房型/基础房型相关 `currency` 定义。
- [ ] 已明确分类 DB、RPC、Redis、QMQ/消息等契约面。
- [ ] 每个被删除的赋值都确认没有必要消费方。
- [ ] 已检查包含 `currency` 逻辑的方法是否存在直接调用。
- [ ] 对静态搜索不足以判断的动态/框架调用风险已说明。
- [ ] 已用测试或定向编译覆盖被修改的 converter、mapper、serializer。
- [ ] 未引入大范围重构、新依赖或热路径性能退化。
