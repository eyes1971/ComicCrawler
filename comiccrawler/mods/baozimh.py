# 專為Comic Crawler的baozimh腳本
import re
from html import unescape
from urllib.parse import urljoin, urlparse, parse_qs
from ..core import Episode
from bs4 import BeautifulSoup

# 網站相關資訊
domain = ["www.baozimh.com","www.twmanga.com"]
name = "baozimh"
noepfolder = False  # 不創建單獨的集數文件夾

def get_title(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    title_tag = soup.find("h1", class_="comics-detail__title")
    title = title_tag.text.strip() if title_tag else "Untitled Comic"
    return title

def get_episodes(html, url):
    episodes = []
    soup = BeautifulSoup(html, 'html.parser')
    for episode_tag in soup.select("div.pure-u-1-1.pure-u-sm-1-2.pure-u-md-1-3.pure-u-lg-1-4.comics-chapters"):
        episode_title = episode_tag.find("span").text.strip()
        episode_url = episode_tag.find("a")["href"]
        episode_url = urljoin(url, episode_url)
        real_url = construct_real_url(episode_url)
        episodes.append(Episode(title=episode_title, url=real_url))
    return episodes

def construct_real_url(episode_url):
    parsed_url = urlparse(episode_url)
    query_params = parse_qs(parsed_url.query)
    
    comic_id = query_params.get("comic_id", [""])[0]
    section_slot = query_params.get("section_slot", ["0"])[0]
    chapter_slot = query_params.get("chapter_slot", ["0"])[0]
    
    real_url = f"https://www.twmanga.com/comic/chapter/{comic_id}/{section_slot}_{chapter_slot}.html"
    return real_url

def is_korean_style_manga(html):
    """檢查是否為韓漫格式（通過檢查頁面標題中的分頁標記和下一頁按鈕）"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # 檢查標題是否包含分頁標記 (1/N)
    title = soup.find("h1", class_="chapter-title")
    if title and re.search(r'\((\d+)/(\d+)\)', title.text):
        return True
    
    # 檢查是否存在"下一頁"按鈕
    next_buttons = soup.find_all("a", class_="next-page")
    for button in next_buttons:
        if "下一頁" in button.text:
            return True
    
    return False

def get_next_section_url(html, current_url):
    """獲取下一個章節部分的URL"""
    soup = BeautifulSoup(html, 'html.parser')
    for link in soup.find_all("a", href=True):
        if "下一頁" in link.text:
            next_url = urljoin(current_url, link["href"])
            print(f"Found next page link: {next_url}")  # Debug log
            return next_url
    print("No '下一頁' link found in the HTML.")
    return None

def get_section_info(html):
    """獲取當前章節部分的信息（如：2/5）"""
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.find("h1", class_="chapter-title")
    if title:
        match = re.search(r'\((\d+)/(\d+)\)', title.text)
        if match:
            current_section = int(match.group(1))
            total_sections = int(match.group(2))
            return current_section, total_sections
    return 1, 1

def get_images(html, url):
    imgs = []
    
    if is_korean_style_manga(html):
        from ..grabber import grabhtml
        current_url = url
        seen_urls = set()  # 避免循環引用
        
        while current_url and current_url not in seen_urls:
            seen_urls.add(current_url)
            
            # 獲取當前頁面的HTML
            current_html = html if current_url == url else grabhtml(current_url)
            if not current_html:
                print(f"Failed to load page: {current_url}")
                break  # 遇到無法抓取的頁面時跳出迴圈或加入重試機制
            
            # 獲取當前章節的分頁資訊
            current_section, total_sections = get_section_info(current_html)
            
            # 提取當前部分的所有圖片
            soup = BeautifulSoup(current_html, 'html.parser')
            for img in soup.find_all("img", src=True):
                if "comic" in img["src"]:
                    img_url = urljoin(current_url, img["src"])
                    if img_url not in imgs:  # 避免重複圖片
                        imgs.append(img_url)
            
            # Debug log 檢查抓取進展
            print(f"Collected {len(imgs)} images from section {current_section}/{total_sections}")
            
            # 如果還不是最後一個部分，獲取下一部分的URL
            next_url = get_next_section_url(current_html, current_url)
            if next_url:
                current_url = next_url
                print(f"Moving to next section URL: {current_url}")  # Debug log
            else:
                print("No next section URL found; assuming last section reached.")
                break
            
    else:
        # 原有的普通漫畫處理邏輯
        soup = BeautifulSoup(html, 'html.parser')
        for img in soup.find_all("img", src=True):
            if "comic" in img["src"]:
                img_url = urljoin(url, img["src"])
                imgs.append(img_url)
    
    return imgs

def get_next_page(html, url):
    """
    對於韓漫，返回None因為在get_images中已處理分頁
    對於一般漫畫，返回下一頁URL
    """
    if is_korean_style_manga(html):
        return None
    
    next_page = re.search(r'<a href="([^"]+)"[^>]*class="next"', html)
    return urljoin(url, next_page.group(1)) if next_page else None
