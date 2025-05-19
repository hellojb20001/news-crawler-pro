import re
import datetime
import random # 랜덤 지연 위해 추가
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import time

# --- 기사 수집 로직 (수정: 순서 유지를 위해 list 사용 및 중복 제거 로직 변경) ---
def _collect_articles_from_elements(elements, article_class_pattern, articles_list_ref, seen_hrefs_ref):
    """
    주어진 웹 요소 리스트에서 조건에 맞는 기사(제목, 링크)를 찾아 list에 순서대로 추가합니다.
    seen_hrefs_ref set을 사용하여 중복된 기사(href 기준)는 추가하지 않습니다.
    페이지 정보를 <dt> 또는 <dd> 태그에서 찾아 제목에 추가합니다.
    """
    collected_count = 0
    for article_element in elements: # article_element는 일반적으로 <a> 태그입니다.
        try:
            # 클래스 속성 필터링
            class_string = article_element.get_attribute('class')
            if not class_string: continue
            classes = class_string.split()
            has_matching_class = False
            for cls in classes:
                if article_class_pattern.match(cls):
                    has_matching_class = True; break
            if not has_matching_class: continue

            # 제목 및 링크 추출
            title = article_element.text.strip()
            href = article_element.get_attribute('href')
            
            page_info_str = ""

            # --- 페이지 정보 추출 로직 (제공된 HTML 예시 기반) ---
            # Priority 1: <a> 태그를 포함하는 <dt> 태그 내에서 면 정보 찾기
            try:
                parent_dt = article_element.find_element(By.XPATH, "./parent::dt")
                newspaper_info_span = parent_dt.find_element(By.XPATH, "./span[@class='newspaper_info']")
                page_text = newspaper_info_span.text.strip()
                match = re.search(r"([A-Z]?\d+면)", page_text) 
                if match:
                    page_info_str = f"[{match.group(1)}] "
            except NoSuchElementException:
                pass 

            # Priority 2: <a> 태그를 포함하는 <dt> 태그의 다음 형제 <dd> 태그 내에서 면 정보 찾기
            if not page_info_str:
                try:
                    parent_dt = article_element.find_element(By.XPATH, "./parent::dt")
                    following_dd = parent_dt.find_element(By.XPATH, "./following-sibling::dd[1]")
                    newspaper_info_span = following_dd.find_element(By.XPATH, "./span[@class='newspaper_info']")
                    page_text = newspaper_info_span.text.strip()
                    match = re.search(r"([A-Z]?\d+면)", page_text)
                    if match:
                        page_info_str = f"[{match.group(1)}] "
                except NoSuchElementException:
                    pass
            # --- 페이지 정보 추출 로직 끝 ---

            # 유효성 검사
            if title and href and ('news.naver.com' in href or 'n.news.naver.com' in href):
               modified_title = f"{page_info_str}{title}"
               
               # 중복 제거 및 순서대로 리스트에 추가
               if href not in seen_hrefs_ref: # URL(href)을 기준으로 중복 확인
                    articles_list_ref.append((modified_title, href)) # 리스트에 추가하여 순서 유지
                    seen_hrefs_ref.add(href) # 중복 확인을 위해 set에 href 추가
                    # print(f"  [수집] {modified_title}") # 상세 로그 필요시 주석 해제
                    collected_count += 1
        except StaleElementReferenceException: pass
        except Exception as article_err:
             print(f"  개별 기사 처리 오류: {article_err} - {title[:50] if title else '제목 없음'}")
    return collected_count

