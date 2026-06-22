# 贪吃蛇游戏 — Neon Vault 风格设计

## 概述

纯前端贪吃蛇游戏，单文件 `snake.html`，Neon Vault 霓虹视觉风格。

## 架构

单文件：HTML 骨架 + 内联 CSS + 内联 JS。`<canvas>` 渲染。Google Fonts 仅 CSS `@import`，降级到系统 monospace。

## 视觉风格

- 背景：深黑 `#0a0a0f` + CSS dot-grid pattern
- 蛇身：霓虹绿 `#00ff88`，发光 shadow
- 食物：霓虹橙 `#ff6b35`，脉动动画
- 网格线：`rgba(0,255,136,0.05)`
- 字体：JetBrains Mono（降级：系统 monospace）
- 死亡：屏幕闪红 + 霓虹边框重开按钮

## 游戏规格

| 项目 | 值 |
|------|-----|
| Canvas | 400×400 |
| 网格 | 20×20 格（每格 20px） |
| 速度 | 150ms/帧 |
| 初始蛇长 | 3 格 |
| 操作 | ↑↓←→ / WASD / 触摸滑动 |
| 暂停 | 空格键 |
| 得分 | 每个食物 +10 |

## 游戏状态

三种状态：`playing` / `paused` / `dead`。空格键切换暂停。标签失焦自动暂停。

## 边界条件

- 蛇填满棋盘（400 格）→ 胜利，显示 "YOU WIN"
- localStorage 不可用时静默降级（高分不持久化）
- Canvas 2D 上下文不可用时显示错误信息

## 碰撞

- 蛇头出界（<0 或 ≥20）→ 死
- 蛇头与蛇身重叠 → 死（先移除尾部再检查，避免误判尾部位置）
- 食物不与蛇身重叠生成；棋盘满时触发胜利

## 游戏循环

```
update(direction) → popTail → checkCollision → eatFood? → redraw → setTimeout(loop, 150)
```

## 文件

- 创建：`snake.html`
