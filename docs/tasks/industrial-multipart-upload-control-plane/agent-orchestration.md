# Agent Orchestration for Industrial Multipart Upload Control Plane

本文档定义 `docs/tasks/industrial-multipart-upload-control-plane/README.md` 中 T00-T17 的多 agent 执行方式。它不替代 PRD，也不改变任务验收标准；所有实现仍以 `docs/prd/industrial-multipart-upload-control-plane/` 和任务 README 为准。

## 1. Master Agent 职责与禁令

Master agent 是编排者，不是实现者。

允许职责：

- 拆解 T00-T17 为更小、可审查、可恢复的 agent 任务。
- 为每个 sub agent 指定输入文档、依赖、范围、交付物、验收命令和 handoff 要求。
- 判断依赖是否满足，决定哪些任务可以并行派发。
- 审查 sub agent 的结果、handoff、测试证据和风险记录。
- 说明合并目的、合并顺序和最终变更意图。
- 在最终合并前做整体一致性审查，确认 PRD 硬约束没有被破坏。

禁止事项：

- 不直接写代码。
- 不直接改文件，包括文档文件。
- 不直接解决冲突。
- 不直接修小 bug、补测试、改格式或做临时 cleanup。
- 不绕过 Validation agent 或 Merge agent 直接合并实现分支。
- 不把 blocked 或 rejected 的结果包装成完成状态。

Master agent 如果发现问题，只能派发 Repair agent、要求原 agent 补充 handoff，或拒绝进入合并流程。

## 2. Sub Agent 类型

| 类型 | 职责 | 输出 |
|---|---|---|
| Implementation Agent | 实现一个细粒度功能切片，包含必要代码、迁移、配置、测试和局部文档。 | 实现分支、测试证据、handoff。 |
| Documentation Agent | 编写或更新任务执行文档、handoff 模板、运行说明、设计补充说明。 | 文档变更、引用来源、handoff。 |
| Validation Agent | 独立验证 Implementation 或 Documentation 结果，不扩大功能范围。 | 验证报告、复现命令、accepted/partial/blocked/rejected 判定。 |
| Merge Agent | 在 Master review 通过后执行合并、处理非语义性冲突、保留合并记录。 | 合并分支、冲突处理记录、merge handoff。 |
| Repair Agent | 针对 Validation 或 Master review 发现的问题做有限修复。 | 修复分支、变更说明、回归测试证据、recovery handoff。 |

Repair Agent 不能顺手做新功能。如果问题超出原任务边界，必须交回 Master agent 重新拆分。

## 3. Handoff-first 规则

每个 agent 完成或失败都必须先留下 handoff/recovery 文档，再等待审查。任务不能是整成整败；可以提交部分可用结果，但必须明确剩余风险和恢复入口。

状态只允许以下四类：

- `accepted`: 范围内目标完成，验收命令通过，风险可接受。
- `partial`: 有可保留的局部成果，但仍有明确未完成项。
- `blocked`: 因外部依赖、缺失信息、环境问题或上游未完成而无法继续。
- `rejected`: 结果不应合入，原因可能是破坏硬约束、测试失败且无法局部修复、范围漂移或实现方向错误。

规则：

- 没有 handoff 的分支不能进入 Validation。
- 没有 Validation handoff 的实现不能进入 Master review。
- `partial` 可以保留分支和证据，但不能被当成完成依赖。
- `blocked` 必须写清楚恢复条件和下一个 agent 应从哪里继续。
- `rejected` 必须保留失败证据，供 Repair 或重新实现时避免重复错误。

## 4. Handoff 文档位置、命名和模板

handoff 文档统一放在：

```text
docs/tasks/industrial-multipart-upload-control-plane/handoffs/
```

命名格式：

```text
YYYYMMDD-HHMM-{task-id}-{agent-type}-{scope}-{status}.md
```

示例：

```text
20260624-1530-T04-implementation-storage-adapter-partial.md
20260624-1700-T04-validation-storage-adapter-rejected.md
20260624-1815-T04-repair-storage-adapter-accepted.md
```

推荐模板：

```markdown
# Handoff: {task-id} {scope}

Status: accepted | partial | blocked | rejected
Agent type: Implementation | Documentation | Validation | Merge | Repair
Branch: {branch-name}
Worktree: {path-or-none}
Started: YYYY-MM-DD HH:MM TZ
Finished: YYYY-MM-DD HH:MM TZ

## Scope

- Intended scope:
- Explicitly out of scope:
- PRD/task files read:

## Changes

- Files changed:
- Behavior changed:
- Compatibility notes:

## Verification

- Commands run:
- Results:
- Commands not run and why:

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
- Clients receive no MinIO/S3 credentials:
- Complete uses object storage ListParts as authority:
- Authorization uses permission_grants:
- Internal IDs remain UUIDs:
- MQTT/Go/edge remain optional and dependency-gated:

## Risks and Follow-up

- Remaining risks:
- Known gaps:
- Suggested next agent:

## Recovery Notes

- If accepted, next dependency unlocked:
- If partial, reusable pieces:
- If blocked, unblock condition:
- If rejected, do not repeat:
```