# --- 신문사별 크롤링 함수 (수정: articles를 list로 변경, seen_hrefs set 추가) ---
def crawl_newspaper_articles(driver, newspaper_name, oid, crawl_scope="전체"):
    articles_ordered_list = []  # 수집된 기사를 순서대로 저장할 리스트
    seen_article_hrefs = set()  # 이미 수집된 기사의 href를 저장하여 중복 방지
    
    wait = WebDriverWait(driver, 10)
    article_class_pattern = re.compile(r'^nclicks\(cnt_papaerart\d+\)$')

    try:
        start_url = f"https://news.naver.com/main/list.naver?mode=LPOD&mid=sec&oid={oid}&listType=paper"
        driver.get(start_url)
        print(f"접속 완료: {newspaper_name} 신문게재기사 페이지 ({start_url})")

        content_selector = "div.list_body.newsflash_body" 
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, content_selector)))
            print("기사 목록 영역 로딩 확인.")
        except TimeoutException:
            print(f"경고: {newspaper_name}에서 기사 목록 영역 로딩 시간 초과.")
            
        if crawl_scope == "1면":
            print(f"\n--- {newspaper_name} '1면' 기사만 수집 시작 ---")
            is_1men_section = False
            try:
                elements_selector = f"{content_selector} h4.paper_h4, {content_selector} a[class*='nclicks(cnt_papaerart']"
                elements_for_1st_page = [] # 1면 기사 링크 요소만 저장할 리스트
                
                # 잠재적 요소들을 먼저 모두 가져옵니다.
                all_potential_elements = []
                try:
                    all_potential_elements = WebDriverWait(driver, 5).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, elements_selector))
                    )
                except TimeoutException:
                     print(f"1면 스캔: 시간 내 요소를 찾지 못했습니다 ({elements_selector}).")

                print(f"1면 스캔: {len(all_potential_elements)}개의 잠재적 요소 발견 (h4, a)")

                for element in all_potential_elements:
                    try:
                        tag = element.tag_name
                        if tag == 'h4':
                            header_text = element.text.strip()
                            if header_text.endswith("1면"):
                                print(f"1면 섹션 시작 확인: '{header_text}'")
                                is_1men_section = True
                            elif is_1men_section: # 다른 면으로 넘어갔다고 판단
                                print(f"1면 섹션 종료 확인: 다음 헤더 '{header_text}' 발견.")
                                is_1men_section = False
                                # 1면 섹션이 끝났으므로 더 이상 h4, a 요소를 볼 필요가 없을 수 있음 (페이지 구조에 따라 다름)
                                # 여기서는 루프를 계속 진행하여 다른 '1면' 섹션이 또 나올 가능성을 대비합니다.
                        elif tag == 'a' and is_1men_section:
                            elements_for_1st_page.append(element)
                    except StaleElementReferenceException:
                        print("  처리 중 Stale 발생 (1면 스캔 중). 요소 건너뜀.")
                        continue 

                # 1면으로 식별된 요소들에 대해서만 기사 수집
                _collect_articles_from_elements(elements_for_1st_page, article_class_pattern, articles_ordered_list, seen_article_hrefs)
                print(f"{newspaper_name} '1면'에서 {len(articles_ordered_list)}개의 기사 수집 완료 (중복제거 후).")


            except Exception as e1:
                print(f"{newspaper_name} '1면' 수집 중 오류: {e1}")

        elif crawl_scope == "전체":
            print(f"\n--- {newspaper_name} '전체' 기사 수집 시작 ---")
            num_categories_to_process = 0
            category_box_selector = ".topbox_type6"
            category_button_selector = f"{category_box_selector} ul li a[class*='nclicks(cnt_order)']"
            total_buttons_found = 0
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, category_box_selector)))
                initial_category_buttons = driver.find_elements(By.CSS_SELECTOR, category_button_selector)
                total_buttons_found = len(initial_category_buttons)
                if total_buttons_found == 0:
                    print(f"{newspaper_name}: 카테고리 탭 없음.")
                    num_categories_to_process = 0
                else:
                    num_categories_to_process = (total_buttons_found + 1) // 2
                    print(f"총 {total_buttons_found}개 버튼 발견, {num_categories_to_process}개 카테고리 처리 예정.")
            except TimeoutException:
                print(f"{newspaper_name}: 카테고리 탭 영역 로딩 실패 또는 없음.")
                num_categories_to_process = 0
            except Exception as e:
                print(f"{newspaper_name}: 카테고리 탭 개수 확인 중 오류: {e}.")
                num_categories_to_process = 0

            if num_categories_to_process > 0:
                for i in range(num_categories_to_process):
                    print(f"\n--- {newspaper_name} 카테고리 {i+1}/{num_categories_to_process} 처리 시작 ---")
                    current_category_name = f"카테고리 {i+1}"
                    retries = 3; success = False
                    for attempt in range(retries):
                        try:
                            # 각 카테고리 버튼을 다시 찾음 (페이지 변경으로 인해 stale 될 수 있으므로)
                            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, category_box_selector)))
                            category_buttons = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, category_button_selector)))
                            
                            if i >= len(category_buttons): # 버튼 개수가 동적으로 변할 경우 방지
                                print(f"오류: 카테고리 버튼 인덱스 ({i}) 범위를 벗어남. (버튼 수: {len(category_buttons)})")
                                time.sleep(0.5); continue

                            try:
                                current_category_name = category_buttons[i].text.strip()
                                if not current_category_name: current_category_name = f"카테고리 {i+1}"
                            except StaleElementReferenceException: 
                                print("카테고리 이름 가져오기 실패 (Stale). 재시도...")
                                time.sleep(0.5); continue
                            except Exception as name_err:
                                print(f"카테고리 이름 가져오기 중 기타 오류: {name_err}")


                            if i > 0: # 첫 번째 카테고리는 이미 로드된 상태일 수 있으므로 클릭하지 않음
                                button_to_click = category_buttons[i]
                                try:
                                    print(f"카테고리 클릭 시도: '{current_category_name}'")
                                    wait.until(EC.element_to_be_clickable(button_to_click))
                                    driver.execute_script("arguments[0].click();", button_to_click)
                                    # 콘텐츠 영역이 다시 로드되거나, 특정 요소가 나타날 때까지 기다리는 것이 좋음
                                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, content_selector))) 
                                    time.sleep(random.uniform(0.5, 1.0)) # 페이지 로드 대기 시간 추가
                                except StaleElementReferenceException: 
                                    print(f"'{current_category_name}' 클릭 시도 중 Stale 발생. 재시도...")
                                    time.sleep(0.5); continue
                                except TimeoutException: 
                                    print(f"'{current_category_name}' 클릭 후 콘텐츠 로딩 타임아웃. 다음 시도 또는 카테고리.")
                                    time.sleep(0.5); continue 
                                except Exception as click_err: 
                                    print(f"'{current_category_name}' 클릭 중 오류: {click_err}. 다음 시도 또는 카테고리.")
                                    time.sleep(0.5); continue 
                            else:
                                print(f"초기 카테고리 처리 중 (클릭 없음): '{current_category_name}'")
                            
                            print(f"'{current_category_name}' 카테고리 기사 수집 중...")
                            potential_article_links_selector = f"{content_selector} a[class*='nclicks(cnt_papaerart']"
                            potential_elements = []
                            try:
                                potential_elements = WebDriverWait(driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, potential_article_links_selector)))
                            except TimeoutException:
                                print(f"'{current_category_name}'에서 기사 링크를 시간 내 찾지 못했습니다.")

                            # _collect_articles_from_elements 함수에 articles_ordered_list와 seen_article_hrefs 전달
                            _collect_articles_from_elements(potential_elements, article_class_pattern, articles_ordered_list, seen_article_hrefs)
                            print(f"'{current_category_name}' 카테고리에서 추가된 기사 수 확인 (누적: {len(articles_ordered_list)}개).")
                            success = True; break 
                        except StaleElementReferenceException: 
                            print(f"StaleElementReferenceException 발생 (카테고리 루프, 시도 {attempt+1}/{retries}). 재시도 중...")
                            time.sleep(0.5 + attempt * 0.5) 
                        except TimeoutException: 
                            print(f"TimeoutException 발생 (카테고리 루프, 시도 {attempt+1}/{retries}). 재시도 중...")
                            time.sleep(0.5 + attempt * 0.5)
                        except Exception as category_err:
                           print(f"카테고리 처리 중 기타 오류: {category_err}. 다음 카테고리로 이동 시도."); success = True; break # 심각한 오류 시 해당 카테고리 처리 중단
                    if not success: print(f"!!! 카테고리 '{current_category_name}' 처리 최종 실패.")
            else: 
                print(f"\n--- {newspaper_name} 첫 페이지만 수집 시도 (카테고리 없음) ---")
                potential_article_links_selector = f"{content_selector} a[class*='nclicks(cnt_papaerart']"
                potential_elements = []
                try:
                    potential_elements = WebDriverWait(driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, potential_article_links_selector)))
                except TimeoutException:
                    print(f"첫 페이지에서 기사 링크를 시간 내 찾지 못했습니다.")
                
                _collect_articles_from_elements(potential_elements, article_class_pattern, articles_ordered_list, seen_article_hrefs)
                print(f"첫 페이지에서 추가된 기사 수 확인 (누적: {len(articles_ordered_list)}개).")

        print(f"\n=== {newspaper_name} 최종 기사 수집 완료 ({len(articles_ordered_list)}개) ===")
        return articles_ordered_list # set 대신 순서가 유지된 list 반환

    except Exception as e:
        print(f"!!! {newspaper_name} 크롤링 중 심각한 오류 발생: {e}")
        return articles_ordered_list # 오류 발생 시에도 현재까지 수집된 기사 반환


