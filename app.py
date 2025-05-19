from flask import Flask, render_template, request, jsonify
from news.newsbrief_all import crawl_newspaper_articles
from config import newspaper_groups
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import datetime
import random
import time
import json
import os

app = Flask(__name__)

# --- 신문사 그룹 정의 ---
all_papers_set = set(newspaper_groups['economic']) | set(newspaper_groups['general']) | set(newspaper_groups['evening'])
newspaper_groups['all'] = sorted(list(all_papers_set))

def setup_chrome_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--no-sandbox")  # Required for some Linux environments
    chrome_options.add_argument("--disable-dev-shm-usage")  # Required for some Linux environments
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    
    # Create results directory if it doesn't exist
    if not os.path.exists('results'):
        os.makedirs('results')
    
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

@app.route('/')
def index():
    return render_template('index.html', newspaper_groups=newspaper_groups)

@app.route('/crawl', methods=['POST'])
def crawl():
    selected_newspapers = json.loads(request.form.get('selected_newspapers', '[]'))
    crawl_scope = request.form.get('scope', '전체')
    
    if not selected_newspapers:
        return jsonify({'error': '신문사를 선택해주세요.'}), 400
    
    # Create a mapping of newspaper names to their OIDs
    newspaper_oid_map = {}
    for group in newspaper_groups.values():
        for name, oid in group:
            newspaper_oid_map[name] = oid
    
    all_articles = {}
    driver = setup_chrome_driver()
    
    try:
        for newspaper_name in selected_newspapers:
            if newspaper_name in newspaper_oid_map:
                oid = newspaper_oid_map[newspaper_name]
                articles_list = crawl_newspaper_articles(driver, newspaper_name, oid, crawl_scope)
                all_articles[newspaper_name] = articles_list
                time.sleep(random.uniform(1.0, 2.5))
        
        # Generate filename
        now = datetime.datetime.now()
        filename = f"results/신문기사_{now.strftime('%Y%m%d_%H%M%S')}.txt"
        
        # Save results to file
        with open(filename, "w", encoding="utf-8") as f:
            f.write("📰 오늘의 신문 기사 모음\n\n")
            
            if not all_articles:
                f.write("수집된 신문사가 없습니다.\n")
            else:
                for newspaper_name, article_tuples in all_articles.items():
                    f.write(f"📌 [{newspaper_name}]\n")
                    if not article_tuples:
                        f.write("수집된 기사가 없습니다.\n\n")
                    else:
                        for title, link in article_tuples:
                            f.write(f"🔹 {title}\n")
                    f.write("\n")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'articles': all_articles
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        driver.quit()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
