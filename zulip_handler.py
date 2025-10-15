import threading
from database import create_connection, get_paper_by_zulip_topic
from gpt4o_technical_analyst import get_paper_embedding_db, answer_question
import logging
import zulip
from datetime import datetime, timezone
import re

logger = logging.getLogger("Huggingface daily papers")

# 初始化 Zulip 客戶端
zulip_client = None

try:
    zulip_client = zulip.Client(config_file=".zuliprc")
    logger.info('Zulip client initialized successfully')
except FileNotFoundError:
    logger.error('Zulip config file .zuliprc not found')
except Exception as e:
    logger.error(f'Failed to initialize Zulip client: {type(e).__name__} - {e}')

def post_to_zulip(topic, content):
    """
    發送訊息到 Zulip stream

    Args:
        topic: 主題名稱
        content: 訊息內容

    Returns:
        發送結果或 None（若客戶端不可用）
    """
    if zulip_client is None:
        logger.warning('Zulip client not available, skipping message post')
        return None

    request = {
        "type": "stream",
        "to": "Paper_Reader",
        "topic": topic,
        "content": content,
    }

    try:
        result = zulip_client.send_message(request)
        logger.info(f'[zulip] message sent: {result}')
        return result
    except Exception as e:
        logger.error(f'Failed to send message to Zulip: {type(e).__name__} - {e}')
        return None


def handle_zulip_messages():
    """
    啟動 Zulip 訊息處理執行緒
    """
    if zulip_client is None:
        logger.error('Cannot handle Zulip messages: client not initialized')
        return

    last_message_time = datetime.now(timezone.utc)

    try:
        bot_email = zulip_client.email
    except Exception as e:
        logger.error(f'Failed to get bot email: {e}')
        return

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
            sender_full_name = msg['sender_full_name']

            # 检查消息是否来自其他用户（不是机器人自己）
            if sender_email == bot_email:
                return

            if stream_name == 'Paper_Reader':
                logger.info(f'got a message: {msg}')
                is_quote_of_bot = '@_**PaperReaderBot' in content or '@**PaperReaderBot**' in content
                if is_quote_of_bot:
                    # 提取新的问题（去除引用部分）
                    match = re.search(r'```quote\n(.*?)\n```\n(.*)', content, re.DOTALL)
                    if match:
                        new_question = match.group(2).strip()
                    else:
                        new_question = content.split('```')[-1].strip()
                else:
                    logger.info(f'receive a message, but not the question for bot')
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
                # quoted_content = f"> {content}\n\n{response}"
                # 构造回复内容，包括引用和 @ 标记
                quoted_content = f"@_**{sender_full_name}** 問道：\n```quote\n{new_question}\n```\n\n{response}"

                # 发送引用回复
                try:
                    zulip_client.send_message({
                        "type": "stream",
                        "to": stream_name,
                        "subject": topic,
                        "content": quoted_content,
                        "reply_to": message_id,  # 指定回复的消息ID
                    })
                    logger.info(f'Successfully replied to question in topic: {topic}')
                except Exception as e:
                    logger.error(f'Failed to send reply to Zulip: {type(e).__name__} - {e}')

    try:
        thread = threading.Thread(target=zulip_client.call_on_each_message, args=(on_message,), daemon=True)
        thread.start()
        logger.info('Zulip message handler thread started successfully')
    except Exception as e:
        logger.error(f'Failed to start Zulip message handler thread: {type(e).__name__} - {e}')