# --- main 함수 ---
# (main 함수는 변경되지 않았으므로 이전과 동일하게 유지됩니다.
#  결과를 파일에 쓸 때 articles_ordered_list를 순회하므로 순서대로 저장됩니다.)
def main():
    # --- 신문사 그룹 정의 ---
    newspaper_groups = {
        "economic": [
            ("매일경제", "009"), ("머니투데이", "008"), ("서울경제", "011"),
            ("아시아경제", "277"), ("이데일리", "018"), ("파이낸셜뉴스", "014"),
            ("한국경제", "015"), ("헤럴드경제", "016")
        ],
        "general": [
            ("경향신문", "032"), ("국민일보", "005"), ("동아일보", "020"),
            ("문화일보", "021"), ("서울신문", "081"), ("세계일보", "022"),
            ("조선일보", "023"), ("중앙일보", "025"), ("한겨레", "028"),
            ("한국일보", "469"), ("디지털타임스", "029"), ("전자신문", "030")
        ],
        "evening": [
            ("문화일보", "021"), ("헤럴드경제", "016"), ("아시아경제", "277")
        ]
    }
    all_papers_set = set(newspaper_groups['economic']) | set(newspaper_groups['general']) | set(newspaper_groups['evening'])
    newspaper_groups['all'] = sorted(list(all_papers_set))

    # --- 사용자 입력 1: 신문 그룹 선택 ---
    print("-" * 30)
    print("크롤링할 신문 그룹을 선택하세요:")
    print("  1: 전체 신문")
    print("  2: 경제 신문")
    print("  3: 종합 일간지")
    print("  4: 석간 신문")
    print("-" * 30)
    choice = ""
    while choice not in ['1', '2', '3', '4']:
        choice = input("번호를 입력하세요 (1-4): ")
    selected_key = ""
    if choice == '1': selected_key = 'all'; group_name = "전체"
    elif choice == '2': selected_key = 'economic'; group_name = "경제"
    elif choice == '3': selected_key = 'general'; group_name = "종합"
    elif choice == '4': selected_key = 'evening'; group_name = "석간"
    target_newspapers = newspaper_groups[selected_key]
    print(f"\n▶ '{group_name}' 그룹 ({len(target_newspapers)}개 언론사) 선택됨.")

    # --- 사용자 입력 2: 수집 범위 선택 ---
    print("\n수집 범위를 선택하세요:")
    print("  1: 전체 기사 (선택된 그룹의 모든 카테고리 또는 첫 페이지)")
    print("  2: 1면 기사만 (선택된 그룹의 첫 페이지만)")
    print("-" * 30)
    scope_choice = ""
    while scope_choice not in ['1', '2']:
        scope_choice = input("번호를 입력하세요 (1-2): ")
    crawl_scope = "전체" if scope_choice == '1' else "1면"
    print(f"\n▶ 수집 범위: '{crawl_scope}' 선택됨.")
    print("-" * 30)


    # --- Selenium 설정 ---
    chrome_options = Options()
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    driver = webdriver.Chrome(options=chrome_options)

    all_collected_articles_by_newspaper = {} # 결과 저장용 딕셔너리
    try:
        # --- 크롤링 루프 ---
        for name, oid in target_newspapers:
            print(f"\n{'='*10} {name} (oid={oid}) 크롤링 시작 ({crawl_scope} 범위) {'='*10}")
            # crawl_newspaper_articles 함수는 이제 순서가 있는 list를 반환합니다.
            ordered_articles_for_newspaper = crawl_newspaper_articles(driver, name, oid, crawl_scope)
            all_collected_articles_by_newspaper[name] = ordered_articles_for_newspaper
            print(f"{name}에서 수집된 총 기사 수: {len(ordered_articles_for_newspaper)}")
            time.sleep(random.uniform(1.0, 2.5))

        # --- 파일 저장 ---
        now = datetime.datetime.now()
        filename = f"신문기사_{group_name}_{crawl_scope}_{now.strftime('%Y%m%d_%H%M%S')}.txt"
        print(f"\n크롤링 결과를 '{filename}' 파일에 저장합니다...")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"네이버 뉴스 '{group_name}' 그룹 '{crawl_scope}' 범위 크롤링 결과\n")
                f.write(f"생성 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("="*50 + "\n\n")
                if not all_collected_articles_by_newspaper:
                    f.write("수집된 신문사가 없습니다.\n")
                else:
                    for newspaper_name_key, article_tuples_list in all_collected_articles_by_newspaper.items():
                        f.write(f"--- {newspaper_name_key} ({len(article_tuples_list)}개) ---\n\n")
                        if not article_tuples_list:
                            f.write("수집된 기사가 없습니다.\n\n")
                        else:
                            # article_tuples_list는 이미 순서가 유지된 리스트입니다.
                            for idx, (title_text, link_url) in enumerate(article_tuples_list, 1):
                                f.write(f"{idx}. 제목: {title_text}\n")
                                f.write(f"   링크: {link_url}\n\n")
                        f.write("-" * 50 + "\n\n")
            print(f"결과를 '{filename}' 파일에 성공적으로 저장했습니다.")
        except Exception as e_file:
            print(f"파일 저장 중 오류 발생: {e_file}")

    finally:
        print("\n브라우저를 종료합니다.")
        driver.quit()

if __name__ == "__main__":
    main()