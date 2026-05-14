---
name: room-currency-deprecation-audit
description: Analyze room type/basic room type currency field definitions, usages, pass-through paths, and direct method calls before safely deprecating currency with minimal code changes.
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

# Room Currency Deprecation Audit

Use this skill when an upstream service wants to remove or stop using `currency` from room type and basic room type models, including database entities such as `htlhoteldb.roomType` and `htlhoteldb.basicroomtype`, remote-call DTOs, Redis cache objects, QMQ/event payloads, and related converters.

The goal is to produce an evidence-based audit first, then make the smallest safe code change. Preserve performance by using targeted searches, avoiding broad rewrites, and not adding runtime reflection or repeated serialization/deserialization.

## Principles

- Start with analysis. Do not delete fields until definitions, reads, writes/pass-throughs, and direct callers are known.
- Keep compatibility for persisted data, external RPC contracts, Redis payloads, and message payloads unless the task explicitly confirms the upstream/downstream contract has been removed.
- Prefer removing production usage and pass-through logic before removing schema fields from public or persisted contracts.
- Treat generated code, ORM mappings, IDL/proto/thrift files, and message schemas as contract surfaces.
- Avoid changing hot-path loops, cache construction, and batch converters beyond the specific `currency` handling being removed.
- Use structured or compiler-aware tools when present; otherwise use `rg` plus focused code reading.

## Fast audit command

From the target service repository, copy or reference this skill's helper script and run:

```bash
python .cursor/skills/room-currency-deprecation-audit/scripts/audit_room_currency.py . --output room-currency-audit.md
```

If the skill is installed outside the target repository, run the script by absolute path:

```bash
python /path/to/room-currency-deprecation-audit/scripts/audit_room_currency.py /path/to/service --output room-currency-audit.md
```

The script is read-only and dependency-free. It gives a first-pass report for:

- room/basic-room related files that define `currency`
- usage and pass-through evidence such as `getCurrency`, `setCurrency`, direct field access, JSON/schema keys, and variables
- methods containing `currency` logic and heuristic direct call-site counts

Use the report as a starting point, then manually inspect important files before editing.

## Manual analysis workflow

### 1. Find room-related `currency` definitions

Search only likely source/config files and ignore build outputs:

```bash
rg -n --hidden --glob '!{.git,target,build,out,dist,node_modules,.gradle}/**' \
  --glob '*.{java,kt,scala,proto,avsc,xml,yml,yaml,json}' \
  -i '(roomtype|room_type|basicroomtype|basic_room_type|htlhoteldb\.roomtype|htlhoteldb\.basicroomtype|currency)' .
```

Build an inventory table:

| Area | Class/file | Field/schema definition | Contract type | Notes |
| --- | --- | --- | --- | --- |
| DB entity | `...RoomType...` | `currency` line | persisted DB/ORM | keep until schema plan is confirmed |
| RPC DTO | `...RoomType...DTO` | `currency` line | external contract | check clients/providers |
| Redis cache | `...RoomType...Cache` | `currency` line | serialized cache | check cache key version and rebuild path |
| QMQ/message | `...RoomType...Message` | `currency` line | async contract | check producers/consumers |

Definition candidates include:

- Java/Kotlin/Scala fields named `currency`
- protobuf/thrift/avro fields named `currency`
- JSON/XML/YAML schema keys named `currency`
- ORM mappings, MyBatis result maps, JPA annotations, or codegen metadata for `currency`

### 2. Classify every usage

For each definition, search exact usages:

```bash
rg -n --hidden --glob '!{.git,target,build,out,dist,node_modules,.gradle}/**' \
  '\b(getCurrency|setCurrency|currency)\b' .
```

Classify evidence into these buckets:

1. **Business read**: conditions, price/currency calculations, display decisions, validation.
2. **Pass-through write**: `target.setCurrency(source.getCurrency())`, builder assignment, mapstruct/manual converter, copy/clone logic.
3. **Persistence/schema only**: ORM mapping, field definition, generated accessor with no caller.
4. **Serialization contract**: RPC response/request, Redis object, QMQ/event body, JSON/proto/avro field.
5. **Tests only**: fixtures, snapshots, assertions.

Only bucket 1 and externally required bucket 4 usually block removal. Bucket 2 can often be removed with a narrow converter edit after the contract decision is clear.

### 3. Check whether related methods are directly called

For each method that reads, writes, or maps `currency`:

1. Record method signature and owning class.
2. Search direct callers:

   ```bash
   rg -n '\bmethodName\s*\(' .
   ```

3. Exclude the method declaration itself, overrides with the same signature, generated code, tests, and comments.
4. If the method is public/protected or is used by a framework, note that static search cannot prove it is unused. Check:
   - controller/RPC annotations
   - scheduled jobs
   - QMQ/listener annotations
   - reflection/JSON binding
   - mapper XML references
   - Spring bean method references

Report direct-call status as:

- `directly called`: direct call sites found in production code
- `not directly called`: no direct production call sites found; mention possible framework/serialization use
- `test-only`: direct calls only from tests
- `unknown/dynamic`: framework, reflection, generated mapper, or external invocation surface

### 4. Decide the minimal safe edit

Use this order of preference:

1. **No code change** if the audit shows the field is still part of an active external/persisted contract and no removal instruction is confirmed.
2. **Stop pass-through only** when callers do not consume `currency`, but DTO/schema compatibility must remain. Remove assignments like `setCurrency(source.getCurrency())`; leave fields.
3. **Remove internal field/accessors** only for internal-only classes with no direct or dynamic callers and no serialization/persistence contract.
4. **Remove contract/schema field** only when upstream and downstream schemas, cache versions, message producers/consumers, and migration plans are confirmed.

For performance-sensitive paths:

- Do not add extra DB queries, cache lookups, object copies, or stream traversals.
- Prefer deleting an assignment over introducing conditional logic.
- If a cache/message shape changes, use existing versioning or rebuild mechanisms instead of per-request compatibility transforms.
- Keep converter loops single-pass.

### 5. Required audit output

Before editing, provide a concise report:

```markdown
## Room currency audit

### Definitions
- `path/Class`: line, contract type, reason it is room/basic-room related

### Usages and pass-throughs
- `path:line`: usage type, source -> target if applicable

### Related methods and direct calls
- `Class.method(...)`: direct-call status, sample call sites, dynamic-call caveats

### Recommended minimal change
- change/no-change decision
- files to edit
- compatibility/performance notes
```

After editing, summarize:

- which `currency` definitions were left intact and why
- which usages/pass-throughs were removed
- verification commands and results

## Review checklist

- [ ] All room/basic-room `currency` definitions were inventoried.
- [ ] DB, RPC, Redis, and QMQ/message contract surfaces were explicitly classified.
- [ ] Every removed assignment had no required consumer.
- [ ] Direct callers were checked for methods that contain `currency` logic.
- [ ] Dynamic/framework usage risk was documented where static search is insufficient.
- [ ] Tests or focused compile checks cover edited converters, mappers, and serializers.
- [ ] No broad refactor, dependency addition, or hot-path performance regression was introduced.
