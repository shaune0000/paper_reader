import os
import base64
from openai import OpenAI
from langchain.chat_models import ChatOpenAI
from langchain.document_loaders import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import FAISS
from langchain.chains.question_answering import load_qa_chain
from langchain.chains.summarize import load_summarize_chain
from langchain.llms import OpenAI
from langchain.prompts import PromptTemplate
from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.schema.messages import HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain.schema import Document

from pathlib import Path
import logging
import warnings
import re
import json
from dotenv import load_dotenv
load_dotenv()


logger = logging.getLogger("Huggingface daily papers")


OPENAI_API_KEY = os.environ['OPENAI_API_KEY']
OPENAI_ORG_ID = os.environ['OPENAI_ORG_ID']

client = OpenAI(organization=OPENAI_ORG_ID)
llm = ChatOpenAI(
    temperature=0,
    openai_api_key=OPENAI_API_KEY,
    model_name="gpt-4o-mini",
)

class Transcription(BaseModel):
    title_hook: str = Field(description="shorten title in 40 characters.")
    reply_content: str = Field(description="main content.")

if not os.path.exists('./embedding_db'):
    os.mkdir('./embedding_db')

def load_paper(pdf_path):
    loader = PyPDFLoader(pdf_path)
    pages = loader.load_and_split()
    text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    texts = text_splitter.split_documents(pages)
    return texts, pages

def create_embeddings_and_db(texts):
    embeddings = OpenAIEmbeddings()
    db = FAISS.from_documents(texts, embeddings)
    return db

def save_db(db, path):
    db.save_local(path)

def load_db(path):
    embeddings = OpenAIEmbeddings()
    return FAISS.load_local(path, embeddings, allow_dangerous_deserialization=True)

def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')
  
def answer_question(db, question, paper_title):
    # 創建系統消息模板
    system_template = """你是一個專門回答有關科學論文問題的AI助手。你的任務是根據標題為《{title}》的論文提供準確且相關的信息。
        如果在給定的上下文中找不到答案，請說‘在文獻中找不到相關的訊息來回答這個問題。’請始終保持專業和學術的語氣。"""

    system_message_prompt = SystemMessagePromptTemplate.from_template(system_template)

    # 創建人類消息模板
    human_template = "Context: {context}\n\問題: {question}"
    human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

    # 組合聊天提示模板
    chat_prompt = ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])

    # 載入 QA 鏈
    chain = load_qa_chain(llm, chain_type="stuff", prompt=chat_prompt)

    # 執行相似性搜索
    docs = db.similarity_search(question)

    # 運行鏈並返回答案
    return chain.run(input_documents=docs, question=question, title=paper_title)


def sumarize_paper(texts, docs, paper_title):
    response_schemas = [
        ResponseSchema(name="標題", description="文本標題"),
        ResponseSchema(name="短標題", description="40個字元內的短標題"),
        ResponseSchema(name="主題", description="列出文檔的主要主題"),
        ResponseSchema(name="摘要", description="條列出關鍵點摘要", type="List[string]"),
        ResponseSchema(name="分析", description="提供對文檔內容的簡短分析"),
        ResponseSchema(name="結論", description="總結文檔的主要結論或建議"),
    ]
    output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
    format_instructions = output_parser.get_format_instructions()

    system_template = """
        你是一個專業的科學家、文檔分析助手並閱讀了很多論文。
        你的任務是閱讀提供的文本，並生成一個結構化的摘要和分析。
        你能夠提供正確且豐富的訊息，也能夠分析、列表及總結這篇論文的內容。
        所有的資訊都是基於這篇論文"{title}"的內容而闡述。
        
        % 回應的語氣:

        - 你的回答應該以積極的語氣給出並固執己見
        - 你的語氣應該嚴肅，帶有一絲機智和諷刺
        - 你的回答淺顯易懂，必要時會舉出列子
        
        % 回應的規格:
        
        - 回應簡潔、清晰且信息豐富
        - 特別注意與標題 "{title}" 相關的內容
        - 不要用表情符號回應
        
        % 回應的內容:

        - 列出論文的目的
        - 討論論文方法
        - 分析改進項目或是提出貢獻內容
        - 未來還能夠朝哪個方向前進
        - 提出此篇論文是否存在矛盾論點
        - 結論是否有更值得探索的議題

        % 回應格式:
            {format_instructions}
        
    """      

    # system_message_prompt = SystemMessagePromptTemplate.from_template(system_template)
    system_message_prompt = SystemMessagePromptTemplate.from_template(system_template, 
                                                                      input_variables=["title", "format_instructions"])

    human_template = "請分析並總結以下文本:\n\n{text}"
    human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

    chat_prompt = ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])

    # get a completed chat
    chain = load_summarize_chain(
        llm,
        chain_type="stuff",
        prompt=chat_prompt,
        document_variable_name="text"
    )

    summary = chain.run({"input_documents": docs, "title": paper_title, "format_instructions": format_instructions})
    return output_parser.parse(summary)

def get_paper_embedding_db(paper_id):
    # 確定數據庫文件路徑
    db_path = f"./embedding_db/{paper_id}.db"    

    # 檢查是否已經存在向量數據庫
    db = None
    texts = None
    if os.path.exists(db_path):
        print("Loading existing vector database...")
        db = load_db(db_path)
    else:
        print("Creating new vector database...")
        pdf_path = f'./paper_pdf/{paper_id}.pdf'
        if os.path.exists(pdf_path):
            texts, _ = load_paper(pdf_path)
            db = create_embeddings_and_db(texts)
            save_db(db, db_path)                    
        else:
            return None
        
    return db, texts
   
def generate_image(prompt, size="1792x1024", style = "vivid"):
    logger.info(f'[gpt] generate image with prompts: {prompt}')
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            response_format="url",
            n=1,
            quality="hd",
            size=size, #['256x256', '512x512', '1024x1024', '1024x1792', '1792x1024'] 
            style=style, #['vivid', 'natural']
        )    
        return response.data[0].url
    except Exception as e:
        logger.error(f'[gpt] failed to generate image: {e}')
        return None    

def remove_markdown_code_blocks(markdown_text):
    # This regex matches code blocks in Markdown (``` followed by code and then ending with ```)
    code_block_regex = re.compile(r'```[a-zA-Z0-9]*\n(.*?)```', re.DOTALL)
    
    # Find all matches
    matches = code_block_regex.findall(markdown_text)
    
    # Join all code blocks into a single string, separated by newlines
    code_only = '\n'.join(matches)
    
    return code_only
