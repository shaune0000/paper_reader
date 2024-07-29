import os
import base64
from openai import OpenAI
from langchain.chat_models import ChatOpenAI
from langchain.document_loaders import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import FAISS
from langchain.chains.question_answering import load_qa_chain
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
    text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
    texts = text_splitter.split_documents(pages)
    return texts

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
  
# def answer_question(db, question, paper_title):
#     # 創建系統消息模板
#     system_template = """You are an AI assistant specialized in answering questions about scientific papers. 
#     Your task is to provide accurate and relevant information based on the paper titled "{title}".
#     If the answer cannot be found in the given context, please say "I don't have enough information to answer this question."
#     Always maintain a professional and academic tone in your responses."""

#     system_message_prompt = SystemMessagePromptTemplate.from_template(system_template)

#     # 創建人類消息模板
#     human_template = "Context: {context}\n\nQuestion: {question}"
#     human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

#     # 組合聊天提示模板
#     chat_prompt = ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])

#     # 載入 QA 鏈
#     chain = load_qa_chain(llm, chain_type="stuff", prompt=chat_prompt)

#     # 執行相似性搜索
#     docs = db.similarity_search(question)

#     # 運行鏈並返回答案
#     return chain.run(input_documents=docs, question=question, title=paper_title)


def answer_question(db, question, paper_title):
    response_schemas = [
        ResponseSchema(name="title", description="A short title (max 40 characters) summarizing the answer"),
        ResponseSchema(name="content", description="The detailed answer to the question")
    ]
    output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
    format_instructions = output_parser.get_format_instructions()

    system_template = """You are an AI assistant specialized in answering questions about scientific papers. 
    Your task is to provide accurate and relevant information based on the paper titled "{title}".
    If the answer cannot be found in the given context, please say "I don't have enough information to answer this question."
    Always maintain a professional and academic tone in your responses.
    {format_instructions}"""

    system_message_prompt = SystemMessagePromptTemplate.from_template(system_template)

    human_template = "Context: {context}\n\nQuestion: {question}"
    human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

    chat_prompt = ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])

    chain = load_qa_chain(llm, chain_type="stuff", prompt=chat_prompt)

    docs = db.similarity_search(question)

    result = chain.run(input_documents=docs, question=question, title=paper_title, format_instructions=format_instructions)
    
    print(result)
    return output_parser.parse(result)

def get_paper_embedding_db(paper_id):
    # 確定數據庫文件路徑
    db_path = f"./embedding_db/{paper_id}.db"    

    # 檢查是否已經存在向量數據庫
    db = None
    if os.path.exists(db_path):
        print("Loading existing vector database...")
        db = load_db(db_path)
    else:
        print("Creating new vector database...")
        pdf_path = f'./paper_pdf/{paper_id}.pdf'
        if os.path.exists(pdf_path):
            texts = load_paper(pdf_path)
            db = create_embeddings_and_db(texts)
            save_db(db, db_path)                    
        else:
            return None
        
    return db
   
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
    
