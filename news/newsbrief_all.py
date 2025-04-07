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

# --- 기사 수집 로직 (중복 제거 위해 별도 함수로 분리) ---
def _collect_articles_from_elements(elements, article_class_pattern, articles_set):
    """
    주어진 웹 요소 리스트에서 조건에 맞는 기사(제목, 링크)를 찾아 set에 추가합니다.
    """
    collected_count = 0
    for article_element in elements:
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

            # 유효성 검사 및 set에 추가
            if title and href and ('news.naver.com' in href or 'n.news.naver.com' in href):
               article_tuple = (title, href)
               if article_tuple not in articles_set:
                    articles_set.add(article_tuple)
                    # print(f"  [수집] {title}") # 상세 로그 필요시 주석 해제
                    collected_count += 1
        except StaleElementReferenceException: pass # Stale 요소는 건너<0xEB><0x9B><0xB0>
        except Exception as article_err:
             print(f"  개별 기사 처리 오류: {article_err}")
    return collected_count

# --- 신문사별 크롤링 함수 (수정) ---
def crawl_newspaper_articles(driver, newspaper_name, oid, crawl_scope="전체"):
    articles = set() # (제목, 링크) 튜플 저장
    wait = WebDriverWait(driver, 10)
    article_class_pattern = re.compile(r'^nclicks\(cnt_papaerart\d+\)$')

    try:
        start_url = f"https://news.naver.com/main/list.naver?mode=LPOD&mid=sec&oid={oid}&listType=paper"
        driver.get(start_url)
        print(f"접속 완료: {newspaper_name} 신문게재기사 페이지 ({start_url})")

        # 초기 페이지 로딩 대기 (어떤 스코프든 필요)
        content_selector = "div.list_body.newsflash_body" # 메인 콘텐츠 영역
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, content_selector)))
            print("기사 목록 영역 로딩 확인.")
        except TimeoutException:
            print(f"경고: {newspaper_name}에서 기사 목록 영역 로딩 시간 초과.")
            # 로딩 실패해도 일단 진행 (구조가 다를 수 있음)

        # ==============================================
        # === 수집 범위에 따른 로직 분기 ===
        # ==============================================
        if crawl_scope == "1면":
            # --- Logic for 1면 only ---
            print(f"\n--- {newspaper_name} '1면' 기사만 수집 시작 ---")
            is_1men_section = False
            try:
                # h4 헤더와 잠재적 기사 링크를 모두 찾음
                elements_selector = f"{content_selector} h4.paper_h4, {content_selector} a[class*='nclicks(cnt_papaerart']"
                elements = []
                try:
                     # 요소들이 나타날 때까지 잠시 기다림 (5초)
                    elements = WebDriverWait(driver, 5).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, elements_selector))
                    )
                except TimeoutException:
                     print(f"1면 스캔: 시간 내 요소를 찾지 못했습니다 ({elements_selector}).")


                print(f"1면 스캔: {len(elements)}개의 잠재적 요소 발견 (h4, a)")
                front_page_elements = [] # 1면 섹션의 링크만 저장할 리스트

                for element in elements:
                    try:
                        tag = element.tag_name
                        if tag == 'h4':
                            header_text = element.text.strip()
                            # "A1면", "1면" 등 '1면'으로 끝나는지 확인
                            if header_text.endswith("1면"):
                                print(f"1면 섹션 시작 확인: '{header_text}'")
                                is_1men_section = True
                            elif is_1men_section:
                                # 1면 섹션 진행 중 다른 헤더 만나면 종료
                                print(f"1면 섹션 종료 확인: 다음 헤더 '{header_text}' 발견.")
                                is_1men_section = False
                                break # 1면 영역 벗어났으므로 요소 탐색 중단
                        elif tag == 'a' and is_1men_section:
                            # 1면 섹션 내의 링크 요소이면 리스트에 추가
                            front_page_elements.append(element)
                    except StaleElementReferenceException:
                        print("  처리 중 Stale 발생. 요소 건너<0xEB><0x9B><0xB0>.")
                        continue # 다음 요소 처리

                # 1면 섹션에서 찾은 링크들에 대해 기사 수집 함수 호출
                collected_count = _collect_articles_from_elements(front_page_elements, article_class_pattern, articles)
                print(f"{newspaper_name} '1면'에서 {collected_count}개의 기사 수집 완료.")

            except Exception as e1:
                print(f"{newspaper_name} '1면' 수집 중 오류: {e1}")

        elif crawl_scope == "전체":
            # --- Logic for all categories (기존 로직) ---
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
                # 카테고리 순회
                for i in range(num_categories_to_process):
                    print(f"\n--- {newspaper_name} 카테고리 {i+1}/{num_categories_to_process} 처리 시작 ---")
                    # ... (카테고리 클릭 및 페이지 업데이트 대기 로직 - 이전과 동일) ...
                    current_category_name = f"카테고리 {i+1}"
                    retries = 3; success = False
                    for attempt in range(retries):
                       # ...(이하 카테고리 클릭 및 기사 수집 로직은 이전 답변과 동일하게 유지)...
                        try:
                            # (A) 버튼 재탐색
                            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, category_box_selector)))
                            category_buttons = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, category_button_selector)))
                            if i >= len(category_buttons): time.sleep(0.5); continue

                            # (B) 이름 가져오기 및 클릭 (i > 0)
                            try:
                                current_category_name = category_buttons[i].text.strip()
                                if not current_category_name: current_category_name = f"카테고리 {i+1}"
                            except StaleElementReferenceException: time.sleep(0.5); continue
                            except Exception: pass

                            if i > 0:
                                button_to_click = category_buttons[i]
                                try:
                                    wait.until(EC.element_to_be_clickable(button_to_click))
                                    driver.execute_script("arguments[0].click();", button_to_click)
                                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, content_selector)))
                                    time.sleep(0.3)
                                except StaleElementReferenceException: time.sleep(0.5); continue
                                except TimeoutException: success = True; break
                                except Exception: success = True; break
                            else:
                                print(f"초기 카테고리 처리 중: '{current_category_name}'")


                            # (C) 기사 수집
                            print(f"'{current_category_name}' 카테고리 기사 수집 중...")
                            potential_article_links_selector = f"{content_selector} a[class*='nclicks(cnt_papaerart']"
                            potential_elements = []
                            try:
                                potential_elements = WebDriverWait(driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, potential_article_links_selector)))
                            except TimeoutException:
                                print(f"'{current_category_name}'에서 기사 링크를 시간 내 찾지 못했습니다.")

                            # 분리된 함수 호출하여 기사 수집
                            collected_count = _collect_articles_from_elements(potential_elements, article_class_pattern, articles)
                            print(f"'{current_category_name}' 카테고리에서 {collected_count}개의 새 기사 수집 완료.")
                            success = True; break # 성공 시 재시도 중단

                        except StaleElementReferenceException: time.sleep(0.5)
                        except TimeoutException: time.sleep(0.5)
                        except Exception as category_err:
                           print(f"카테고리 처리 중 오류: {category_err}."); success = True; break
                    if not success: print(f"!!! 카테고리 {i+1} 처리 최종 실패.")
            else:
                 # 카테고리 탭이 없는 경우 첫 페이지만 처리
                print(f"\n--- {newspaper_name} 첫 페이지만 수집 시도 (카테고리 없음) ---")
                potential_article_links_selector = f"{content_selector} a[class*='nclicks(cnt_papaerart']"
                potential_elements = []
                try:
                    potential_elements = WebDriverWait(driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, potential_article_links_selector)))
                except TimeoutException:
                    print(f"첫 페이지에서 기사 링크를 시간 내 찾지 못했습니다.")

                collected_count = _collect_articles_from_elements(potential_elements, article_class_pattern, articles)
                print(f"첫 페이지에서 {collected_count}개의 새 기사 수집 완료.")


        print(f"\n=== {newspaper_name} 최종 기사 수집 완료 ({len(articles)}개) ===")
        return list(articles)

    except Exception as e:
        print(f"!!! {newspaper_name} 크롤링 중 심각한 오류 발생: {e}")
        return list(articles)


