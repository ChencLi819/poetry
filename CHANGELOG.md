# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与
[语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0] - 2026-10-07

### Added

- **离线诗库**：SQLite 数据库随包分发，离线检索，带 `ord` / `au` / `dy` / `ti` / `prov` 索引。
- **十二分类**：唐诗三百首、宋词精选、古诗三百首、诗经、楚辞、乐府、古诗十九首、
  婉约词、豪放词、小学 / 初中 / 高中古诗文。
- **逐字注音**：正文叠加拼音，注音按位置对齐（UTF-16 码元下标），支持逐字点击查字义。
- **详情多标签**：原文 / 注释 / 译文 / 赏析 / 创作背景，标签吸顶、局部刷新不跳顶。
- **无限滚动**：列表滚到底自动续拉。
- **收藏与统计**：收藏夹、已读计数、查字计数、按天诵读量、连续打卡。
- **汉字字典**：`zi` 表内置新华字典数据，可查释义、拼音、部首、字形说解与书证。
- **朗读诵读**：调用系统 TTS 朗读全篇。
- **水墨宣纸风格 UI**：WebView 单页应用，底部五等分导航 + 中央搜索入口。
- **语料工具链**（`tools/`）：
  - `build_public.py` — chinese-poetry 公开语料繁转简、去重、按热度筛选
  - `build_db.py` — 生成运行时 SQLite 诗库（含三级注音来源）
  - `build_zi.py` — 字典数据并入 `zi` 表
  - `textutil.py` — 跨脚本共用的清洗规则与去重签名
  - `check_db.py` — 建库后的不变量门禁（15 项硬校验 + 10 项质量提示）
  - `fetch.py` / `crawl_all.py` / `catalog.py` / `parse.py` / `parse_all.py` / `scale.py`
    — 本地资料采集与解析，数据源由环境变量指定
- **文档**：`README.md`、`docs/NOTICE.md`（数据来源与版权边界）、MIT `LICENSE`。
- **高保真原型**：`poetry-app-prototype.html`（六屏 + 色彩字体规范）。

### Notes

- `android/app/src/main/assets/poems.db` 体积超过 GitHub 单文件上限，**不随源码分发**，
  需按 README「数据准备」本地生成。
- 签名密钥与口令不入库。

[1.0]: https://github.com/ChencLi819/poetry/releases/tag/v1.0
