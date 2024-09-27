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
        logger.info(f"Downloaded: {filename}")
    else:
        error_message = f"Failed to download: {url}. Status code: {response.status_code}"
        logger.error(error_message)
        raise Exception(error_message)

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
    # 嘗試匹配 /NNNN.NNNNN 格式，不限於 .pdf 結尾
    match = re.search(r'/(\d+\.\d+)(?:\.pdf)?(?:\?|$)', pdf_link)
    if match:
        return match.group(1)
    
    # 如果上面的匹配失敗，嘗試匹配最後一個斜槓後的數字（不包括文件擴展名）
    match = re.search(r'/(\d+)(?:\.\w+)?(?:\?|$)', pdf_link)
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

    return file_name

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

def write_error(information):
    # 確保日誌目錄存在
    log_dir = './log'
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, 'error.log')
    
    # 讀取現有的錯誤日誌（如果存在）
    existing_errors = []
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            try:
                existing_errors = json.load(f)
            except json.JSONDecodeError:
                # 如果文件不是有效的 JSON，我們將從空列表開始
                existing_errors = []
    
    # 添加時間戳到錯誤信息
    information['timestamp'] = datetime.now().isoformat()
    
    # 將新的錯誤信息添加到現有錯誤列表中
    existing_errors.append(information)
    
    # 將更新後的錯誤列表寫入文件
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(existing_errors, f, ensure_ascii=False, indent=2)
    
    logger.info(f"錯誤信息已寫入：{log_file}")

def read_paper(zulip, papers_data):

    with create_connection() as conn:
    
        create_table(conn)
    
        md_files = []
        for paper in papers_data:
            logger.info(f"start to read paper: {paper['title']}")

            paper_id = extract_id_from_pdf_link(paper['pdf_link'])
                        
            if not paper_id:
                logger.warning(f"無法從 PDF 連結提取 ID: {paper['pdf_link']}")
                write_error(
                    {
                        "message": f"無法從 PDF 連結提取 ID: {paper['pdf_link']}",
                        "pdf_link": paper['pdf_link'],
                        "title": paper['title']
                    }
                )
                continue            

            existing_paper = get_paper(conn, paper_id)
            if not existing_paper:

                # download pdf
                paper['id'] = paper_id
                
                # 檢查並下載 PDF
                pdf_target_path = f"./paper_pdf/{paper_id}.pdf"
                try:
                    pdf_filename = download_pdf_if_not_exists(paper['pdf_link'], pdf_target_path)
                except Exception as e:
                    write_error(
                        {
                            "message": f"下載檔案錯誤: {e}",
                            "pdf_link": paper['pdf_link'],
                            "title": paper['title']
                        }
                    )
                    continue

                paper['local_pdf'] = pdf_filename

                try:
                    texts, docs = load_paper(pdf_filename)
                    llm_res = sumarize_paper(texts, docs, paper['title'])
                    logger.info(json.dumps(llm_res, ensure_ascii=False))
                    md_content = json_to_md(llm_res, paper['pdf_link'])

                    # 寫入 Markdown 文件
                    md_file = write_md_file(paper_id, md_content)

                    paper['summary'] = json.dumps(llm_res, ensure_ascii=False)                
                    zulip_topic = f'{llm_res["短標題"]}'
                    if zulip:
                        post_to_zulip(zulip_topic, md_content)
                    paper['zulip_topic'] = zulip_topic
                    
                    insert_paper(conn, paper)

                    md_files.append(md_file)
                except Exception as e:
                    write_error(
                        {
                            "message": f"讀取檔案錯誤: {e}",
                            "pdf_link": paper['pdf_link'],
                            "title": paper['title'],
                            "file_path": paper['local_pdf']
                        }
                    )
                    # 嘗試刪除本地 PDF 文件
                    try:
                        if os.path.exists(paper['local_pdf']):
                            os.remove(paper['local_pdf'])
                            logger.info(f"已刪除錯誤的 PDF 文件: {paper['local_pdf']}")
                    except Exception as delete_error:
                        logger.error(f"無法刪除錯誤的 PDF 文件 {paper['local_pdf']}: {delete_error}")
                                        
                    continue


        logger.info(f'{len(md_files)} papers have been read!!!')

        
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

