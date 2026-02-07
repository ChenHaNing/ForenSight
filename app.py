import json
import time
import uuid
from pathlib import Path
import streamlit as st

from src.config import load_config
from src.llm_client import LLMClient
from src.orchestrator import run_pipeline

PROJECT_DIR = Path(__file__).resolve().parent
SAMPLE_PAPER = PROJECT_DIR / "AI大模型驱动的智能博弈财务舞弊识别系统构建.pdf"
SAMPLE_10K = PROJECT_DIR / "aapl_10-K-2025-As-Filed.pdf"


st.set_page_config(page_title="FFMAS 原型", layout="wide")

st.title("多智能体财务舞弊识别系统原型")

with st.sidebar:
    st.header("运行配置")
    config = load_config()
    provider = st.text_input("LLM Provider", value=config.llm_provider)
    model = st.text_input("LLM Model", value=config.llm_model_name)
    api_key = st.text_input("LLM API Key", value=config.llm_api_key, type="password")
    base_url = st.text_input("LLM Base URL", value=config.llm_base_url)
    enable_defense = st.checkbox("启用辩护智能体", value=True)
    st.divider()
    use_samples = st.checkbox("使用样本文档", value=False)

selected_files = []
if use_samples:
    if SAMPLE_PAPER.exists():
        selected_files.append(str(SAMPLE_PAPER))
    if SAMPLE_10K.exists():
        selected_files.append(str(SAMPLE_10K))
else:
    uploaded = st.file_uploader("上传PDF", type=["pdf"], accept_multiple_files=True)
    if uploaded:
        upload_dir = PROJECT_DIR / "uploads"
        upload_dir.mkdir(exist_ok=True)
        for f in uploaded:
            path = upload_dir / f.name
            path.write_bytes(f.read())
            selected_files.append(str(path))

run_btn = st.button("运行分析")

if run_btn:
    if not selected_files:
        st.error("请至少选择或上传一个PDF。")
    else:
        llm = LLMClient(provider=provider, model=model, api_key=api_key, base_url=base_url)
        output_dir = PROJECT_DIR / "outputs" / f"run_{time.time_ns()}_{uuid.uuid4().hex[:8]}"
        with st.spinner("正在分析，请稍候..."):
            final_report = run_pipeline(
                input_texts=None,
                pdf_paths=selected_files,
                llm=llm,
                output_dir=output_dir,
                enable_defense=enable_defense,
            )

        st.success("分析完成")

        st.subheader("综合结论")
        st.write(final_report)

        st.subheader("单项报告")
        agent_dir = output_dir / "agent_reports"
        for report_file in sorted(agent_dir.glob("*.json")):
            st.markdown(f"**{report_file.stem}**")
            data = json.loads(report_file.read_text(encoding="utf-8"))
            st.json(data)

        st.subheader("下载")
        st.download_button(
            "下载最终报告 JSON",
            data=(output_dir / "final_report.json").read_text(encoding="utf-8"),
            file_name="final_report.json",
        )
        st.download_button(
            "下载工作底稿 JSON",
            data=(output_dir / "workpaper.json").read_text(encoding="utf-8"),
            file_name="workpaper.json",
        )