def sumerize_paper_content_langchain(paper_pdf_file):
           
    system_template = """
        You are an incredibly wise and smart quantitative analyst that lives and breathes the world of quantitative finance.
        Your goal is to analyze and write a report given price trending charts in the area of cryptocurrency.
        
        % RESPONSE TONE:

        - Your response should be given in an active voice and be opinionated
        - Your tone should be serious w/ a hint of wit and sarcasm
        
        % RESPONSE FORMAT:
        
        - Be extremely clear and concise
        - Respond with phrases detailedly
        - Do not respond with emojis
        - Respond with no markdown
        
        % RESPONSE CONTENT:

        - Analyze these charts of trading trends in different time zones. 
        - Discuss the price trends, the support and resistance levels, and the status of MACD and RSI.
        - Figure out the potential price patterns in the charts. 
        - Include the price predictions of where the trending goes
        - Make a plan if there are trading opportunities
        - Advise the entry point of buy or short and the prices for stop-loss and take profit 
        - For the hook, avoiding repetition or similarity to the existing content such as: {hooks}

        % RESPONSE TEMPLATE:

        - Here is the response structure: 
            Title_eng: Title it
            Hook_eng: Captivate with a one-liner.
            Analysis_eng: Explain the detail of charts.
            Patterns_eng: figure the price patterns.
            Plan_eng: Trading plan.
            Strategy_eng: buy or short entry point and the prices for stop-loss and take profit 
            Summary_eng: Summarize the trending.
            Image_eng: Provide the image prompt according to the emotion of analysis which we will send to DALL-E to generate.
            Title_cht: Title in 繁體中文.
            Hook_cht: Hook in 繁體中文.
            Analysis_cht: Analysis in 繁體中文.
            Patterns_cht: Patterns in 繁體中文.
            Plan_cht: Plan in 繁體中文.
            Strategy_cht: Strategy in 繁體中文.
            Summary_cht: Summary in 繁體中文.
            Image_cht: Image in 繁體中文.
    
    """  

    logger.info(f'[gpt] Generate summary paper with file: {paper_pdf_file}')
    # system prompt template to follow
    system_message_prompt = SystemMessagePromptTemplate.from_template(
        system_template, input_variables=["hooks"])

    # human template for input
    images = [encode_image(chart_path) for chart_path in chart_path_list]

    if len(images) == 0:
        logger.error(f'[gpt] No valid images provided for analysis')
        raise ValueError("No valid images provided")

    contents = []
    contents.append({ 
                        "type": "text", 
                        "text": "Analyze the charts"
    })    

    for img in images:
        contents.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img}"
                        },
        })    
    human_message_prompt = HumanMessage(content=contents)

    # chat prompt template construction
    chat_prompt = ChatPromptTemplate.from_messages(
        [system_message_prompt, human_message_prompt]
    )

    # get a completed chat
    final_prompt = chat_prompt.format_prompt(hooks=', '.join(hooks_content)).to_messages()

    logger.info(f'[gpt] send the prompt to LLM')
    try:
        # pass template through llm and extract content attribute
        first_response = llm(final_prompt).content
        logger.info(f'[gpt] got response:{first_response}')
        first_draft = extract_response(first_response, report_key_list)
        logger.info(f'[gpt] parsed response:{first_draft}')
        report = AnalysisReport.from_dict(first_draft)    


    except Exception as e:
        logger.error(f'[gpt] error to LLM: {e}')
        return None

    return report

def remove_markdown_code_blocks(markdown_text):
    # This regex matches code blocks in Markdown (``` followed by code and then ending with ```)
    code_block_regex = re.compile(r'```[a-zA-Z0-9]*\n(.*?)```', re.DOTALL)
    
    # Find all matches
    matches = code_block_regex.findall(markdown_text)
    
    # Join all code blocks into a single string, separated by newlines
    code_only = '\n'.join(matches)
    
    return code_only


# def analyze_chart(chart_path_list, cht=True):
#     warnings.warn("Old procedural", DeprecationWarning)
#     images = [encode_image(chart_path) for chart_path in chart_path_list]

#     contents = []
#     single_chart = "Analyze the trading trend. Discuss the price trending, the supported and resisted level and the status of MACD and check any chart pattern for the trend. In the anaylsis, give the best entry point and the price to stop-loss and take profit."
#     # multi_chart = "Analyze these charts of trading trends in different time zones. Discuss the price trends, the support and resistance levels, and the status of MACD and check any chart pattern for the trend. Based on the analysis, give the best strategy to conclude it's buy or short entry point, and give the advices of the prices for stop-loss and take profit"
#     multi_chart = "Analyze these charts of trading trends in different time zones. Discuss the price trends, the support and resistance levels, and the status of MACD and figure out the potential price patterns in the charts. Based on the analysis, conclude it's buy or short entry point and give the prices for stop-loss and take profit if there has opportunities for trading."

#     contents.append({ 
#                         "type": "text", 
#                         "text": single_chart if len(chart_path_list) == 1 else multi_chart
#     })    

#     for img in images:
#         contents.append({
#                             "type": "image_url",
#                             "image_url": {
#                                 "url": f"data:image/jpeg;base64,{img}"
#                         },
#         })    
       
#     history = [
#         {
#             "role": "user",
#             "content": contents,
#         }
#     ]

#     response = client.chat.completions.create(
#         model="gpt-4o",
#         messages=history
#     )

#     eng_result = response.choices[0].message.content
#     cht_result = None
#     if cht:
#         history.append(response.choices[0].message)
#         history.append({"role": "user", "content": '上述分析請直接中文解釋'})
#         response = client.chat.completions.create(
#             model="gpt-4o",
#             messages=history
#         )
#         cht_result = response.choices[0].message.content

#     print('finish chat gpt analysis')
#     return eng_result, cht_result