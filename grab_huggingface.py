import json
import os
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse
import requests
import logging, hashlib
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger("Huggingface daily papers")

if not os.path.exists('./huggingface_dailypaper'):
    os.mkdir('./huggingface_dailypaper')

if not os.path.exists('./paper_pdf'):
    os.mkdir('./paper_pdf')

def fetch_huggingface_dailypapers(url = "https://huggingface.co/papers"):

    t = date.today()
    output_file = f"./huggingface_dailypaper/{t}-huggingface_papers.txt"

    # Send a GET request to the URL
    response = requests.get(url)

    # Check if the request was successful
    if response.status_code == 200:
        # Get the raw text content
        raw_text = response.text
        
        hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        output_file = f"./huggingface_dailypaper/{t}-huggingface_papers-{hash}.txt"
        # Save the raw text to a file
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write(raw_text)
        
        print(f"Raw text content has been saved to {output_file}")
    else:
        print(f"Failed to retrieve the webpage. Status code: {response.status_code}")

    return raw_text, output_file, hash

def download_pdf(url, filename):
    if os.path.exists(filename):
        logger.info(f'pdf已存在: {filename}')
        return filename
    
    response = requests.get(url)
    if response.status_code == 200:
        with open(filename, 'wb') as f:
            f.write(response.content)
        print(f"Downloaded: {filename}")
    else:
        print(f"Failed to download: {url}")
        return ''

    return filename

def parse_date(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    page_title = soup.title.string if soup.title else "Daily Papers - Hugging Face"
    
    date_elem = soup.find('time')
    date = date_elem['datetime'].split('T')[0] if date_elem else str(datetime.now().date())

    return date

def parse_html_to_json(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    page_title = soup.title.string if soup.title else "Daily Papers - Hugging Face"
    
    date_elem = soup.find('time')
    date = date_elem['datetime'].split('T')[0] if date_elem else str(datetime.now().date())

    papers = []
    for article in soup.find_all('article'):
        paper = {}
        
        title_elem = article.find('h3')
        if title_elem and title_elem.a:
            paper['title'] = title_elem.a.text.strip()
            paper['link'] = f"https://huggingface.co{title_elem.a['href']}"
            
            # 解析链接以获取论文ID
            parsed_url = urlparse(paper['link'])
            paper_id = parsed_url.path.split('/')[-1]
            
            paper['id'] = paper_id
            # 构造arXiv PDF链接
            paper['pdf_link'] = f"https://arxiv.org/pdf/{paper_id}.pdf"
            
            # 下载PDF
            pdf_filename = download_pdf(paper['pdf_link'], f"./paper_pdf/{paper_id}.pdf")
            paper['local_pdf'] = pdf_filename
        
        authors = article.find_all('li', class_='text-gray-600')
        paper['authors'] = [author.text.strip() for author in authors if author.text.strip()]
        
        paper['publishedAt'] = article.find('time')['datetime'] if article.find('time') else None
        summary_elem = article.find('p', class_='line-clamp-3')
        paper['summary'] = summary_elem.text.strip() if summary_elem else None

        upvotes_elem = article.find('div', class_='leading-none')
        if upvotes_elem:
            try:
                paper['upvotes'] = int(upvotes_elem.text.strip())
            except ValueError:
                paper['upvotes'] = 0
        else:
            paper['upvotes'] = 0

        comments_elem = article.find('a', href=lambda x: x and '#community' in x)
        if comments_elem:
            try:
                paper['comments'] = int(comments_elem.text.strip())
            except ValueError:
                paper['comments'] = 0
        else:
            paper['comments'] = 0

        papers.append(paper)

    result = {
        "pageTitle": page_title,
        "date": date,
        "papers": papers
    }

    # return json.dumps(result, ensure_ascii=False, indent=2)
    return result

def parse_data_to_json(data, hash):
    
    html_content = data
    try: 
        # 读取txt文件
        with open(data, 'r', encoding='utf-8') as file:
            html_content = file.read()
    except:
        html_content = data

    # 解析HTML并生成JSON
    json_output = parse_html_to_json(html_content)

    t = date.today()    
    output_file = f"./huggingface_dailypaper/{t}-huggingface_papers-{hash}.json"
    json_output['output_file'] = output_file

    # 将JSON写入文件
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write(json.dumps(json_output, ensure_ascii=False, indent=2))

    print("JSON file has been created successfully.")

    return json_output, output_file
    