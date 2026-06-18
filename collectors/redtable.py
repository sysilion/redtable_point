import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from datetime import datetime

# 초기 설정
base_url = "https://redtable.global/ko/must-eat/load-more"
params = {
    's_commercial_area_id': 234,
    's_must_eat_id': 8849,
    's_channel': 'redtable',
    'offset': 1,
    'tit_flag': 2
}
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}

# 결과를 저장할 리스트
results = []

# 오프셋 설정
offset = 1
limit = 5
total_processed = 0

while offset <= limit:
    print(f"Processing offset: {offset}")
    
    # 요청 파라미터 업데이트
    params['offset'] = offset
    
    # 요청 보내기
    response = requests.get(base_url, params=params, headers=headers)
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 카드 요소 추출
        cards = soup.find_all('div', class_='card-musteat')
        
        for card in cards:
            title_element = card.find('h3', class_='musteat-title')
            link_element = card.find('div', class_='content').find('div', class_='store').find('h3', class_='musteat-title')
            
            if title_element and link_element:
                title = title_element.get_text(strip=True).replace('\n', ' ')
                title = re.sub(r'\s+', ' ', title)
                link = card['onclick'].split("'")[1].replace('food','ko/food')
                
                # 매장 상세 페이지 요청
                store_response = requests.get(link, headers=headers)
                if store_response.status_code == 200:
                    store_soup = BeautifulSoup(store_response.content, 'html.parser')
                    
                    # 매장 주소 추출
                    address_element = store_soup.find('h5', id='address')
                    address = address_element.get_text(strip=True) if address_element else 'N/A'
                    
                    # 매장 전화번호 추출
                    phone_element = store_soup.find('div', class_='business-time').find('p')
                    phone = phone_element.get_text(strip=True) if phone_element else 'N/A'
                    
                    # 매장 카테고리 추출
                    category_element = store_soup.find('h4', class_='store-label')
                    category = category_element.get_text(strip=True).split('|')[0].strip() if category_element else 'N/A'
                    
                    # 지도 링크에서 위도와 경도 추출
                    map_element = store_soup.find('div', class_='store-map').find('a')
                    if map_element and 'href' in map_element.attrs:
                        map_url = map_element['href']
                        lat_lon_match = re.search(r'query=([\d.]+),([\d.]+)', map_url)
                        if lat_lon_match:
                            latitude = lat_lon_match.group(1)
                            longitude = lat_lon_match.group(2)
                        else:
                            latitude = 'N/A'
                            longitude = 'N/A'
                    else:
                        latitude = 'N/A'
                        longitude = 'N/A'
                    
                    # 결과 저장
                    results.append({
                        'Title': title,
                        'Link': link,
                        'Address': address,
                        'Phone': phone,
                        'Category': category,
                        'Latitude': latitude,
                        'Longitude': longitude
                    })
                    total_processed += 1
                else:
                    print(f"Failed to retrieve store details from {link} with status code {store_response.status_code}")
                
                # 1초 딜레이 추가
                time.sleep(1)
        
        print(f"Processed {len(cards)} stores at offset {offset}")
    else:
        print(f"Failed to retrieve data at offset {offset} with status code {response.status_code}")
        break
    
    offset += 1

# 결과를 DataFrame으로 변환
df = pd.DataFrame(results)

# 가게 이름으로 정렬
df = df.sort_values(by='Title')

# CSV 파일로 저장
df.to_csv('must_eat_data_'+datetime.now().strftime('%Y%m%d')+'.csv', index=False, encoding='utf-8-sig')

print(f"Total processed stores: {total_processed}")
print("Data saved to must_eat_data.csv")

