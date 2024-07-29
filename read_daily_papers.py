import os, logging, argparse
from logging.handlers import TimedRotatingFileHandler
from datetime import date, datetime, timedelta, timezone
import time, json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
import zulip

from grab_huggingface import fetch_huggingface_dailypapers, parse_data_to_json, parse_date
from gpt4o_technical_analyst import get_paper_embedding_db, answer_question
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
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=10, microsecond=0)
    return (next_midnight - now).total_seconds()


try:
    zulip_client = zulip.Client(config_file=".zuliprc")
except:
    print('zulip service down')

def post_to_zulip(title, content):
    request = {
            "type": "stream",
            "to": "Full Body Scanner",
            "topic": topic,
            "content": content,
        }

    result = zulip_client.send_message(request)

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Fetch daily papers and summarize content.")
    parser.add_argument('--init', action='store_true', help='Send report in the begining')
    # parser.add_argument('--notify', action='store_true', help='Send analysis report to line notify')        
    # parser.add_argument('--warpcast', action='store_true', help='post analysis report to warpcast')        
    # parser.add_argument('--tickers', type=str, nargs='+', default=['BTCUSD', 'ETHUSD', 'SOLUSD'], help='A list of ticker to fetch and analyze')
    args = parser.parse_args()

    logger.info(f"Start to daily summerized papers")

    system_json = read_system_info()

    t = str(date.today())
    
    # raw_text, text_file = fetch_huggingface_dailypapers()
    # huggingface_date = parse_date(raw_text)
    # if 'latest_update' not in system_json or huggingface_date != system_json['latest_update']:
    #     json_output, json_file = parse_data_to_json(raw_text)
    #     latest_update = json_output["date"]
    #     system_json['latest_update'] = latest_update
    #     write_system_info(system_json)

    with open('./huggingface_dailypaper/2024-07-29-huggingface_papers.json') as f:
        json_output = json.load(f)
        print(json_output['date'])

    system_json['latest_update'] = json_output["date"]
    write_system_info(system_json)        

    for paper in json_output['papers']:
        db = get_paper_embedding_db(paper['id'])
        if db:
            question = '請整理出內容大綱以淺顯易懂的詞彙表達，必要時請舉出例子。'
            answer = answer_question(db, question, paper['title'])
            print(answer)
        break


    while True:
        

        # Calculate the time to sleep until the next midnight (UTC)
        sleep_seconds = seconds_to_midnight()
        logger.info(f"Sleeping for {sleep_seconds} seconds. to get next report!!")
        print(f"Sleeping for {sleep_seconds} seconds. to get next report!!")
        time.sleep(sleep_seconds)
        

        # Execute the function at 00:00:00 UTC
        # update_data(args.tickers)        
        # try:
        #     r_file = price_trending_analyze_v2(args.tickers, True)
        # except Exception as e:
        #     logger.warning(f'failed to trending analyze: {e}') 

        # url = warpcast_post(r_file, args.tickers)

        # if url:
        #     send_to_line_notify(url, None)

        t = str(date.today())

        write_system_info()