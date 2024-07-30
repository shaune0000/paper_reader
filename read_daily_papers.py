import os, logging, argparse
from logging.handlers import TimedRotatingFileHandler
from datetime import date, datetime, timedelta, timezone
import sqlite3
import time, json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
import random, hashlib

from grab_huggingface import fetch_huggingface_dailypapers, parse_data_to_json
from gpt4o_technical_analyst import sumarize_paper, load_paper
from database import create_connection, create_table, insert_paper, get_paper
from zulip_handler import post_to_zulip, handle_zulip_messages

# 
# logger init
#
dir_path = os.path.dirname(os.path.realpath(__file__))
log_dir_path = f"{dir_path}/log"
Path(log_dir_path).mkdir(parents=True, exist_ok=True)
logname = log_dir_path+"/daily_papers.log"

logger = logging.getLogger("Huggingface daily papers")
logger.setLevel(logging.INFO)    

formatter = logging.Formatter('%(asctime)s|%(name)s|%(levelname)s|%(message)s')
rh = TimedRotatingFileHandler(logname, when='midnight', interval=1)
rh.setLevel(logging.INFO)
rh.suffix = "%Y%m%d"
#TimedRotatingFileHandler对象自定义日志格式
rh.setFormatter(formatter)
logger.addHandler(rh)    #logger日志对象加载TimedRotatingFileHandler对象


'''
Utility Functions
'''

def write_system_info(json_data, output_file='./read_paper.json'):
    # 将JSON写入文件
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write(json.dumps(json_data, indent=4))

def read_system_info(input_file='./read_paper.json'):
    data = {}
    # JSON file
    try:
        with open (input_file, "r") as f:
            data = json.loads(f.read())     
    except:
        pass

    return data   

def seconds_to_midnight():
    now = datetime.now(timezone.utc)
    next_midnight = (now + timedelta(days=1)).replace(hour=4, minute=0, second=0, microsecond=0)
    return (next_midnight - now).total_seconds()

def random_sleep():
    sleep_time = random.randint(1800, 3600)  # 30分钟到1小时之间的随机时间
    logger.info(f"Sleeping for {sleep_time} seconds before next update.")
    time.sleep(sleep_time)

def json_to_md(json_content, link, pdf_link):
    str = f'> ### {json_content["標題"]}\n'
    str += f'> [huggingface]({link}), [pdf]({pdf_link})\n\n'
    str += f'>#### 主題: {json_content["主題"]}\n\n'
    abstracts = '\n> - '.join(json_content["摘要"])
    str += f'>#### 摘要: \n> - {abstracts}\n\n'
    str += f'> {json_content["分析"]}\n\n'
    str += f'> {json_content["結論"]}\n\n'

    return str



# def update_paper(system_json):
#     json_output = {}
#     raw_text, text_file = fetch_huggingface_dailypapers()
#     huggingface_date = parse_date(raw_text)
#     if 'latest_update' not in system_json or huggingface_date != system_json['latest_update']:
#         json_output, json_file = parse_data_to_json(raw_text)
#         system_json['latest_update'] = json_output["date"]
#         write_system_info(system_json)
#     elif 'latest_update' in system_json and huggingface_date == system_json['latest_update']:
#         logger.info('paper are latest, no need to update')
#         return system_json

#     # with open('./huggingface_dailypaper/2024-07-30-huggingface_papers.json') as f:
#     #     json_output = json.load(f)
#     #     print(json_output['date'])

#     # system_json['latest_update'] = json_output["date"]
#     # write_system_info(system_json)        
#     if 'papers' in json_output:
#         for paper in json_output['papers']:
#             # for QA
#             # db, _ = get_paper_embedding_db(paper['id'])
#             # if db:
#             #     answer = answer_question(db, paper['title'])
#             #     print(answer)

#             texts, docs = load_paper(f"./paper_pdf/{paper['id']}.pdf")
#             llm_res = sumarize_paper(texts, docs, paper['title'])
#             res = json_to_md(llm_res, paper['link'], paper['pdf_link'])
#             print(res)

#             zulip_topic = f'{json_output["date"]} {llm_res["短標題"]}'
#             post_to_zulip(zulip_topic, res)
#             paper['zulip_topic'] = zulip_topic
#             json_output['papers'] = paper
        
#         # 将更新JSON写回文件
#         with open(json_output['output_file'], 'w', encoding='utf-8') as file:
#             file.write(json.dumps(json_output, ensure_ascii=False, indent=2))   
#     else:
#         logger.error(f'fetching peper is empty')

#     return system_json

def update_paper():
    with create_connection() as conn:
    
        create_table(conn)
    
        raw_text, _, hash = fetch_huggingface_dailypapers()    
        json_output, _ = parse_data_to_json(raw_text, hash)
        # with open('./huggingface_dailypaper/2024-07-30-huggingface_papers-15d3e0242235caf391dfb98edac8c34a2b105aeba6bd8730f580fc2db43242d4.json') as f:
        #     json_output = json.load(f)
        #     print(json_output['date'])

        logger.info(f'update huggingface: {json_output["date"]} with papers: {len(json_output.get("papers", []))}')

        for paper in json_output['papers']:
            existing_paper = get_paper(conn, paper['id'])
            if not existing_paper:
                texts, docs = load_paper(f"./paper_pdf/{paper['id']}.pdf")
                llm_res = sumarize_paper(texts, docs, paper['title'])
                logger.info(json.dumps(llm_res, ensure_ascii=False))
                print(llm_res)
                res = json_to_md(llm_res, paper['link'], paper['pdf_link'])

                paper['summary'] = json.dumps(llm_res, ensure_ascii=False)
                zulip_topic = f'{json_output["date"]} {llm_res["短標題"]}'
                post_to_zulip(zulip_topic, res)
                paper['zulip_topic'] = zulip_topic
                
                insert_paper(conn, paper)
        
if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Fetch daily papers and summarize content.")
    parser.add_argument('--init', action='store_true', help='Send report in the begining')
    # parser.add_argument('--notify', action='store_true', help='Send analysis report to line notify')        
    # parser.add_argument('--warpcast', action='store_true', help='post analysis report to warpcast')        
    # parser.add_argument('--tickers', type=str, nargs='+', default=['BTCUSD', 'ETHUSD', 'SOLUSD'], help='A list of ticker to fetch and analyze')
    args = parser.parse_args()

    logger.info(f"Start to daily summerized papers")

    logger.info('enable zulip message handler')
    handle_zulip_messages()

    while True:
        
        update_paper()
        logger.info('sleep for next update')
        random_sleep()

