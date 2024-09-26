import os, logging, argparse
from logging.handlers import TimedRotatingFileHandler
from datetime import date, datetime, timedelta, timezone
import sqlite3
import time, json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
import random, hashlib

from gpt4o_technical_analyst import sumarize_paper, load_paper
from database import create_connection, create_table, insert_paper, get_paper
from zulip_handler import post_to_zulip, handle_zulip_messages

import requests
# 
# logger init
#

logger = logging.getLogger("Reading papers")
logger.setLevel(logging.INFO)    


'''
Utility Functions
'''

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

def json_to_md(json_content, pdf_link):
    str = f'> ### {json_content["標題"]}\n'
    str += f'> [pdf]({pdf_link})\n\n'
    str += f'>#### 主題: {json_content["主題"]}\n\n'
    abstracts = '\n> - '.join(json_content["摘要"])
    str += f'>#### 摘要: \n> - {abstracts}\n\n'
    str += f'> {json_content["分析"]}\n\n'
    str += f'> {json_content["結論"]}\n\n'

    return str


import re

def extract_id_from_pdf_link(pdf_link):
    match = re.search(r'/(\d+\.\d+)\.pdf$', pdf_link)
    return match.group(1) if match else None

def write_md_file(paper_id, md_content):
    # 確保 ./md/ 目錄存在
    os.makedirs('./md', exist_ok=True)
    
    # 生成文件名
    file_name = f"./md/{paper_id}.md"
    
    # 寫入 Markdown 內容到文件
    with open(file_name, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    logger.info(f"已將 Markdown 內容寫入文件：{file_name}")

def download_pdf_if_not_exists(pdf_link, target_path):
    if os.path.exists(target_path):
        logger.info(f"PDF 文件已存在：{target_path}")
        return target_path
    
    # 確保目標目錄存在
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    
    # 下載 PDF
    pdf_filename = download_pdf(pdf_link, target_path)
    logger.info(f"已下載 PDF 文件：{pdf_filename}")
    return pdf_filename

def read_paper(zulip, papers_data):
    with create_connection() as conn:
    
        create_table(conn)
    
        for paper in papers_data:

            paper_id = extract_id_from_pdf_link(paper['pdf_link'])
                        
            if not paper_id:
                logger.warning(f"無法從 PDF 連結提取 ID: {paper['pdf_link']}")
                continue            

            existing_paper = get_paper(conn, paper_id)
            if not existing_paper:

                # download pdf
                paper['id'] = paper_id
                
                # 檢查並下載 PDF
                pdf_target_path = f"./paper_pdf/{paper_id}.pdf"
                pdf_filename = download_pdf_if_not_exists(paper['pdf_link'], pdf_target_path)
                paper['local_pdf'] = pdf_filename

                texts, docs = load_paper(pdf_filename)
                llm_res = sumarize_paper(texts, docs, paper['title'])
                logger.info(json.dumps(llm_res, ensure_ascii=False))
                md_content = json_to_md(llm_res, paper['pdf_link'])

                # 寫入 Markdown 文件
                write_md_file(paper_id, md_content)

                paper['summary'] = json.dumps(llm_res, ensure_ascii=False)                
                zulip_topic = f'{llm_res["短標題"]}'
                if zulip:
                    post_to_zulip(zulip_topic, md_content)
                paper['zulip_topic'] = zulip_topic
                
                insert_paper(conn, paper)

        
if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Fetch daily papers and summarize content.")
    parser.add_argument('--zulip', type=bool, help='disable zulip', default=True)
    parser.add_argument('--json_file', type=str, help='papers file path', default=None)
    # parser.add_argument('--notify', action='store_true', help='Send analysis report to line notify')        
    # parser.add_argument('--warpcast', action='store_true', help='post analysis report to warpcast')        
    # parser.add_argument('--tickers', type=str, nargs='+', default=['BTCUSD', 'ETHUSD', 'SOLUSD'], help='A list of ticker to fetch and analyze')
    args = parser.parse_args()

    logger.info(f"Start to daily summerized papers")

    if args.json_file:
        # 使用指定的 JSON 檔案
        with open(args.json_file, 'r', encoding='utf-8') as f:
            json_output = json.load(f)

        logger.info(f'從 {args.json_file} 讀取了 {len(json_output)} 篇論文')

        read_paper(args.zulip, json_output)

