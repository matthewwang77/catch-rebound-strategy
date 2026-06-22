# /dagent — Claude Code + Codex 协作 Skill 设计

## 概述

`/dagent` 是一个全局纪律执行型 skill，为大任务提供 Claude Code + Codex 互相审查、交替执行的 5 步协作工作流。两边都说"无问题"才算通过。

## 触发条件

- 手动触发：用户说 `/dagent` 或提到 "dagent"
- 仅大任务：多文件改动、新功能、架构变更
- 排除：单行修复、纯配置变更、小改动

## 规模评估

技能启动时先做规模评估：
- 单文件小改 / 单行修复 / 纯配置变更 → 拒绝，走普通流程
- 多文件 / 新功能 / 架构变更 → 走完整 5 步

## 5 步流程

```
Step 1: Claude Code brainstorm + writing-plans → spec + plan
    ↓
Step 2: Codex 审查计划 → 挑毛病
    ↓ (有问题 → 回 Step 1)
    ↓ (无问题)
Step 3: Codex 执行代码
    ↓
Step 4: Claude Code code review
    ↓
Step 5: Codex sub-agent 多重审查
    ↓ (任一有问题 → 回 Step 3)
    ↓ (都无问题)
   ✅ 完成
```

### Step 1 — Claude Code 写计划

- 调用 `superpowers:brainstorming` → 输出 spec
- 调用 `superpowers:writing-plans` → 输出 plan
- 输出文件：`docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` + `docs/superpowers/plans/YYYY-MM-DD-<topic>-plan.md`
- 通过条件：spec + plan 写入且用户 approve

### Step 2 — Codex 审查计划

- Codex 读取 spec + plan，从以下角度审查：
  - 架构合理性
  - 遗漏的边界条件
  - 过度工程/不够工程
  - 与现有代码的冲突
  - 测试覆盖缺口
- 输出：问题列表（标记严重程度）
- 通过条件：空问题列表
- 不通过 → 回 Step 1 修改计划

### Step 3 — Codex 执行代码

- Codex 按 plan 实现代码
- 拥有写文件、运行测试等权限
- 输出：代码变更（git diff）

### Step 4 — Claude Code 审查代码

- 用 `code-review` skill 审查 diff
- 关注：逻辑 bug、边界错误、代码质量
- 输出：问题列表

### Step 5 — Codex Sub-agent 多重审查

- Codex 启动 2-3 个子 agent，从不同角度审查：
  - 正确性（逻辑错误）
  - 安全性（注入、泄露）
  - 性能（N+1、内存）
- 输出：汇总问题列表

### 退出判断

- Step 4 **且** Step 5 都返回空问题列表 → ✅ 完成
- 任一有问题 → 回 Step 3，Codex 修代码
- 硬上限：3 轮 → 列出争议点，交给用户仲裁

## 异常处理

| 情况 | 处理 |
|------|------|
| Codex 未安装 | 提示 `npm install -g @openai/codex`，阻塞等待 |
| Codex 未认证 | 提示 `codex login`，阻塞等待 |
| Codex 网络/API 错误 | 回退为纯 Claude Code 流程 |
| 循环 ≥ 3 轮不收敛 | 暂停，列出争议，用户仲裁 |
| Codex 执行崩溃 | 保留已写内容，下一轮继续 |
| 用户中断 | 保留当前状态，用户可手动继续 |

## Skill 文件结构

```
~/.claude/skills/dagent/
  SKILL.md    # 自包含，~300-400 词
```

全内容内联，无需额外文件。

## 反合理化表

| 借口 | 现实 |
|------|------|
| "plan 很清晰，可以跳过 Codex review" | Step 2 强制。计划者不能审查自己的计划。 |
| "改动很小，一轮就够了" | 必须走完 S4+S5 才能退出。 |
| "Codex 已 review 过，S4 可以轻一点" | S4 和 S5 角度不同——CC 找 bug，Codex 找安全/性能。互补不替代。 |
| "第 3 轮了，差不多就行了" | 3 轮后交给用户决策，不自己放行。 |

## 红旗信号

- "这个任务不够大，但我想用 /dagent" → 规模评估不通过，拒绝
- "Codex 没装，我跳过 S2-S5 直接实现" → 必须装好 Codex
- "S4 发现 2 个小问题但我已经顺手修了，不用回 S3" → 必须回 S3
- "循环到第 2 轮了，问题很少了，直接退出吧" → 必须双方都返回空

## TodoWrite 追踪

每步对应一个 todo，状态对用户可见：

1. `Step 1: Brainstorm + writing-plans → spec + plan`
2. `Step 2: Codex review plan → 问题列表`
3. `Step 3: Codex 执行代码`
4. `Step 4: Claude Code code review`
5. `Step 5: Codex sub-agent 多重审查`
6. `[Loop N/3] 判断退出 or 回 Step 3`

## 依赖

- `superpowers:brainstorming` skill
- `superpowers:writing-plans` skill
- `codex:setup` skill
- `code-review` skill
- `@openai/codex` CLI（用户自行安装）