## 5. Worktree 和 Branch 命名规范

每个 Implementation、Repair、Documentation 或 Validation agent 使用独立分支。Master agent 不直接写文件，因此不需要实现分支。

分支命名：

```text
codex/industrial-upload/{task-id}-{agent-type}-{scope}
```

示例：

```text
codex/industrial-upload/T01-implementation-domain-kernel
codex/industrial-upload/T04-validation-storage-adapter
codex/industrial-upload/T04-repair-listparts-complete
codex/industrial-upload/docs-agent-orchestration
```

worktree 命名：

```text
../upload-control-plane-{task-id}-{agent-type}-{scope}
```

示例：

```text
../upload-control-plane-T01-implementation-domain-kernel
../upload-control-plane-T07-implementation-browser-uploader
```

命名规则：

- `{task-id}` 使用 T00-T17。
- `{agent-type}` 使用 `implementation`、`documentation`、`validation`、`merge`、`repair`。
- `{scope}` 用短横线连接，描述最小职责范围。
- 可选任务仍保留原 T15-T17 编号，不用提前改成核心任务。
- 不创建真实 worktree，除非 Master agent 明确派发并确认依赖已经满足。

## 6. 可并行策略

原则：能并行就并行，但不能在依赖未满足时提前做。并行任务必须使用独立分支和 handoff，不能共享未合并的隐式状态。

核心链：

```text
T00 -> T01 -> T02 -> T03 -> T04 -> T05 -> T06
    -> T09 -> T10 -> T11 -> T12 -> T13 -> T14
```

核心链上的任务默认串行，因为每一层会固化下一层的接口、模型或运行边界。

明确并行点：

- T07 Browser 和 T08 Python CLI 可在 T06 accepted 后并行。
- T09 Dataset 可在 T06 accepted 后启动，不依赖 T07/T08。
- T11 Workers 可在 T06、T09、T10 accepted 后启动。
- T12 Validation 可在 T09、T11 accepted 后启动。
- T13 Observability 在 T11、T12 accepted 后启动。
- T14 Failure/Benchmark 在 T13 accepted 后启动。
- T15 MQTT 只能在 T10、T11、T13 accepted 后启动。
- T16 Go uploader 只能在 T08、T14 accepted 后启动。
- T17 Go gateway 只能在 T13 accepted 且有明确部署理由后启动。

禁止并行：

- 不能在 T04 未 accepted 时实现依赖真实 storage complete 的 T06。
- 不能在 T03 未 accepted 时实现绕过权限模型的上传 API。
- 不能用 T15 MQTT、T16 Go 或 T17 gateway 补偿 Python backend、HTTP API、授权或 outbox 的缺口。
- 不能让 Browser/CLI 添加专属后端接口来绕过 T06。

## 7. 细粒度 Agent 拆分

下表把 T00-T17 拆成接力式小 agent。每个 agent 应尽量只完成一层职责；如果执行中发现范围过大，先留下 `partial` handoff，再由 Master agent 继续拆分。

