import streamlit as st
import json, os, shutil, openai, csv
from pathlib import Path
from tqdm import tqdm
from dotenv import load_dotenv
from langchain.evaluation.qa import QAGenerateChain
from langchain.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI, AzureChatOpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter, CharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.document_loaders import (
    PyMuPDFLoader,
)
from langchain.retrievers import (
    SVMRetriever,
    AzureCognitiveSearchRetriever,
    TFIDFRetriever,
)

work_path = os.path.abspath('.')


def setup_env():
    # Load OpenAI key
    if os.path.exists("key.txt"):
        shutil.copyfile("key.txt", ".env")
        load_dotenv()
    else:
        print("key.txt with OpenAI API is required")

    # Load config values
    if os.path.exists(os.path.join(r'config.json')):
        with open(r'config.json') as config_file:
            config_details = json.load(config_file)

        # Setting up the embedding model
        embedding_model_name = config_details['EMBEDDING_MODEL']
        openai.api_type = "azure"
        openai.api_base = config_details['OPENAI_API_BASE']
        openai.api_version = config_details['OPENAI_API_VERSION']
        openai.api_key = os.getenv("OPENAI_API_KEY")
    else:
        print("config.json with Azure OpenAI config is required")


def set_reload_setting_flag():
    # st.write("New document need upload")
    st.session_state["evalreloadflag"] = True


def define_llm(model: str):
    if "gpt-35-turbo" in model:
        llm = AzureChatOpenAI(deployment_name=model,
                              openai_api_key=openai.api_key,
                              openai_api_base=openai.api_base,
                              openai_api_type=openai.api_type,
                              openai_api_version=openai.api_version,
                              max_tokens=1024,
                              temperature=0.2,
                              # model_kwargs={'engine': self.config_details['CHATGPT_MODEL']},
                              )
    elif "" in model:
        pass
    return llm


def define_retriver(retriver: str):
    if retriver == "Similarity Search":
        pass
    elif retriver == "Azure Cognitive Search":
        pass
    elif retriver == "SVM":
        pass
    return retriver


def define_splitter(splitter: str, chunk_size, chunk_overlap):
    if splitter == "RecursiveCharacterTextSplitter":
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    elif splitter == "CharacterTextSplitter":
        text_splitter = CharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return text_splitter


def define_embedding(embedding_method: str):
    if embedding_method == "OpenAI":
        embeddings = OpenAIEmbeddings(deployment="text-embedding-ada-002", chunk_size=1)
    elif embedding_method == "Azure Cognitive Search":
        pass
    return embeddings


def load_single_document(file_path):
    loader = PyMuPDFLoader(file_path)
    return loader.load()  # [0]


def main():
    # Initial
    setup_env()
    if "evalreloadflag" not in st.session_state:
        st.session_state["evalreloadflag"] = True

    # Setup Side Bar
    with st.sidebar:
        # 1. Model
        aa_llm_model = st.radio(label="`LLM Model`",
                                options=["gpt-35-turbo", "gpt-35-turbo-16k"],
                                index=0,
                                on_change=set_reload_setting_flag)
        # 2. Split
        aa_eval_q = st.slider(label="`Number of eval questions`",
                              min_value=1,
                              max_value=10,
                              value=5,
                              on_change=set_reload_setting_flag)
        aa_chunk_size = st.slider(label="`Choose chunk size for splitting`",
                                  min_value=500,
                                  max_value=2000,
                                  value=1000,
                                  on_change=set_reload_setting_flag)
        aa_overlap_size = st.slider(label="`Choose overlap for splitting`",
                                    min_value=0,
                                    max_value=100,
                                    value=200,
                                    on_change=set_reload_setting_flag)
        aa_split_methods = st.radio(label="`Split method`",
                                    options=["RecursiveTextSplitter", "CharacterTextSplitter"],
                                    index=0,
                                    on_change=set_reload_setting_flag)

        # 3. Retriver
        aa_retriver = st.radio(label="`Choose retriever`",
                               options=["Azure Cognitive Search", "Similarity Search", "SVM", "TFIDF"],
                               index=0,
                               on_change=set_reload_setting_flag)
        aa_chunk_num = st.select_slider("`Choose # chunks to retrieve`",
                                        options=[3, 4, 5, 6, 7, 8],
                                        on_change=set_reload_setting_flag)

        # 4. Embedding
        aa_embedding_method = st.radio(label="`Choose embeddings`",
                                       options=["Azure Cognitive Search", "OpenAI"],
                                       index=0,
                                       on_change=set_reload_setting_flag)

    if st.session_state["evalreloadflag"] == True:
        LlmModel = define_llm(aa_llm_model)
        EmbeddingModel = define_embedding(aa_embedding_method)
        TextSplitter = define_splitter(aa_split_methods, aa_chunk_size, aa_overlap_size)
        st.session_state["evalreloadflag"] = False

    # Main
    st.header("`Demo auto-evaluator`")
    file_paths = st.file_uploader("1.Upload document files to generate QAs",
                                  type=["pdf"],
                                  accept_multiple_files=False)

    if st.button("Upload"):
        if file_paths is not None or len(file_paths) > 0:
            # save file
            with st.spinner('Reading file'):
                uploaded_paths = []
                for file_path in file_paths:
                    uploaded_paths.append(os.path.join(work_path + "/tempDir/output", file_path.name))
                    uploaded_path = uploaded_paths[-1]
                    with open(uploaded_path, mode="wb") as f:
                        f.write(file_path.getbuffer())

            # process file
            with st.spinner('Create vector DB'):
                # load documents
                documents = []
                with tqdm(total=len(uploaded_path), desc='Loading new documents', ncols=80) as pbar:
                    for uploaded_path in uploaded_paths:
                        documents = documents + load_single_document(uploaded_path)
                        pbar.update()

                # split documents
                for i in range(len(uploaded_paths)):
                    uploaded_path = uploaded_paths[i]
                    texts = TextSplitter.split_documents(documents)

                    # search & retriver
                    # FAISS: save documents as index, and then load them(not use the save function)
                    # Others do not support save for now
                    single_index_name = Path(uploaded_path).stem + ".index"
                    if Path(single_index_name).is_file() == False:
                        if aa_retriver == "Similarity Search":
                            tmpdocsearch = FAISS.from_documents(texts, EmbeddingModel)
                            tmpdocsearch.save_local("./index/", Path(uploaded_path).stem)
                        elif aa_retriver == "SVM":
                            tmpdocsearch = SVMRetriever.from_documents(texts, EmbeddingModel)
                        elif aa_retriver == "TFIDF":
                            tmpdocsearch = TFIDFRetriever.from_documents(texts)
                        elif aa_retriver == "Azure Cognitive Search":
                            tmpdocsearch = AzureCognitiveSearchRetriever(content_key="content", top_k=4)

                        if i == 0:
                            docsearch = tmpdocsearch
                        else:
                            # not used
                            docsearch.merge_from(tmpdocsearch)
                    else:
                        # not used
                        if i == 0:
                            docsearch = FAISS.load_local("./index/", EmbeddingModel, Path(uploaded_path).stem)
                        else:
                            # not used
                            docsearch.merge_from(FAISS.load_local("./index/", EmbeddingModel, Path(uploaded_path).stem))

                # make chain
                qa_chain = RetrievalQA.from_chain_type(LlmModel, retriever=docsearch)


                if len(uploaded_paths) > 0:
                    st.write(f"✅ " + ", ".join(uploaded_paths) + " uploaed")


if __name__ == "__main__":
    main()
