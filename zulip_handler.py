import threading
from database import create_connection, get_paper_by_zulip_topic
from gpt4o_technical_analyst import get_paper_embedding_db, answer_question
import logging
import zulip
from datetime import datetime, timezone
import re

logger = logging.getLogger("Huggingface daily papers")

try:
    zulip_client = zulip.Client(config_file=".zuliprc")
except:
    logger.error('zulip service down')

def post_to_zulip(topic, content):
    request = {
            "type": "stream",
            "to": "Paper_Reader",
            "topic": topic,
            "content": content,
        }

    result = zulip_client.send_message(request)
    logger.info(f'[zulip] message sent: {result}')


def handle_zulip_messages():
    last_message_time = datetime.now(timezone.utc)
    bot_email = zulip_client.email

    def on_message(msg):
        nonlocal last_message_time

        # 检查消息是否是新的
        message_time = datetime.fromtimestamp(msg['timestamp'], timezone.utc)
        if message_time <= last_message_time:
            return

        # 更新最后处理的消息时间
        last_message_time = message_time

        if msg['type'] == 'stream':
            content = msg['content']
            sender_email = msg['sender_email']
            stream_name = msg['display_recipient']
            topic = msg['subject']
            message_id = msg['id']  # 获取原始消息的ID

            # 检查消息是否来自其他用户（不是机器人自己）
            if sender_email == bot_email:
                return

            print(msg)
            if stream_name == 'Paper_Reader':

                is_quote_of_bot = '@_**PaperReaderBot' in content
                if is_quote_of_bot:
                    # 提取新的问题（去除引用部分）
                    match = re.search(r'```quote\n(.*?)\n```\n(.*)', content, re.DOTALL)
                    if match:
                        new_question = match.group(2).strip()
                    else:
                        new_question = content.split('```')[-1].strip()
                print('new question', new_question)
                return 
                with create_connection() as conn:
                    # 步骤1: 从数据库中查找匹配的论文
                    paper = get_paper_by_zulip_topic(conn, topic)                
                if not paper:
                    response = "抱歉，找不到與此主題相關的論文。"
                    logger.warning(f'{topic}: {response}')
                    return
                else:
                    # 步骤2: 获取论文的嵌入数据库
                    paper_id = paper['id']
                    paper_title = paper['title']
                    db, _ = get_paper_embedding_db(paper_id)
                    
                    if not db:
                        response = f"無法取得此論文 '{paper_title}' 的embedding db。"
                        logger.warning(f'{topic}: {response}')
                        return
                    else:
                        # 步骤3: 使用 answer_question 获取答案
                        answer = answer_question(db, content, paper_title)
                        response = answer #f"关于论文 '{paper_title}' 的回答：\n\n{answer}"

                # 构造引用回复
                quoted_content = f"> {content}\n\n{response}"

                # 发送引用回复
                zulip_client.send_message({
                    "type": "stream",
                    "to": stream_name,
                    "subject": topic,
                    "content": quoted_content,
                    "reply_to": message_id,  # 指定回复的消息ID
                })                

    thread = threading.Thread(target=zulip_client.call_on_each_message, args=(on_message,))
    thread.start()
