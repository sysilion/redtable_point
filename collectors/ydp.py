import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime


# 기본 URL
base_url = "https://ydp.redtable.global/ko/storeLoad?s_loc1=Korea&offset={}"

# 데이터를 저장할 리스트
data = []

# 오프셋 범위 설정 (1부터 51까지)
for offset in range(1, 100):
    # 실제 요청할 URL
    url = base_url.format(offset)
    
    # 페이지 요청
    response = requests.get(url)
    if response.status_code != 200:
        print(f"[오프셋 {offset}] 데이터 가져오기 실패: 상태 코드 {response.status_code}")
        continue

    # BeautifulSoup으로 HTML 파싱
    soup = BeautifulSoup(response.text, 'html.parser')

    # 원하는 데이터가 들어있는 div 태그 찾기
    places = soup.find_all('div', class_='col-lg-4 col-md-4')

    count_for_offset = 0  # 현재 오프셋에서 수집된 항목 수

    for place in places:
        # 가게 이름
        store_name = place.find('h3', id='store_name').text.strip()

        # 주소 및 전화번호
        store_name2 = place.find('p', id='store_name2').text.strip()
        address, phone = store_name2.rsplit(' ', 1)  # 마지막 부분이 전화번호로 가정

        # 카테고리 (음식 종류) - 쉼표 기준으로 첫 번째 카테고리만 추출
        category_span = place.find('span', class_='cate-nm')
        if category_span:
            category = category_span.text.split(',')[0].strip()  # 쉼표로 분리 후 첫 번째 항목 선택
        else:
            category = "N/A"  # 카테고리가 없을 경우

        # 가게 링크 - 전체 주소가 이미 href에 포함되어 있으므로 그대로 사용
        store_url = place.find('a')['href']

        # 수집한 데이터를 리스트에 추가
        data.append([store_name, address, phone, category, store_url])
        count_for_offset += 1

    # 현재 오프셋에서 수집된 데이터 수 출력
    print(f"[오프셋 {offset}] 수집된 항목 수: {count_for_offset}")
    if count_for_offset == 0:
        break

# 총 수집된 데이터 수 출력
total_count = len(data)
print(f"총 수집된 가게 수: {total_count}")

# 수집한 데이터를 DataFRame 으로 변환
df = pd.DataFrame(data, columns=['Title', 'Address', 'Phone', 'Category', 'Link'])

# 가게 이름으로 정렬
df = df.sort_values(by='Title')


# CSV 파일로 저장
df.to_csv('ydp_store_data_'+datetime.now().strftime('%Y%m%d')+'.csv', index=False, encoding='utf-8-sig')

print("Data collection complete. Saved to store_data.csv")

