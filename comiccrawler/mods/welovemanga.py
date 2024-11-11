import re
import time
import os
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from comiccrawler.episode import Episode

# Domain and module information
domain = ["welovemanga.one"]
name = "WeLoveManga"
noepfolder = False  # 每集創建單獨文件夾
rest = 0.5            # 每張圖片下載間隔5秒
rest_analyze = 3    # 分析頁面間隔5秒

# 模組配置
config = {
    "use_largest_image": "true"
}

def get_title(html, url):
    """返回漫畫的標題，從 <ul class="manga-info"> 中的 <h3> 標籤提取。"""
    print("HTML 内容用于调试:", html[:500])  # 打印 HTML 内容的前500字符进行调试
    # 嘗試從 <ul class="manga-info"> 內的 <h3> 標籤中提取標題
    match = re.search(r'<ul class="manga-info">.*?<h3>(.+?)</h3>', html, re.DOTALL)
    if match:
        return match.group(1).strip()  # 提取標題並去除首尾空格
    else:
        raise ValueError("無法找到漫畫標題")

def get_episodes(html, url):
    """抓取漫畫章節"""
    episodes = []

    # 初始化無頭 Chrome 瀏覽器
    options = uc.ChromeOptions()
    options.add_argument("--headless")  # 後台運行，不顯示瀏覽器窗口
    options.add_argument("--disable-gpu")  # 禁用 GPU 加速
    options.add_argument("--no-sandbox")  # 解決某些環境下的錯誤
    driver = uc.Chrome(options=options)

    try:
        print(f"[get_episodes] 開始打開 URL: {url}")
        driver.get(url)

        # 等待頁面加載，並查找章節列表元素
        try:
            print("[get_episodes] 等待 .list-chapters 元素出現...")
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'list-chapters'))
            )
            print("[get_episodes] 成功找到 .list-chapters 元素")

            # 抓取章節列表
            chap_list = driver.find_element(By.CLASS_NAME, 'list-chapters')
            chapters = chap_list.find_elements(By.TAG_NAME, 'a')
            base_url = "https://welovemanga.one"

            for chapter in chapters:
                chapter_title = chapter.get_attribute('title')
                chapter_url = chapter.get_attribute('href')
                # 如果 href 是相對路徑，轉換為絕對 URL
                if not chapter_url.startswith("http"):
                    chapter_url = urljoin(base_url, chapter_url)
                episodes.append(Episode(title=chapter_title, url=chapter_url))

                # 打印提取的章節信息
                print(f"[get_episodes] 章節標題: {chapter_title}, URL: {chapter_url}")

        except Exception as e:
            print(f"[get_episodes] 無法抓取章節列表: {e}")

    finally:
        # 關閉瀏覽器
        print("[get_episodes] 關閉瀏覽器")
        driver.quit()

    return episodes

def get_images(html, url):
    """抓取漫畫頁面上的圖片"""
    print(f"Processing page: {url}")
    
    options = uc.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    driver = uc.Chrome(options=options)
    
    try:
        driver.get(url)
        
        # 首先等待 lazy_loading.gif 圖片出現並完成載入
        print("Waiting for lazy loading images...")
        wait = WebDriverWait(driver, 5)
        lazy_images = wait.until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "img.chapter-img[src*='lazy_loading.gif']")
            )
        )
        print(f"Found {len(lazy_images)} lazy loading images")
        
        # 等待每個 lazy_loading.gif 完成載入
        def wait_for_image_load(img_element):
            try:
                return img_element.get_attribute('complete') == 'true'
            except:
                return False
        
        for img in lazy_images:
            WebDriverWait(driver, 3).until(lambda d: wait_for_image_load(img))
        
        # 現在等待圖片被替換為實際內容
        def check_real_images():
            images = driver.find_elements(By.CSS_SELECTOR, "img.chapter-img")
            for img in images:
                try:
                    src = img.get_attribute('src')
                    srcset = img.get_attribute('data-srcset')
                    # 檢查是否仍然是 lazy_loading.gif
                    if 'lazy_loading.gif' in (src or '') and not srcset:
                        return False
                except:
                    return False
            return True
        
        print("Waiting for real images to load...")
        # 滾動頁面來觸發圖片載入
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        max_scroll_attempts = 5
        
        while scroll_attempts < max_scroll_attempts:
            # 滾動到頁面底部
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # 等待內容載入
            
            # 計算新的滾動高度
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                # 如果高度沒有變化，檢查圖片是否都已載入
                if check_real_images():
                    break
            last_height = new_height
            scroll_attempts += 1
            print(f"Scroll attempt {scroll_attempts}/{max_scroll_attempts}")
        
        # 收集實際圖片URL
        images = []
        img_elements = driver.find_elements(By.CSS_SELECTOR, "img.chapter-img")
        
        for img in img_elements:
            try:
                # 優先檢查 data-srcset
                srcset = img.get_attribute('data-srcset')
                if srcset and 'lazy_loading.gif' not in srcset:
                    # 提取實際URL（通常是第一個URL）
                    img_url = srcset.strip().split()[0]
                    if img_url:
                        images.append(img_url)
                        print(f"Found image URL from data-srcset: {img_url}")
                else:
                    # 檢查其他可能的屬性
                    src = img.get_attribute('src')
                    if src and 'lazy_loading.gif' not in src:
                        images.append(src)
                        print(f"Found image URL from src: {src}")
            except Exception as e:
                print(f"Error processing image element: {e}")
                continue
        
        if not images:
            print("Warning: No actual images found!")
            # 輸出當前頁面狀態以供調試
            print("Current page state:")
            print(driver.page_source[:1000])
        else:
            print(f"Successfully found {len(images)} images")
            
        return images
        
    finally:
        driver.quit()

def grabhandler(grab_method, url, **kwargs):
    """處理圖片下載請求"""
    options = {
        'headers': {
            'Referer': 'https://welovemanga.one/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9'
        }
    }
    kwargs.update(options)
    return grab_method(url, **kwargs)

def get_next_page(html, url):
    """返回下一页的URL（如果是多页的漫画）"""
    match = re.search(r"<a[^>]*?id=['\"]nextpage['\"][^>]*?href=['\"](.+?)['\"]>", html)
    if match:
        return urljoin(url, match.group(1))

def load_config():
    """当配置重载时调用"""
    pass

def grabhandler(grab_method, url, **kwargs):
    """检查是否有 'I Know' 按钮并点击"""
    # 不再进行 'I Know' 按钮的处理
    pass

if __name__ == "__main__":
    # 抓取漫画标题
    try:
        print("抓取漫画标题:")
        title = get_title("", url)
        print(f"漫画标题: {title}")
    except Exception as e:
        print(f"获取标题时发生错误: {e}")