| Task | Agent scope | 类型 | 依赖 | 主要职责 |
|---|---|---|---|---|
| T00 | Foundation runtime scaffold | Implementation | none | Python 3.13、FastAPI health、settings、compose、Makefile、基础质量门禁。 |
| T00 | Foundation validation | Validation | T00 impl | 验证 `make dev-up`、`make test`、health、MinIO Console 可访问性证据。 |
| T01 | Domain part math and state | Implementation | T00 | part size/range、session state machine、task/object aggregate rules。 |
| T01 | Domain dataset/auth rules | Implementation | T01 part base | dataset/validation/recovery exposure、object key sanitizer、fingerprint、permission-code evaluator。 |
| T01 | Domain validation | Validation | T01 impl | 边界值、非法状态迁移、权限继承和 deny-over-allow 测试。 |
| T02 | Persistence schema | Implementation | T01 | SQLAlchemy models、Alembic、UUID PK/FK、无 upload_batches/batch_id。 |
| T02 | Persistence seed | Implementation | T02 schema | dev tenant/API key/storage policy/project/dataset/device/permission grants。 |
| T02 | Persistence validation | Validation | T02 impl | 空库迁移、seed、状态字段分离、UUID 内部 ID。 |
| T03 | AuthN/AuthZ foundation | Implementation | T02 | API key、tenant active、request ID、stable error response。 |
| T03 | AuthZ permission filtering | Implementation | T03 foundation | permission_grants 服务、project list/detail、effective_permissions。 |
| T03 | AuthZ validation | Validation | T03 impl | project.view 过滤、upload 权限 gate、每次控制面请求重新鉴权设计。 |
| T04 | Storage adapter interface | Implementation | T02,T03 | ObjectStorage protocol、capabilities、内部 client 与 presign client 分离。 |
| T04 | Storage multipart operations | Implementation | T04 interface | create/presign/list/complete/abort/head，ListParts 分页。 |
| T04 | Storage validation | Validation | T04 impl | MinIO multipart 集成测试、host-reachable presign、禁止字符串改签名 URL host。 |
| T05 | Upload Task API | Implementation | T03,T04 | `POST /v1/projects/{project_id}/upload-tasks`、事务创建 task/object/dataset/session。 |
| T05 | Upload Task idempotency/quota | Implementation | T05 api | idempotency、quota before storage、policy selection、server object key、audit/events。 |
| T05 | Upload Task validation | Validation | T05 impl | 单/多文件、重试、quota 拒绝不泄漏 storage multipart、无裸 session 创建。 |
| T06 | Runtime presign/status/ack | Implementation | T05 | status、presign、ack、parts list，权限重评估。 |
| T06 | Runtime lifecycle actions | Implementation | T06 presign | pause/resume/complete/abort，session lock，idempotency，storage-authoritative complete。 |
| T06 | Runtime validation | Validation | T06 impl | paused presign 拒绝、fresh URL、missing_parts 409、ListParts authoritative complete、tenant isolation。 |
| T07 | Browser manual uploader | Implementation | T06 | Vite tool、file picker、API fields、direct PUT、pause/resume/abort/status controls。 |
| T07 | Browser validation | Validation | T07 impl | 浏览器直传 MinIO、不经 FastAPI、CORS、无专属后端路由、URL query redaction。 |
| T08 | Python CLI upload/resume | Implementation | T06 | `uploadctl upload/resume/status/pause/resume-session/abort`、manifest、concurrency。 |
| T08 | CLI validation | Validation | T08 impl | interruption resume、URL expiry re-presign、manifest 不存 presigned URLs、可读进度。 |
| T09 | Dataset lifecycle API | Implementation | T06 | list/search/detail/update/download/archive/delete/restore/purge、tags。 |
| T09 | Dataset exposure policy | Implementation | T09 api | dataset_status、validation_status、recovery_status、legal hold/object lock gate、audit。 |
| T09 | Dataset validation | Validation | T09 impl | download 权限、quarantine/rejected 阻断、soft delete/restore/purge 策略。 |
| T10 | Device identity | Implementation | T09 | register/update/disable/enable、credential provisioning/rotation、once-only secret return。 |
| T10 | Device upload authorization | Implementation | T10 identity | device-to-project auth、device upload creates ordinary UploadTasks/Sessions。 |
| T10 | Device validation | Validation | T10 impl | revoked/disabled/expired credential、source_device_id UUID、source_device_code metadata。 |
| T11 | Workers lifecycle | Implementation | T06,T09,T10 | expire sessions、abort expired multipart、recycle/purge、recovery reconciliation。 |
| T11 | Workers outbox | Implementation | T11 lifecycle | outbox append/dispatcher/retry/dead-letter，domain transaction atomicity。 |
| T11 | Workers validation | Validation | T11 impl | repeated worker safety、restore mismatch、outbox failure 不回滚 domain action。 |
| T12 | Validation worker | Implementation | T09,T11 | quarantine/release、metadata extractor、HDF5 stub/implementation、inspection hook。 |
| T12 | Validation API | Implementation | T12 worker | validation result、retry validation、preview metadata persistence。 |
| T12 | Validation validation | Validation | T12 impl | completed dataset enters validation、failure records errors、blocked exposure、retry idempotent。 |
| T13 | Observability | Implementation | T11,T12 | JSON logs、metrics、latency/backlog/recovery/outbox metrics、optional tracing。 |
| T13 | Operations docs/runbooks | Documentation | T13 obs | SLO/alert examples、KMS/CORS/storage outage/leaked URL/device compromise/runbooks。 |
| T13 | Observability validation | Validation | T13 impl/docs | `/metrics`、redaction、labels、logs contain required identifiers without secrets。 |
| T14 | Failure injection | Implementation | T13 | URL expiry、duplicate complete、missing storage part、permission/device revocation、validation/outbox failure。 |
| T14 | Benchmark suite | Implementation | T14 failure | benchmark script、512 MiB local MinIO benchmark、`docs/benchmarks.md` template。 |
| T14 | Failure/Benchmark validation | Validation | T14 impl | failure suite passes、benchmark scoped, no production throughput claims。 |
| T15 | MQTT adapter | Implementation | T10,T11,T13 | command adapter、topic schema、device auth mapping、correlation、ACL、TLS config。 |
| T15 | MQTT validation | Validation | T15 impl | no file bytes、no retained presigned URLs、idempotent duplicate commands、topic isolation。 |
| T16 | Go uploader | Implementation | T08,T14 | `go/robot-uploader`、same API、goroutine concurrency、manifest compatibility/versioning。 |
| T16 | Go uploader validation | Validation | T16 impl | upload/resume against Python backend、benchmark comparison、no MinIO credentials。 |
| T17 | Go gateway | Implementation | T13 and accepted reason | reverse proxy/control gateway、auth validation、rate limit、request ID propagation。 |
| T17 | Go gateway validation | Validation | T17 impl | never proxies file bytes、disable without semantic change、does not replace backend auth/reconciliation。 |

