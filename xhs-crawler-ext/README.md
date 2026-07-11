# xhs-crawler-ext

小红书搜索结果采集助手。当前已开始迁移成 **Chrome MV3 浏览器插件**：用户自己在小红书页面完成搜索/筛选后，打开插件侧边栏，按当前页面采集标题、正文、图片链接和评论，并本地导出 JSON/CSV。

> 数据保存在浏览器扩展自己的 IndexedDB，本版不上云端、不需要后端服务。原始 browser-harness 脚本保留在 `archive/`。

## 当前状态

### 浏览器插件 MVP

`extension/` 是可加载的 Chrome MV3 插件：

- 用户自己打开小红书页面并搜索关键词，插件不提供关键词输入
- 侧边栏检测当前页面可见笔记卡片
- 可设置采集数量、评论模式、速度模式
- content script 在当前页面逐篇打开笔记并提取数据
- background service worker 使用 IndexedDB 本地保存任务和笔记
- 支持暂停、继续、停止
- 支持从本地数据导出 JSON / CSV / XLSX
- XLSX 导出会把帖子图片嵌入表格右侧
- 支持把本次任务的帖子图和评论图下载到浏览器下载目录

加载方式：

1. 打开 `chrome://extensions`
2. 开启「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择 `xhs-crawler-ext/extension`
5. 打开小红书页面，自己搜索关键词后点击扩展图标

XLSX 使用本地 vendored `ExcelJS` bundle 生成，不加载远程脚本。图片请求通过扩展后台发起，并用 `declarativeNetRequest` 给 `xhscdn.com` 图片请求补 `Referer: https://www.xiaohongshu.com/`。

### browser-harness 归档版

browser-harness (CDP) 版本已经过实战验证：

- 最近一次运行：关键词「男生反复长痘痘」，目标 20 篇 → **20/20 成功，0 失败，117 条评论**
- 单篇重试、断点续爬（`state.json`）、增量落盘、连接健康检查均已内置
- 导出 Excel 含嵌入图片（openpyxl + OneCellAnchor）

跑通记录见根目录 `xhs_data/20260626_男生反复长痘痘/`。

## 目录结构

```
xhs-crawler-ext/
├── README.md                          # 本文件
├── archive/                           # 现有 browser-harness (CDP) 版本，完整可跑
│   ├── xhs_batch.py                   # ★ 批量爬取编排（纯函数 + 页面 JS 片段 + CDP 调用）
│   ├── xhs_export.py                  #   Excel 导出（图片下载 + OneCellAnchor 嵌图）
│   ├── test_xhs_batch_pure.py         #   纯函数单测（waterfall_sort / compute_threads / state）
│   └── SKILL.md                       #   用法 + 流程 + 反爬要点（CDP 版操作手册）
├── references/                        # 小红书站点知识（迁移到插件必读）
│   ├── selectors.md                   #   完整 DOM 选择器表
│   ├── gotchas.md                     #   18 个已知坑 + 解法（附 JS 片段）
│   └── waterfall-layout.md            #   5 列瀑布流阅读顺序排序算法（含 JS 实现）
└── docs/
    └── migration-to-extension.md      # ★ CDP → MV3 浏览器插件迁移设计
```

## 现在怎么跑（archive 版）

前提：browser-harness 已安装、Chrome 已连接、小红书已登录、`openpyxl` 已装。

```bash
cd xhs-crawler-ext/archive
XHS_KEYWORD="咖啡" XHS_TARGET=20 browser-harness < xhs_batch.py
# 导出 Excel（图片并行下载 + 嵌入）
python3 xhs_export.py ../../xhs_data/<输出目录>  <输出.xlsx>
```

环境变量见 `archive/xhs_batch.py` 顶部（`XHS_KEYWORD` / `XHS_TARGET` / `XHS_OUTDIR` / `XHS_MAX_RETRY`）。

## 下一步

继续补齐产品能力：

- 单篇失败重试入口和失败原因筛选
- 真实浏览器加载测试和小红书页面端到端验证
- XLSX 导出性能优化（大量图片时的进度、失败重试、图片数量上限）
- 可选嵌入评论图片
- 更完整的页面类型检测（搜索页、话题页、主页、收藏页）