# --- main 함수 수정 ---
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

    all_articles = {}
    try:
        # --- 크롤링 루프 ---
        for name, oid in target_newspapers:
            print(f"\n{'='*10} {name} (oid={oid}) 크롤링 시작 ({crawl_scope} 범위) {'='*10}")
            # 선택된 수집 범위 전달
            articles_list = crawl_newspaper_articles(driver, name, oid, crawl_scope)
            all_articles[name] = articles_list
            print(f"{name}에서 수집된 총 기사 수: {len(articles_list)}")
            time.sleep(random.uniform(1.0, 2.5))

        # --- 파일 저장 ---
        now = datetime.datetime.now()
        # 파일 이름에 그룹명과 범위 포함
        filename = f"신문기사_{group_name}_{crawl_scope}_{now.strftime('%Y%m%d_%H%M%S')}.txt"
        print(f"\n크롤링 결과를 '{filename}' 파일에 저장합니다...")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"네이버 뉴스 '{group_name}' 그룹 '{crawl_scope}' 범위 크롤링 결과\n")
                f.write(f"생성 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("="*50 + "\n\n")
                if not all_articles:
                    f.write("수집된 신문사가 없습니다.\n")
                else:
                    for newspaper_name, article_tuples in all_articles.items():
                        f.write(f"--- {newspaper_name} ({len(article_tuples)}개) ---\n\n")
                        if not article_tuples:
                            f.write("수집된 기사가 없습니다.\n\n")
                        else:
                            for idx, (title, link) in enumerate(article_tuples, 1):
                                f.write(f"{idx}. 제목: {title}\n")
                                f.write(f"   링크: {link}\n\n")
                        f.write("-" * 50 + "\n\n")
            print(f"결과를 '{filename}' 파일에 성공적으로 저장했습니다.")
        except Exception as e:
            print(f"파일 저장 중 오류 발생: {e}")

    finally:
        print("\n브라우저를 종료합니다.")
        driver.quit()

if __name__ == "__main__":
    main()


# import re
# import datetime
# from selenium import webdriver
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.common.by import By
# from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
# import time

# # 공통 함수: 특정 신문사의 조간신문 기사 크롤링 (제목, 링크 반환)
# # (이 함수는 이전과 동일하게 유지됩니다)
# def crawl_newspaper_articles(driver, newspaper_name, oid):
#     articles = set() # (제목, 링크) 튜플 저장
#     wait = WebDriverWait(driver, 10)
#     article_class_pattern = re.compile(r'^nclicks\(cnt_papaerart\d+\)$')

#     try:
#         start_url = f"https://news.naver.com/main/list.naver?mode=LPOD&mid=sec&oid={oid}&listType=paper"
#         driver.get(start_url)
#         print(f"접속 완료: {newspaper_name} 신문게재기사 페이지 ({start_url})")

#         try:
#             wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.list_body.newsflash_body")))
#             print("기사 목록 영역 로딩 확인.")
#         except TimeoutException:
#             print(f"경고: {newspaper_name}에서 기사 목록 영역 로딩 시간 초과. 구조가 다를 수 있습니다.")


#         num_categories_to_process = 0 # 처리할 고유 카테고리 수
#         category_box_selector = ".topbox_type6"
#         category_button_selector = f"{category_box_selector} ul li a[class*='nclicks(cnt_order)']"
#         total_buttons_found = 0 # 초기화 추가
#         try:
#             wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, category_box_selector)))
#             initial_category_buttons = driver.find_elements(By.CSS_SELECTOR, category_button_selector)
#             total_buttons_found = len(initial_category_buttons) # 여기서 값 할당

#             if total_buttons_found == 0:
#                 print(f"{newspaper_name}: 카테고리 탭을 찾을 수 없습니다. 첫 페이지만 수집합니다.")
#                 num_categories_to_process = 0
#             else:
#                 num_categories_to_process = (total_buttons_found + 1) // 2 # 홀수도 처리하도록 +1 후 정수나누기
#                 print(f"총 {total_buttons_found}개 버튼 발견, {num_categories_to_process}개 카테고리 처리 예정.")


#         except TimeoutException:
#             print(f"{newspaper_name}: 카테고리 탭 영역('.topbox_type6') 로딩 실패 또는 없음. 첫 페이지만 수집 시도.")
#             num_categories_to_process = 0
#         except Exception as e:
#             print(f"{newspaper_name}: 카테고리 탭 개수 확인 중 오류: {e}. 첫 페이지만 수집 시도.")
#             num_categories_to_process = 0


#         if num_categories_to_process > 0:
#             for i in range(num_categories_to_process):
#                 print(f"\n--- {newspaper_name} 카테고리 {i+1}/{num_categories_to_process} 처리 시작 ---")
#                 current_category_name = f"카테고리 {i+1}"

#                 retries = 3
#                 success = False
#                 for attempt in range(retries):
#                     try:
#                         wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, category_box_selector)))
#                         category_buttons = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, category_button_selector)))

#                         if i >= len(category_buttons):
#                             print(f"오류: 인덱스 {i} 버튼 찾기 실패. 재시도 {attempt + 1}/{retries}")
#                             time.sleep(0.5); continue

#                         try:
#                             current_category_name = category_buttons[i].text.strip()
#                             if not current_category_name: current_category_name = f"카테고리 {i+1}"
#                         except StaleElementReferenceException:
#                             print(f"이름 가져오기 실패 (Stale). 재시도 {attempt + 1}/{retries}")
#                             time.sleep(0.5); continue
#                         except Exception as name_err:
#                             print(f"이름 가져오기 오류: {name_err}")

#                         if i > 0:
#                             button_to_click = category_buttons[i]
#                             print(f"카테고리 클릭 시도: '{current_category_name}' (버튼 인덱스 {i})")
#                             try:
#                                 wait.until(EC.element_to_be_clickable(button_to_click))
#                                 driver.execute_script("arguments[0].click();", button_to_click)
#                                 print(f"'{current_category_name}' 클릭 완료.")
#                                 wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.list_body.newsflash_body")))
#                                 print("페이지 업데이트 후 기사 목록 영역 로딩 확인.")
#                                 time.sleep(0.3)
#                             except StaleElementReferenceException:
#                                 print(f"클릭 시도 중 Stale 발생. 재시도 {attempt + 1}/{retries}")
#                                 time.sleep(0.5); continue
#                             except TimeoutException:
#                                 print(f"클릭 불가 또는 타임아웃. 다음 카테고리로...")
#                                 success = True; break
#                             except Exception as click_err:
#                                 print(f"클릭 중 오류: {click_err}. 다음 카테고리로...")
#                                 success = True; break
#                         else:
#                             print(f"초기 카테고리 처리 중: '{current_category_name}'")

#                         print(f"'{current_category_name}' 카테고리 기사 수집 중 (패턴 필터링)...")
#                         potential_article_links_selector = "div.list_body.newsflash_body a[class*='nclicks(cnt_papaerart']"
#                         potential_elements = []
#                         try:
#                             potential_elements = WebDriverWait(driver, 5).until(
#                                 EC.presence_of_all_elements_located((By.CSS_SELECTOR, potential_article_links_selector))
#                             )
#                         except TimeoutException:
#                             print(f"'{current_category_name}'에서 잠재적 기사 링크({potential_article_links_selector})를 시간 내 찾지 못했습니다.")


#                         collected_count = 0
#                         for article_element in potential_elements:
#                             try:
#                                 class_string = article_element.get_attribute('class')
#                                 if not class_string: continue
#                                 classes = class_string.split()
#                                 has_matching_class = False
#                                 for cls in classes:
#                                     if article_class_pattern.match(cls):
#                                         has_matching_class = True; break
#                                 if not has_matching_class: continue

#                                 title = article_element.text.strip()
#                                 href = article_element.get_attribute('href')

#                                 if title and href and ('news.naver.com' in href or 'n.news.naver.com' in href):
#                                    article_tuple = (title, href)
#                                    if article_tuple not in articles:
#                                         articles.add(article_tuple)
#                                         collected_count += 1
#                             except StaleElementReferenceException: pass
#                             except Exception as article_err:
#                                  print(f"  개별 기사 처리 오류: {article_err}")

#                         print(f"'{current_category_name}' 카테고리에서 패턴과 일치하는 {collected_count}개의 새 기사 수집 완료.")
#                         success = True
#                         break

#                     except StaleElementReferenceException:
#                         print(f"카테고리 {i+1} 처리 중 Stale 발생. 재시도 {attempt + 1}/{retries}")
#                         time.sleep(0.5)
#                     except TimeoutException:
#                         print(f"카테고리 {i+1} 처리 중 타임아웃 발생. 재시도 {attempt + 1}/{retries}")
#                         time.sleep(0.5)
#                     except Exception as category_err:
#                         print(f"카테고리 {i+1} 처리 중 예상치 못한 오류 발생: {category_err}. 다음 카테고리로.")
#                         success = True; break

#                 if not success:
#                     print(f"!!! 카테고리 {i+1} 처리 최종 실패. 다음 카테고리로 넘어갑니다.")
#         else:
#             # --- 카테고리 탭이 없는 경우, 첫 페이지만 수집 시도 ---
#             print(f"\n--- {newspaper_name} 첫 페이지만 수집 시도 (카테고리 없음 또는 로딩 실패) ---")
#             potential_article_links_selector = "div.list_body.newsflash_body a[class*='nclicks(cnt_papaerart']"
#             potential_elements = []
#             try:
#                 potential_elements = WebDriverWait(driver, 5).until(
#                     EC.presence_of_all_elements_located((By.CSS_SELECTOR, potential_article_links_selector))
#                 )
#             except TimeoutException:
#                  print(f"첫 페이지에서 잠재적 기사 링크({potential_article_links_selector})를 시간 내 찾지 못했습니다.")

#             collected_count = 0
#             for article_element in potential_elements:
#                 try:
#                     class_string = article_element.get_attribute('class')
#                     if not class_string: continue
#                     classes = class_string.split()
#                     has_matching_class = False
#                     for cls in classes:
#                         if article_class_pattern.match(cls):
#                             has_matching_class = True; break
#                     if not has_matching_class: continue

#                     title = article_element.text.strip()
#                     href = article_element.get_attribute('href')

#                     if title and href and ('news.naver.com' in href or 'n.news.naver.com' in href):
#                        article_tuple = (title, href)
#                        if article_tuple not in articles:
#                             articles.add(article_tuple)
#                             collected_count += 1
#                 except StaleElementReferenceException: pass
#                 except Exception as article_err:
#                      print(f"  개별 기사 처리 오류: {article_err}")
#             print(f"첫 페이지에서 패턴과 일치하는 {collected_count}개의 새 기사 수집 완료.")

#         print(f"\n=== {newspaper_name} 최종 기사 수집 완료 ({len(articles)}개) ===")
#         return list(articles)

#     except Exception as e:
#         print(f"!!! {newspaper_name} 크롤링 중 심각한 오류 발생: {e}")
#         return list(articles)


# # --- main 함수 수정 ---
# def main():
#     # --- 신문사 그룹 정의 ---
#     newspaper_groups = {
#         "economic": [
#             ("매일경제", "009"), ("머니투데이", "008"), ("서울경제", "011"),
#             ("아시아경제", "277"), ("이데일리", "018"), ("파이낸셜뉴스", "014"),
#             ("한국경제", "015"), ("헤럴드경제", "016") # 석간에도 포함됨
#         ],
#         "general": [
#             ("경향신문", "032"), ("국민일보", "005"), ("동아일보", "020"),
#             ("문화일보", "021"), # 석간에도 포함됨
#             ("서울신문", "081"), ("세계일보", "022"),
#             ("조선일보", "023"), ("중앙일보", "025"), ("한겨레", "028"),
#             ("한국일보", "469"), ("디지털타임스", "029"), ("전자신문", "030")
#         ],
#         "evening": [
#             ("문화일보", "021"), ("헤럴드경제", "016"), ("아시아경제", "277")
#         ]
#     }
#     # 'all' 그룹 생성 (모든 그룹의 unique한 신문사 리스트, 이름순 정렬)
#     all_papers_set = set(newspaper_groups['economic']) | set(newspaper_groups['general']) | set(newspaper_groups['evening'])
#     newspaper_groups['all'] = sorted(list(all_papers_set))

#     # --- 사용자 입력 받기 ---
#     print("-" * 30)
#     print("크롤링할 신문 그룹을 선택하세요:")
#     print("  1: 전체 신문")
#     print("  2: 경제 신문")
#     print("  3: 종합 일간지")
#     print("  4: 석간 신문")
#     print("-" * 30)

#     choice = ""
#     while choice not in ['1', '2', '3', '4']:
#         choice = input("번호를 입력하세요 (1-4): ")
#         if choice not in ['1', '2', '3', '4']:
#             print("잘못된 입력입니다. 1, 2, 3, 4 중 하나를 입력하세요.")

#     # 선택된 그룹 키 결정
#     selected_key = ""
#     if choice == '1': selected_key = 'all'; group_name = "전체 신문"
#     elif choice == '2': selected_key = 'economic'; group_name = "경제 신문"
#     elif choice == '3': selected_key = 'general'; group_name = "종합 일간지"
#     elif choice == '4': selected_key = 'evening'; group_name = "석간 신문"

#     # 크롤링 대상 목록 설정
#     target_newspapers = newspaper_groups[selected_key]
#     print(f"\n▶ '{group_name}' 그룹 ({len(target_newspapers)}개 언론사) 크롤링을 시작합니다...")
#     print("-" * 30)


#     # --- Selenium 설정 ---
#     chrome_options = Options()
#     # chrome_options.add_argument("--headless")
#     chrome_options.add_argument("--start-maximized")
#     chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")
#     chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
#     chrome_options.add_experimental_option('useAutomationExtension', False)
#     chrome_options.add_argument('--disable-blink-features=AutomationControlled')
#     driver = webdriver.Chrome(options=chrome_options)


#     all_articles = {} # 결과 저장용 딕셔너리

#     try:
#         # --- 선택된 그룹의 신문사 목록으로 크롤링 실행 ---
#         for name, oid in target_newspapers: # 선택된 리스트 사용
#             print(f"\n{'='*10} {name} (oid={oid}) 크롤링 시작 {'='*10}")
#             articles_list = crawl_newspaper_articles(driver, name, oid)
#             all_articles[name] = articles_list
#             print(f"{name}에서 수집된 총 기사 수: {len(articles_list)}")
#             # 서버 부하를 줄이기 위해 약간의 지연 시간 추가
#             time.sleep(random.uniform(1.0, 2.5)) # 1초 ~ 2.5초 사이 랜덤 지연


#         # --- 모든 크롤링 완료 후 파일 저장 ---
#         now = datetime.datetime.now()
#         # 파일 이름에 선택한 그룹명도 포함
#         filename = f"신문기사_{group_name}_{now.strftime('%Y%m%d_%H%M%S')}.txt"
#         print(f"\n크롤링 결과를 '{filename}' 파일에 저장합니다...")

#         try:
#             with open(filename, "w", encoding="utf-8") as f:
#                 f.write(f"네이버 뉴스 '{group_name}' 크롤링 결과\n") # 그룹명 명시
#                 f.write(f"생성 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
#                 f.write("="*50 + "\n\n")

#                 if not all_articles:
#                     f.write("수집된 신문사가 없습니다.\n")
#                 else:
#                     for newspaper_name, article_tuples in all_articles.items():
#                         f.write(f"--- {newspaper_name} ({len(article_tuples)}개) ---\n\n")
#                         if not article_tuples:
#                             f.write("수집된 기사가 없습니다.\n\n")
#                         else:
#                             for idx, (title, link) in enumerate(article_tuples, 1):
#                                 f.write(f"{idx}. 제목: {title}\n")
#                                 f.write(f"   링크: {link}\n\n")
#                         f.write("-" * 50 + "\n\n")

#             print(f"결과를 '{filename}' 파일에 성공적으로 저장했습니다.")

#         except Exception as e:
#             print(f"파일 저장 중 오류 발생: {e}")

#     finally:
#         print("\n브라우저를 종료합니다.")
#         driver.quit()

# # 스크립트 실행 시 main 함수 호출
# if __name__ == "__main__":
#     # 랜덤 지연을 위해 random 모듈 임포트 (파일 상단에도 추가 가능)
#     import random
#     main()