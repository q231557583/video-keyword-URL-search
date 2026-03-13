import asyncio
import re
import argparse
from playwright.async_api import async_playwright

def parse_duration(duration_str):
    """
    Parses duration string into seconds.
    Handles formats like "10:05", "1:20:30", "5 hours, 31 minutes", "45 seconds".
    """
    if not duration_str:
        return 0

    # Check for natural language format: "5 hours, 31 minutes"
    total_seconds = 0
    hours_match = re.search(r'(\d+)\s*hour', duration_str)
    minutes_match = re.search(r'(\d+)\s*minute', duration_str)
    seconds_match = re.search(r'(\d+)\s*second', duration_str)

    if hours_match or minutes_match or seconds_match:
        if hours_match:
            total_seconds += int(hours_match.group(1)) * 3600
        if minutes_match:
            total_seconds += int(minutes_match.group(1)) * 60
        if seconds_match:
            total_seconds += int(seconds_match.group(1))
        return total_seconds

    # Check for "HH:MM:SS" or "MM:SS" format
    parts = duration_str.split(':')
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1:
            return int(parts[0])
    except ValueError:
        pass

    return 0

async def search_youtube(page, keyword):
    url = f"https://www.youtube.com/results?search_query={keyword.replace(' ', '+')}"
    try:
        await page.goto(url)
        await page.wait_for_selector("ytd-video-renderer", timeout=10000)
    except:
        return []

    # Scroll a bit to load more results if needed
    await page.evaluate("window.scrollBy(0, 2000)")
    await asyncio.sleep(2)

    videos = []
    renderers = await page.query_selector_all("ytd-video-renderer")

    for renderer in renderers:
        title_elem = await renderer.query_selector("#video-title")
        if not title_elem:
            continue

        title = await title_elem.inner_text()
        href = await title_elem.get_attribute("href")
        video_url = f"https://www.youtube.com{href}" if href else ""

        # Duration can be found in aria-label of the renderer or thumbnail overlay
        aria_label = await renderer.get_attribute("aria-label")
        duration_text = ""
        if aria_label:
            match = re.search(r'(\d+\s*hours?,\s*)?(\d+\s*minutes?,\s*)?(\d+\s*seconds?)$', aria_label)
            if match:
                duration_text = match.group(0)

        if not duration_text:
            duration_elem = await renderer.query_selector("span.ytd-thumbnail-overlay-time-status-renderer")
            if duration_elem:
                duration_text = await duration_elem.inner_text()

        duration_sec = parse_duration(duration_text.strip())

        videos.append({
            "title": title.strip(),
            "url": video_url,
            "duration": duration_sec,
            "duration_str": duration_text.strip(),
            "source": "YouTube"
        })
    return videos

async def search_google_video(page, keyword):
    url = f"https://www.google.com/search?q={keyword.replace(' ', '+')}&tbm=vid"
    try:
        await page.goto(url)
    except:
        return []

    videos = []
    results = await page.query_selector_all("div[data-ved]")

    for res in results:
        title_elem = await res.query_selector("h3")
        if not title_elem:
            continue

        title = await title_elem.inner_text()
        link_elem = await res.query_selector("a")
        if not link_elem:
            continue
        video_url = await link_elem.get_attribute("href")

        duration_text = ""
        spans = await res.query_selector_all("span")
        for span in spans:
            text = await span.inner_text()
            if not text: continue
            if re.search(r'^\d+:\d+(:\d+)?$', text.strip()) or ("minute" in text and "ago" not in text):
                duration_text = text
                break

        if not duration_text:
            aria_label = await res.get_attribute("aria-label")
            if aria_label and ("minute" in aria_label or "second" in aria_label):
                duration_text = aria_label

        if not video_url or video_url.startswith("/"):
            continue

        duration_sec = parse_duration(duration_text.strip())

        if any(v['url'] == video_url for v in videos):
            continue

        videos.append({
            "title": title.strip(),
            "url": video_url,
            "duration": duration_sec,
            "duration_str": duration_text.strip(),
            "source": "Google Video"
        })
    return videos

async def main():
    parser = argparse.ArgumentParser(description="Search for videos with keyword and duration range.")
    parser.add_argument("--keyword", required=True, help="Search keyword")
    parser.add_argument("--min_duration", type=int, default=0, help="Minimum duration in seconds")
    parser.add_argument("--max_duration", type=int, default=None, help="Maximum duration in seconds")

    args = parser.parse_args()

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        print(f"Searching for '{args.keyword}'...")

        yt_results = await search_youtube(page, args.keyword)
        gv_results = await search_google_video(page, args.keyword)

        all_results = yt_results + gv_results

        filtered_results = []
        for res in all_results:
            duration = res["duration"]
            if duration >= args.min_duration:
                if args.max_duration is None or duration <= args.max_duration:
                    filtered_results.append(res)

        filtered_results.sort(key=lambda x: x["duration"])

        print(f"\nFound {len(filtered_results)} videos matching criteria:")
        print("-" * 80)
        for res in filtered_results:
            print(f"Source: {res['source']}")
            print(f"Title: {res['title']}")
            print(f"Duration: {res['duration_str']} ({res['duration']}s)")
            print(f"URL: {res['url']}")
            print("-" * 80)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