## 8. 合并流程

标准流程：

```text
Implementation Agent
  -> Validation Agent
  -> Master review
  -> Merge Agent
  -> Master final review
```

步骤要求：

1. Implementation Agent 完成实现并写 handoff。
2. Validation Agent 从实现分支独立验证，写 validation handoff。
3. Master agent 审查实现 handoff、验证 handoff、diff、测试证据和 PRD 硬约束。
4. Master agent 只说明合并目的和允许合并的范围，不直接改冲突。
5. Merge Agent 合并 approved 分支，处理合并冲突并写 merge handoff。
6. Master agent 做最终审查，确认合并结果仍满足依赖、测试和硬约束。

冲突处理：

- Merge Agent 只能处理因相邻任务产生的合并冲突。
- 如果冲突需要语义设计决策，Merge Agent 必须停止并标记 `blocked`。
- 如果冲突暴露实现缺陷，Master agent 应派发 Repair Agent，而不是让 Merge Agent 顺手修。

## 9. 验收和恢复策略

验收层级：

- 局部单元测试：Domain、permission、state machine、part math。
- 集成测试：PostgreSQL migration/seed、MinIO multipart、API session lifecycle。
- 端到端 smoke：upload task -> presign -> direct PUT -> ack -> complete。
- 客户端验证：Browser、CLI、Go uploader 的 resume/pause/abort。
- 运维验证：metrics、logs、redaction、runbook、failure injection、benchmark。

每个 Validation handoff 必须包含：

- 实际运行的命令。
- 命令结果。
- 未运行命令及原因。
- 失败复现步骤。
- 是否满足 PRD 硬约束。

失败记录：

- 失败分支不得删除，除非 Master agent 明确判断没有恢复价值。
- `partial` 分支应写明可复用文件、不可复用文件和下一步建议。
- `blocked` 分支应写明需要的外部条件，例如上游 task accepted、环境服务可用、缺失凭据或设计决策。
- `rejected` 分支应写明拒绝原因和禁止后续 agent 重复的错误方向。

恢复策略：

- 后续 agent 必须先读取对应 handoff，再决定继续、修复或重做。
- Repair Agent 优先从最近的 `partial` 或 `rejected` handoff 恢复，而不是重新猜测问题。
- 如果恢复需要扩大范围，Repair Agent 必须停止并交回 Master agent 重新拆分。
- 不可合并分支保留为证据，直到替代实现 accepted 并完成 Master final review。

## 10. PRD 硬约束保留清单

任何 agent 的设计、实现、验证、合并和修复都必须保留以下约束：

- 后端 API 服务不接收文件字节。
- MQTT/EMQX 不接收文件字节，不承载 multipart chunk，不作为对象存储代理。
- 客户端、浏览器、CLI、设备和 Go uploader 不获得 MinIO/S3 access key 或 secret key。
- Multipart upload 的 complete 必须以 object storage `ListParts` 或等价 storage adapter 行为为权威；DB ack 不能单独决定 complete。
- `permission_grants` 和 permission code 是授权来源；API key scope 不能替代资源级授权。
- 内部主键和外键使用 UUID；人类可读 slug、device code、storage upload ID、object key、idempotency key 都不是内部主键。
- MQTT、Go uploader、Go gateway、edge 能力是后置可选组件，不能提前替代 Python backend、HTTP API、授权、storage reconciliation 或 outbox。
- Pause 是控制面调度状态，不是 storage abort，不保证冻结已经开始的 PUT。
- Presigned URL 是短期 bearer token，不能持久化到 manifest、浏览器 local storage、日志、审计、trace 或 outbox。
- Go gateway 如果存在，只能做控制面网关，不能代理文件字节，不能替代后端授权或 storage complete reconciliation。
