# 贪吃蛇游戏 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 纯前端贪吃蛇游戏，Neon Vault 霓虹风格，单文件 snake.html

**Architecture:** 单文件 HTML + 内联 CSS + 内联 JS。Canvas 渲染 20×20 网格，游戏循环用 setTimeout 150ms/帧。

**Tech Stack:** HTML5 Canvas, 内联 CSS, vanilla JS

**Verification:** `open snake.html` 在浏览器中手动验证游戏可玩

---

### Task 1: 创建完整 snake.html

**Files:**
- Create: `snake.html`

- [ ] **Step 1: 写入完整 snake.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Neon Snake</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: #0a0a0f;
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
    font-family: 'JetBrains Mono', monospace;
    overflow: hidden;
  }

  /* Dot grid background */
  body::before {
    content: '';
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100%;
    background-image: radial-gradient(circle, rgba(0,255,136,0.08) 1px, transparent 1px);
    background-size: 20px 20px;
    pointer-events: none;
    z-index: 0;
  }

  .game-wrapper {
    position: relative;
    z-index: 1;
    text-align: center;
  }

  .score-board {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    padding: 0 4px;
  }

  .score-label {
    color: rgba(0,255,136,0.5);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 2px;
  }

  .score-value {
    color: #00ff88;
    font-size: 32px;
    font-weight: 700;
    text-shadow: 0 0 12px rgba(0,255,136,0.6), 0 0 24px rgba(0,255,136,0.3);
  }

  .high-score {
    text-align: right;
  }

  .high-score .score-value {
    color: rgba(0,255,136,0.4);
    font-size: 18px;
    text-shadow: none;
  }

  canvas {
    border: 2px solid rgba(0,255,136,0.2);
    box-shadow: 0 0 20px rgba(0,255,136,0.08), 0 0 60px rgba(0,255,136,0.04);
    display: block;
  }

  .overlay {
    position: absolute;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    pointer-events: none;
  }

  .game-over-text {
    color: #ff4444;
    font-size: 36px;
    font-weight: 700;
    text-shadow: 0 0 20px rgba(255,68,68,0.8);
    opacity: 0;
    transition: opacity 0.3s;
  }

  .game-over-text.visible {
    opacity: 1;
  }

  .restart-btn {
    display: block;
    margin: 16px auto 0;
    padding: 10px 32px;
    background: transparent;
    color: #00ff88;
    border: 2px solid rgba(0,255,136,0.4);
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    cursor: pointer;
    text-transform: uppercase;
    letter-spacing: 2px;
    transition: all 0.2s;
    opacity: 0;
    pointer-events: none;
  }

  .restart-btn.visible {
    opacity: 1;
    pointer-events: auto;
  }

  .restart-btn:hover {
    background: rgba(0,255,136,0.1);
    border-color: #00ff88;
    box-shadow: 0 0 16px rgba(0,255,136,0.3);
  }

  .controls-hint {
    color: rgba(0,255,136,0.25);
    font-size: 11px;
    margin-top: 12px;
    letter-spacing: 1px;
  }

  /* Death flash */
  @keyframes deathFlash {
    0%, 100% { background: #0a0a0f; }
    50% { background: rgba(255,0,0,0.15); }
  }

  body.dead {
    animation: deathFlash 0.4s ease-out;
  }
</style>
</head>
<body>
<div class="game-wrapper">
  <div class="score-board">
    <div>
      <div class="score-label">Score</div>
      <div class="score-value" id="score">0</div>
    </div>
    <div class="high-score">
      <div class="score-label">Best</div>
      <div class="score-value" id="highScore">0</div>
    </div>
  </div>
  <div style="position: relative;">
    <canvas id="canvas" width="400" height="400"></canvas>
    <div class="overlay">
      <div class="game-over-text" id="gameOverText">GAME OVER</div>
    </div>
  </div>
  <button class="restart-btn" id="restartBtn" onclick="restart()">↻ Retry</button>
  <div class="controls-hint">↑↓←→ or WASD to move</div>
</div>

<script>
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const scoreEl = document.getElementById('score');
const highScoreEl = document.getElementById('highScore');
const gameOverText = document.getElementById('gameOverText');
const restartBtn = document.getElementById('restartBtn');

const GRID = 20;
const CELL = canvas.width / GRID;
const SPEED = 150;

let snake, food, direction, nextDirection, score, highScore, gameState, timer;

// --- Init ---
function init() {
  snake = [
    {x: 10, y: 10},
    {x: 9, y: 10},
    {x: 8, y: 10},
  ];
  direction = {x: 1, y: 0};
  nextDirection = {x: 1, y: 0};
  score = 0;
  gameState = 'playing';
  scoreEl.textContent = '0';
  gameOverText.classList.remove('visible');
  restartBtn.classList.remove('visible');
  document.body.classList.remove('dead');
  spawnFood();
  if (timer) clearTimeout(timer);
  loop();
}

function spawnFood() {
  do {
    food = {
      x: Math.floor(Math.random() * GRID),
      y: Math.floor(Math.random() * GRID),
    };
  } while (snake.some(s => s.x === food.x && s.y === food.y));
}

// --- Game Loop ---
function loop() {
  if (gameState !== 'playing') return;
  update();
  if (gameState === 'dead') return;
  draw();
  timer = setTimeout(loop, SPEED);
}

function update() {
  direction = nextDirection;
  const head = {x: snake[0].x + direction.x, y: snake[0].y + direction.y};

  // Wall collision
  if (head.x < 0 || head.x >= GRID || head.y < 0 || head.y >= GRID) {
    die();
    return;
  }
  // Self collision
  if (snake.some(s => s.x === head.x && s.y === head.y)) {
    die();
    return;
  }

  snake.unshift(head);

  if (head.x === food.x && head.y === food.y) {
    score += 10;
    scoreEl.textContent = score;
    spawnFood();
  } else {
    snake.pop();
  }
}

function die() {
  gameState = 'dead';
  document.body.classList.add('dead');
  gameOverText.classList.add('visible');
  restartBtn.classList.add('visible');
  if (score > highScore) {
    highScore = score;
    localStorage.setItem('neonSnakeHighScore', highScore);
    highScoreEl.textContent = highScore;
  }
  draw();
}

// --- Render ---
function draw() {
  ctx.fillStyle = '#0a0a0f';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Grid lines
  ctx.strokeStyle = 'rgba(0,255,136,0.04)';
  ctx.lineWidth = 0.5;
  for (let i = 0; i <= GRID; i++) {
    ctx.beginPath();
    ctx.moveTo(i * CELL, 0);
    ctx.lineTo(i * CELL, canvas.height);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, i * CELL);
    ctx.lineTo(canvas.width, i * CELL);
    ctx.stroke();
  }

  // Food
  const fx = food.x * CELL + CELL / 2;
  const fy = food.y * CELL + CELL / 2;
  const pulse = Math.sin(Date.now() / 200) * 2 + 7;

  ctx.shadowColor = '#ff6b35';
  ctx.shadowBlur = 12;
  ctx.fillStyle = '#ff6b35';
  ctx.beginPath();
  ctx.arc(fx, fy, pulse, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;

  // Snake
  snake.forEach((seg, i) => {
    const alpha = 1 - (i / (snake.length + 10)) * 0.6;
    const gx = seg.x * CELL;
    const gy = seg.y * CELL;

    ctx.shadowColor = '#00ff88';
    ctx.shadowBlur = i === 0 ? 16 : 6;
    ctx.fillStyle = i === 0
      ? '#00ff88'
      : `rgba(0, 255, 136, ${alpha})`;

    const pad = i === 0 ? 1 : 2;
    ctx.fillRect(gx + pad, gy + pad, CELL - pad * 2, CELL - pad * 2);

    if (i === 0) {
      // Head eyes
      ctx.shadowBlur = 0;
      ctx.fillStyle = '#0a0a0f';
      const ec = 4, er = 2.5;
      if (direction.x === 1) {
        ctx.beginPath(); ctx.arc(gx + 14, gy + 6, er, 0, Math.PI*2); ctx.fill();
        ctx.beginPath(); ctx.arc(gx + 14, gy + 14, er, 0, Math.PI*2); ctx.fill();
      } else if (direction.x === -1) {
        ctx.beginPath(); ctx.arc(gx + 6, gy + 6, er, 0, Math.PI*2); ctx.fill();
        ctx.beginPath(); ctx.arc(gx + 6, gy + 14, er, 0, Math.PI*2); ctx.fill();
      } else if (direction.y === -1) {
        ctx.beginPath(); ctx.arc(gx + 6, gy + 6, er, 0, Math.PI*2); ctx.fill();
        ctx.beginPath(); ctx.arc(gx + 14, gy + 6, er, 0, Math.PI*2); ctx.fill();
      } else {
        ctx.beginPath(); ctx.arc(gx + 6, gy + 14, er, 0, Math.PI*2); ctx.fill();
        ctx.beginPath(); ctx.arc(gx + 14, gy + 14, er, 0, Math.PI*2); ctx.fill();
      }
    }
  });
  ctx.shadowBlur = 0;

  // Death overlay
  if (gameState === 'dead') {
    ctx.fillStyle = 'rgba(10,10,15,0.7)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#ff4444';
    ctx.font = 'bold 28px "JetBrains Mono"';
    ctx.textAlign = 'center';
    ctx.shadowColor = '#ff4444';
    ctx.shadowBlur = 20;
    ctx.fillText(`SCORE: ${score}`, canvas.width / 2, canvas.height / 2);
    ctx.shadowBlur = 0;
    ctx.textAlign = 'start';
  }
}

// --- Input ---
document.addEventListener('keydown', e => {
  if (gameState === 'dead') return;
  const key = e.key.toLowerCase();
  if (key === 'arrowup' || key === 'w')    { if (direction.y === 0) nextDirection = {x: 0, y: -1}; e.preventDefault(); }
  if (key === 'arrowdown' || key === 's')  { if (direction.y === 0) nextDirection = {x: 0, y: 1};  e.preventDefault(); }
  if (key === 'arrowleft' || key === 'a')  { if (direction.x === 0) nextDirection = {x: -1, y: 0}; e.preventDefault(); }
  if (key === 'arrowright' || key === 'd') { if (direction.x === 0) nextDirection = {x: 1, y: 0};  e.preventDefault(); }
});

function restart() {
  init();
}

// --- Start ---
highScore = parseInt(localStorage.getItem('neonSnakeHighScore')) || 0;
highScoreEl.textContent = highScore;
init();
</script>
</body>
</html>
```

- [ ] **Step 2: 验证文件已创建**

```bash
ls -la snake.html && wc -l snake.html
```

- [ ] **Step 3: 用浏览器打开验证游戏可玩**

```bash
open snake.html
```

手动验证：
- 蛇在 400×400 画布上移动 ✅
- 方向键控制方向 ✅
- 吃食物增长 + 分数 +10 ✅
- 撞墙死亡 + Game Over ✅
- 撞自己死亡 ✅
- 重开按钮可用 ✅
- 最高分存储在 localStorage ✅

- [ ] **Step 4: 提交**

```bash
git add snake.html
git commit -m "feat: Neon Vault 贪吃蛇游戏"
```
