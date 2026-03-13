import subprocess
import sys

def run_demo(keyword, min_sec, max_sec):
    print(f"=== 运行 Demo: 搜索 '{keyword}', 时长 {min_sec}-{max_sec} 秒 ===")
    cmd = [
        sys.executable, "search_videos.py",
        "--keyword", keyword,
        "--min_duration", str(min_sec),
        "--max_duration", str(max_sec)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Demo 运行失败: {e}")
        print(e.stderr)

if __name__ == "__main__":
    # 示例 1: 搜索短视频
    run_demo("cat videos", 10, 60)

    # 示例 2: 搜索教育视频
    run_demo("machine learning intro", 300, 1200)
