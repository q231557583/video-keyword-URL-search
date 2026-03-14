import asyncio
import re
import argparse
import csv
import urllib.parse
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
    encoded_keyword = urllib.parse.quote(keyword)
    url = f"https://www.youtube.com/results?search_query={encoded_keyword}"
    try:
        await page.goto(url)
        await page.wait_for_selector("ytd-video-renderer", timeout=10000)
    except Exception as e:
        print(f"Error loading YouTube: {e}")
        return []

    videos = []
    seen_urls = set()

    while len(videos) < limit:
        renderers = await page.query_selector_all("ytd-video-renderer")

        new_found = False
        for renderer in renderers:
            title_elem = await renderer.query_selector("#video-title")
            if not title_elem:
                continue

            href = await title_elem.get_attribute("href")
            if not href:
                continue
            video_url = f"https://www.youtube.com{href}"

            if video_url in seen_urls:
                continue

            title = await title_elem.inner_text()
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
            seen_urls.add(video_url)
            new_found = True

            if len(videos) >= limit:
                break

        if len(videos) < limit and new_found:
            await page.evaluate("window.scrollBy(0, 2000)")
            await asyncio.sleep(2)
        else:
            break

    return videos[:limit]

async def search_google_video(page, keyword, limit=20):
    encoded_keyword = urllib.parse.quote(keyword)
    url = f"https://www.google.com/search?q={encoded_keyword}&tbm=vid"
    try:
        await page.goto(url)
    except Exception as e:
        print(f"Error loading Google: {e}")
        return []

    videos = []
    seen_urls = set()

    while len(videos) < limit:
        results = await page.query_selector_all("div[data-ved]")
        for res in results:
            title_elem = await res.query_selector("h3")
            if not title_elem:
                continue

            link_elem = await res.query_selector("a")
            if not link_elem:
                continue
            video_url = await link_elem.get_attribute("href")

            if not video_url or video_url.startswith("/") or video_url in seen_urls:
                continue

            title = await title_elem.inner_text()
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

            duration_sec = parse_duration(duration_text.strip())
            videos.append({
                "title": title.strip(),
                "url": video_url,
                "duration": duration_sec,
                "duration_str": duration_text.strip(),
                "source": "Google Video"
            })
            seen_urls.add(video_url)

            if len(videos) >= limit:
                break

        if len(videos) < limit:
            next_button = await page.query_selector("a#pnnext")
            if next_button:
                await next_button.click()
                await page.wait_for_timeout(2000)
            else:
                break
        else:
            break

    return videos[:limit]

async def search_bilibili(page, keyword, limit=20, min_duration=0):
    # duration=4 for >60 mins
    duration_param = "&duration=4" if min_duration >= 3600 else ""
    encoded_keyword = urllib.parse.quote(keyword)
    videos = []
    seen_urls = set()
    p = 1

    while len(videos) < limit:
        url = f"https://search.bilibili.com/all?keyword={encoded_keyword}&page={p}{duration_param}"
        try:
            await page.goto(url)
            await page.wait_for_selector(".bili-video-card", timeout=10000)
        except Exception as e:
            print(f"Error loading Bilibili page {p}: {e}")
            break

        cards = await page.query_selector_all(".bili-video-card")
        if not cards:
            break

        found_on_page = 0
        for card in cards:
            title_elem = await card.query_selector(".bili-video-card__info--tit")
            if not title_elem:
                continue

            link_elem = await card.query_selector("a")
            href = await link_elem.get_attribute("href")
            if href.startswith("//"):
                video_url = f"https:{href}"
            else:
                video_url = href

            # Clean Bilibili URL (remove query params)
            video_url = video_url.split('?')[0]

            if video_url in seen_urls:
                continue

            title = await title_elem.get_attribute("title")
            duration_elem = await card.query_selector(".bili-video-card__stats__duration")
            duration_text = await duration_elem.inner_text() if duration_elem else ""
            duration_sec = parse_duration(duration_text.strip())

            videos.append({
                "title": title.strip(),
                "url": video_url,
                "duration": duration_sec,
                "duration_str": duration_text.strip(),
                "source": "Bilibili"
            })
            seen_urls.add(video_url)
            found_on_page += 1

            if len(videos) >= limit:
                break

        if found_on_page == 0:
            break
        p += 1
        await asyncio.sleep(1)

    return videos[:limit]

async def main():
    parser = argparse.ArgumentParser(description="Search for videos with keyword and duration range.")
    parser.add_argument("--keyword", required=True, help="Search keyword")
    parser.add_argument("--min_duration", type=int, default=0, help="Minimum duration in seconds")
    parser.add_argument("--max_duration", type=int, default=None, help="Maximum duration in seconds")
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of results to return")
    parser.add_argument("--source", default="all", help="Source to search from: youtube, google, bilibili, all")
    parser.add_argument("--output", help="Output CSV file path")

    args = parser.parse_args()

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        print(f"Searching for '{args.keyword}' (min {args.min_duration}s, limit {args.limit})...")

        all_results = []

        sources = [s.strip() for s in args.source.lower().split(',')]
        if "all" in sources:
            sources = ["youtube", "google", "bilibili"]

        if "youtube" in sources:
            print("Searching YouTube...")
            all_results.extend(await search_youtube(page, args.keyword, limit=args.limit))
        if "google" in sources:
            print("Searching Google Video...")
            all_results.extend(await search_google_video(page, args.keyword, limit=args.limit))
        if "bilibili" in sources:
            print("Searching Bilibili...")
            all_results.extend(await search_bilibili(page, args.keyword, limit=args.limit, min_duration=args.min_duration))

        filtered_results = []
        for res in all_results:
            duration = res["duration"]
            if duration >= args.min_duration:
                if args.max_duration is None or duration <= args.max_duration:
                    filtered_results.append(res)

        filtered_results.sort(key=lambda x: x["duration"])
        final_results = filtered_results[:args.limit]

        print(f"\nFound {len(final_results)} videos matching criteria:")
        print("-" * 80)
        for res in final_results:
            print(f"Source: {res['source']}")
            print(f"Title: {res['title']}")
            print(f"Duration: {res['duration_str']} ({res['duration']}s)")
            print(f"URL: {res['url']}")
            print("-" * 80)

        if args.output:
            with open(args.output, 'w', newline='', encoding='utf-8-sig') as csvfile:
                fieldnames = ['赛事名称', '视频时长', '网址']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for res in final_results:
                    writer.writerow({
                        '赛事名称': res['title'],
                        '视频时长': res['duration_str'],
                        '网址': res['url']
                    })
            print(f"Results saved to {args.output}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
