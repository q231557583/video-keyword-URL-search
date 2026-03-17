import asyncio
import re
import argparse
import urllib.parse
import csv
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

async def search_youtube(page, keyword, limit=20):
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(keyword)}"
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

async def search_google_video(page, keyword, limit=20):
    url = f"https://www.google.com/search?q={urllib.parse.quote(keyword)}&tbm=vid"
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

async def search_bilibili(page, keyword, limit=20, min_duration=0):
    # If min_duration > 60 mins (3600s), use duration=4 filter
    duration_filter = "&duration=4" if min_duration >= 3600 else ""

    videos = []
    page_num = 1

    while len(videos) < limit:
        url = f"https://search.bilibili.com/all?keyword={urllib.parse.quote(keyword)}{duration_filter}&page={page_num}"
        try:
            await page.goto(url)
            await page.wait_for_load_state("networkidle")
            # Wait for either old or new Bilibili layout
            try:
                await page.wait_for_selector(".video-list-item, .bili-video-card, .video-item", timeout=10000)
            except:
                # If no videos found, check if it's just no results
                no_results = await page.query_selector(".no-results, .v-no-res")
                if no_results:
                    break
        except:
            break

        await page.evaluate("window.scrollBy(0, 2000)")
        await asyncio.sleep(1)

        cards = await page.query_selector_all(".video-list-item, .bili-video-card, .video-item")
        if not cards:
            break

        initial_count = len(videos)
        for card in cards:
            if len(videos) >= limit:
                break

            title_elem = await card.query_selector("h3, .bili-video-card__info--tit")
            if not title_elem:
                continue
            title = await title_elem.inner_text()

            link_elem = await card.query_selector("a")
            if not link_elem:
                continue
            href = await link_elem.get_attribute("href")
            if not href:
                continue
            if href.startswith("//"):
                video_url = f"https:{href}"
            elif href.startswith("/"):
                video_url = f"https://www.bilibili.com{href}"
            else:
                video_url = href

            duration_elem = await card.query_selector(".duration, .bili-video-card__stats__duration")
            duration_text = await duration_elem.inner_text() if duration_elem else ""
            duration_sec = parse_duration(duration_text.strip())

            if any(v['url'] == video_url for v in videos):
                continue

            videos.append({
                "title": title.strip(),
                "url": video_url,
                "duration": duration_sec,
                "duration_str": duration_text.strip(),
                "source": "Bilibili"
            })

        if len(videos) == initial_count: # No new videos found
            break
        page_num += 1
        if page_num > 5: # Safety limit
            break

    return videos

async def main():
    parser = argparse.ArgumentParser(description="Search for videos with keyword and duration range.")
    parser.add_argument("--keyword", required=True, help="Search keyword")
    parser.add_argument("--min_duration", type=int, default=0, help="Minimum duration in seconds")
    parser.add_argument("--max_duration", type=int, default=None, help="Maximum duration in seconds")
    parser.add_argument("--limit", type=int, default=20, help="Max number of results per source")
    parser.add_argument("--source", default="all", choices=["youtube", "google", "bilibili", "all"], help="Search source")
    parser.add_argument("--output", help="Output CSV file path")
    parser.add_argument("--encoding", default="utf-8-sig", help="CSV encoding (e.g., utf-8-sig, gbk)")

    args = parser.parse_args()

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        print(f"Searching for '{args.keyword}' on {args.source}...")

        seen_urls = set()
        all_results = []

        if args.source in ["youtube", "all"]:
            yt_results = await search_youtube(page, args.keyword, limit=args.limit)
            for res in yt_results:
                if res["url"] not in seen_urls:
                    all_results.append(res)
                    seen_urls.add(res["url"])

        if args.source in ["google", "all"]:
            gv_results = await search_google_video(page, args.keyword, limit=args.limit)
            for res in gv_results:
                if res["url"] not in seen_urls:
                    all_results.append(res)
                    seen_urls.add(res["url"])

        if args.source in ["bilibili", "all"]:
            bi_results = await search_bilibili(page, args.keyword, limit=args.limit, min_duration=args.min_duration)
            for res in bi_results:
                if res["url"] not in seen_urls:
                    all_results.append(res)
                    seen_urls.add(res["url"])

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

        if args.output:
            try:
                with open(args.output, mode='w', encoding=args.encoding, newline='', errors='replace') as f:
                    writer = csv.writer(f)
                    writer.writerow(['视频标题', '视频时长', '网址'])
                    for res in filtered_results:
                        writer.writerow([res['title'], res['duration_str'], res['url']])
                print(f"\nResults exported to {args.output}")
            except Exception as e:
                print(f"\nError exporting to CSV: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
