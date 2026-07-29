# 桌宠 Desktop Pet

一个跨平台（Windows / macOS / Linux）的桌面宠物小程序，用 Electron 实现。

## 功能

- **待机动画**：呼吸起伏、随机眨眼
- **自主行走**：闲置一段时间后会自己在屏幕底部左右走动
- **拖拽**：按住桌宠可以把它拖到屏幕任意位置
- **点击互动**：点一下会做出反应（跳一下 + 冒出一句话）
- **右键菜单**：切换配色（换装占位方案）、开关自主走动、退出程序
- 全局快捷键 `Ctrl/Cmd + Shift + Q` 用于紧急退出（因为窗口不在任务栏/Dock 里显示）

## 运行方式

> 这是一个**桌面 GUI 应用**，需要在你自己的电脑（有屏幕）上运行，无法在云端/远程终端里显示界面。

```bash
cd desktop-pet
npm install
npm start
```

## 目前的“形象”是占位的

现在桌宠是一个纯 SVG + CSS 画的卡通猫（`renderer/index.html` 里的 `<svg>`），走的是"先能跑起来，形象后面再换"的思路。换成朋友专属形象有两种路径：

### 方式一：静态图替换（最简单）

1. 准备 2～3 张已经做好的卡通/Q 版立绘 PNG（透明背景），比如：`idle.png`、`walk.png`、`happy.png`
2. 把图片放进 `renderer/assets/` 目录
3. 把 `renderer/index.html` 里的 `<svg>...</svg>` 换成 `<img id="pet-img" src="assets/idle.png" />`
4. 在 `renderer/pet.js` 的 `setState()` 里，根据 state 切换 `img.src`

这样就不用改 `main.js` 的任何逻辑（拖拽/行走/菜单都还能正常工作）。

### 方式二：接入 AI 图像生成，自动把照片转成卡通立绘

如果想做成"上传照片 → 自动生成卡通形象"的完整体验，需要：

1. 一个图生图 API（如通义千问的图像生成、Stable Diffusion WebUI 的 `/sdapi/v1/img2img` 接口等），把人像转成"Q 版/卡通风格"
2. 在 Electron 里加一个简单的设置窗口，用来上传照片、调用该 API、把返回的图片存到 `renderer/assets/` 下
3. 之后走"方式一"的替换逻辑

这一步涉及第三方 API Key 和调用成本，需要你先确定要用哪个服务，我可以再帮你把这部分接入代码写好。

## 项目结构

```
desktop-pet/
├── package.json
├── main.js          # Electron 主进程：窗口创建、拖拽、自主行走、右键菜单
├── preload.js       # 安全地把有限的 API 暴露给渲染进程（window.pet.*）
└── renderer/
    ├── index.html   # 桌宠的 DOM 结构（当前用 SVG 画的占位卡通猫）
    ├── style.css    # 动画与配色（呼吸/走路/开心/拖拽状态）
    └── pet.js       # 渲染进程逻辑：拖拽判定、点击反应、状态切换
```
