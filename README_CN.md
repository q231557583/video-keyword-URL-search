# 视频搜索工具

该工具可以根据指定的关键词在全球各大搜索引擎（如 Google Video）和视频网站（如 YouTube）上搜索符合条件的视频网址，并支持指定视频时长范围进行过滤。

## 功能特点

- **多平台搜索**：支持 YouTube、Google Video 以及 **Bilibili** 搜索。
- **智能去重**：自动过滤不同平台间的重复视频链接。
- **时长过滤**：可以指定最小和最大视频时长（秒），支持 Bilibili 的长视频筛选。
- **结果导出**：支持导出为 CSV 文件，并可自定义编码格式（如 `gbk`）以完美兼容 Excel。
- **时长解析**：自动解析多种时长格式（如 `10:05`、`5 hours, 31 minutes` 等）。
- **自动排序**：结果默认按视频时长升序排列。

## 安装步骤

1. **安装 Python 依赖**：
   确保已安装 `playwright`：
   ```bash
   pip install playwright
   ```

2. **安装浏览器内核**：
   ```bash
   playwright install chromium
   ```

## 使用方法

通过命令行运行 `search_videos.py`，并提供必要的参数。

### 参数说明

- `--keyword`: 搜索关键词（必填）。
- `--min_duration`: 最小视频时长，单位为秒（默认为 0）。
- `--max_duration`: 最大视频时长，单位为秒（可选）。
- `--limit`: 每个平台的搜索结果上限（默认为 20）。
- `--source`: 搜索来源，可选 `youtube`, `google`, `bilibili`, `all`（默认为 `all`）。
- `--output`: 导出 CSV 文件的路径。
- `--encoding`: CSV 文件的编码，例如 `utf-8-sig` 或 `gbk`（默认为 `utf-8-sig`）。

### 示例

1. **搜索关键词 "space"，时长在 1 到 5 分钟之间（60-300秒）**：
   ```bash
   python3 search_videos.py --keyword "space" --min_duration 60 --max_duration 300
   ```

2. **搜索关键词 "python tutorial"，时长至少 10 分钟（600秒）**：
   ```bash
   python3 search_videos.py --keyword "python tutorial" --min_duration 600
   ```

3. **从所有平台搜索 "cooking"，并将结果导出为 Excel 兼容的 CSV**：
   ```bash
   python3 search_videos.py --keyword "cooking" --output results.csv --encoding gbk
   ```

## 开发者说明

该脚本使用 `playwright` 异步库进行网页爬取。它首先在 YouTube 上搜索，然后在 Google Video 上搜索，最后汇总并过滤结果。

### 核心函数

- `parse_duration(duration_str)`：将各种文本格式的时长转换为秒数。
- `search_youtube(page, keyword)`：在 YouTube 抓取视频信息。
- `search_google_video(page, keyword)`：在 Google Video 抓取视频信息。
