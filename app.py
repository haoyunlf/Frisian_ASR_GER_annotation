import streamlit as st
import json
import random
import os
import glob
import re
import time
import gspread
from google.oauth2.service_account import Credentials


# ===== Google Sheets 上传 =====
def upload_to_sheets(answers, user_id, total_elapsed):
    """把所有已完成答案批量写入 Google Sheet（先清旧数据再重写）。"""
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        sheet_id = st.secrets["sheets"]["sheet_id"]
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(sheet_id)

        # 用 user_id 作为 worksheet 名，不同标注者分不同 sheet
        ws_title = user_id[:50]  # worksheet 名最长100字符，截保险
        try:
            ws = sh.worksheet(ws_title)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=ws_title, rows=500, cols=20)

        # 表头
        headers = [
            "uid", "reference", "baseline_1best", "gpt_output",
            "selected_text", "copied_from_nbest", "category",
            "behavior_type", "annotation_timestamp", "elapsed_seconds_at_submit",
            "total_elapsed_seconds", "annotator",
        ]
        rows = [headers]
        for ans in answers:
            rows.append([
                ans.get("uid", ""),
                ans.get("reference", ""),
                ans.get("baseline_1best", ""),
                ans.get("gpt_output", ""),
                ans.get("selected_text", ""),
                str(ans.get("copied_from_nbest", "")),
                ans.get("category", ""),
                ans.get("behavior_type", ""),
                ans.get("annotation_timestamp", ""),
                str(ans.get("elapsed_seconds_at_submit", "")),
                str(round(total_elapsed, 1)),
                user_id,
            ])
        ws.update(rows, value_input_option="RAW")
        return True, None
    except Exception as e:
        return False, str(e)


st.set_page_config(page_title="Frisian ASR Human Annotation", layout="wide")

# ===== 加载数据 =====
@st.cache_data
def load_data():
    data = json.load(open("sampled_sentences_flat.json"))
    samples = []
    for uid, item in data.items():
        samples.append({
            "uid": uid,
            "reference": item["reference"],
            "baseline_1best": item["baseline_1best"],
            "gpt_output": item["gpt_output"],
            "nbest": item["nbest"],
            "category": item["category"],
            "behavior_type": item["behavior_type"],
            "behavior_description": item["behavior_description"],
            "original_wer": item["original_wer"],
            "gpt_wer": item["gpt_wer"]
        })
    return samples

samples = load_data()

st.title("Frisian ASR Error Annotation")

# 添加任务描述
st.markdown("""
On each page, you will be presented with a list of ASR (automatic speech recognition) transcriptions for the same utterance. These are multiple alternative transcription candidates ordered by confidence, with the most likely transcription appearing first.

**Your task is to write a single corrected transcription.**

When reviewing the hypotheses:

- Infer the most likely spoken Frisian from the candidate hypotheses and write your answer in the text box.
- If you think a candidate is completely correct, you can click the copy button to copy it into the text box.
- If none of the candidates are completely correct, you may rewrite them to produce the most possible transcription.
- If there are any spelling or grammatical errors, correct them so the sentence follows normal Frisian usage.
- If dialectal forms appear, do not normalize them into standard Frisian; instead, infer and preserve what the speaker most likely said.
- Ignore capitalization and punctuation differences — all texts have been normalized.
""")

# 自动生成用户ID
if 'user_id' not in st.session_state:
    # 自动生成一个唯一的annotator编号（用户不可见）
    import time
    import random
    
    # 基于时间戳和随机数生成唯一ID
    timestamp = int(time.time())
    random_num = random.randint(100, 999)
    auto_id = f"Annotator_{timestamp}_{random_num}"
    
    st.session_state.user_id = auto_id

user_id = st.session_state.user_id

# 确保annotation目录存在（用于下载功能）
os.makedirs("annotation", exist_ok=True)

# ===== 配置参数 =====
# 管理员可在此修改标注任务的配置
USE_ALL_DATA = False             # 默认使用随机抽样而不是全部数据
ANNOTATION_SAMPLE_SIZE = 20      # 默认样本数量
ALLOW_CUSTOM_SIZE = True         # 是否允许用户自定义样本数量

# ===== 创建新的标注任务 =====
# 网络部署时每次都从头开始
if 'annotation_state' not in st.session_state:
    # 创建新的标注任务
    
    # 让用户选择任务类型
    st.write("**Choose annotation task type:**")
    task_option = st.radio(
        label="",  # 空标签
        options=["Quick test (20 random samples)", "Full dataset (all samples)", "Custom size"],
        index=0,
        key="task_type_radio"
)
    
    if task_option == "Quick test (20 random samples)":
        sample_size = 20
        available_samples = min(sample_size, len(samples))
        st.info(f"This task will include **{available_samples}** randomly selected samples for annotation.")
        task_description = f"Quick test - {available_samples} samples"
        use_all = False
        
    elif task_option == "Full dataset (all samples)":
        available_samples = len(samples)
        st.info(f"This task will include **all {available_samples}** samples from the dataset for annotation.")
        task_description = "Complete dataset annotation"
        use_all = True
        
    else:  # Custom size
        sample_size = st.number_input(
            "Enter number of samples:", 
            min_value=1, 
            max_value=len(samples), 
            value=50
        )
        available_samples = min(sample_size, len(samples))
        st.info(f"This task will include **{available_samples}** randomly selected samples for annotation.")
        task_description = f"Custom task - {available_samples} samples"
        use_all = False
    
    if st.button("🚀 Start New Annotation Task", type="primary"):
        if use_all:
            # 使用全部数据，但先shuffle
            selected_samples = samples.copy()
            random.shuffle(selected_samples)  # 确保数据被shuffle
        else:
            # 随机抽样（random.sample自动shuffle）
            selected_samples = random.sample(samples, available_samples)
            
        state = {
            "subset": selected_samples,
            "idx": 0,
            "answers": [],
            "task_type": task_description,
            "total_available": len(samples)
        }

        # 保存到session state而不是文件
        st.session_state.annotation_state = state
        # 初始化计时器
        st.session_state.task_start_wall = time.time()
        st.session_state.elapsed_before_pause = 0.0
        st.session_state.last_resume_time = time.time()
        st.session_state.is_paused = False
        st.success("✅ New annotation task created!")
        st.rerun()
    else:
        st.stop()

# 从session state获取state
if 'annotation_state' not in st.session_state:
    st.stop()

state = st.session_state.annotation_state

# ===== 检查是否完成 =====
if state["idx"] >= len(state["subset"]):
    st.success("🎉 Annotation task completed!")
    st.write("Thank you for your annotations!")
    
    # 显示统计信息
    st.subheader("📊 Your Annotation Statistics:")
    total_ans = len(state["answers"])
    copied_count = sum(1 for ans in state["answers"] if ans.get("copied_from_nbest") is not None)
    modified_count = total_ans - copied_count

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Annotations", total_ans)
        st.metric("Copied from N-best", copied_count)
    with col2:
        st.metric("Manually Written", modified_count)
        st.metric("Manual Rate", f"{modified_count/total_ans*100:.1f}%" if total_ans > 0 else "0%")
    
    if st.button("Download Results"):
        total_samples = len(state["subset"])
        completed_samples = len(state["answers"])
        # 计算总用时
        is_paused = st.session_state.get('is_paused', False)
        elapsed_before_pause = st.session_state.get('elapsed_before_pause', 0.0)
        last_resume_time = st.session_state.get('last_resume_time', time.time())
        total_elapsed = elapsed_before_pause if is_paused else elapsed_before_pause + (time.time() - last_resume_time)
        save_data = dict(state)
        save_data["total_elapsed_seconds"] = round(total_elapsed, 1)
        # 上传到 Google Sheets
        ok, err = upload_to_sheets(state["answers"], user_id, total_elapsed)
        if ok:
            st.success("✅ Results uploaded to Google Sheets!")
        else:
            st.warning(f"⚠️ Upload failed: {err}")
        st.download_button(
            label="📥 Download Annotation Results",
            data=json.dumps(save_data, ensure_ascii=False, indent=2),
            file_name=f"{user_id}_{completed_samples}of{total_samples}_annotations.json",
            mime="application/json"
        )
    
    if st.button("🔄 Start New Task"):
        # 清除session state重新开始
        for k in ['annotation_state', 'task_start_wall', 'elapsed_before_pause',
                  'last_resume_time', 'is_paused']:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()
    
    st.stop()

# ===== 显示进度 =====
progress = state["idx"] / len(state["subset"])
st.progress(progress)
st.write(f"**Sample {state['idx'] + 1} / {len(state['subset'])}** ({progress*100:.1f}% completed)")

# ===== 当前样本 =====
item = state["subset"][state["idx"]]
idx = state["idx"]

# N-best 候选（最多5条）
nbest = item["nbest"][:5] if len(item["nbest"]) >= 5 else item["nbest"]

# 用于文本框的 session state key
correction_key = f"correction_text_{idx}"

st.subheader("📋 N-best Candidates")
st.write("Review the candidates below. Click **Copy** to load a candidate into the text box, then edit as needed.")

for i, text in enumerate(nbest):
    col_text, col_btn = st.columns([9, 1])
    with col_text:
        st.markdown(f"**{i+1}.** {text}")
    with col_btn:
        if st.button("📋", key=f"copy_{idx}_{i}", help=f"Copy candidate {i+1} into the text box"):
            st.session_state[correction_key] = text
            st.rerun()

st.divider()

# ===== 文本框 =====
st.subheader("✏️ Your Correction")
st.write("Write or edit the corrected transcription here:")

correction = st.text_area(
    "",
    placeholder="Type your correction here, or click a Copy button above to load a candidate...",
    height=100,
    key=correction_key,
)

# 判断是否直接复制自某个 nbest（完全相同）
copied_from_nbest = None
if correction.strip():
    for i, text in enumerate(nbest):
        if correction.strip() == text.strip():
            copied_from_nbest = i + 1  # 1-based
            break

# ===== 验证和提交 =====
st.divider()

# 显示当前状态摘要
if correction.strip():
    if copied_from_nbest:
        st.info(f"✅ Using candidate {copied_from_nbest} (unchanged): {correction.strip()}")
    else:
        st.success(f"📝 Your correction: {correction.strip()}")
else:
    st.warning("⚠️ Please enter a corrected transcription above before submitting.")

# ===== 导航按钮 =====
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    if state["idx"] > 0:
        if st.button("⬅️ Previous", use_container_width=True):
            state["idx"] -= 1
            if state["answers"] and len(state["answers"]) > state["idx"]:
                state["answers"] = state["answers"][:state["idx"]]
            st.session_state.annotation_state = state
            st.rerun()
    else:
        st.button("⬅️ Previous", disabled=True, use_container_width=True, help="No previous sample")

with col2:
    st.write("")

with col3:
    can_submit = bool(correction and correction.strip())
    submit_label = "➡️ Submit & Next" if can_submit else "⚠️ Enter Correction First"

    if st.button(submit_label, type="primary", disabled=not can_submit, use_container_width=True):
        selected_text = correction.strip()

        # 计算当前已用时间
        if not st.session_state.get('is_paused', False):
            cur_elapsed = st.session_state.get('elapsed_before_pause', 0.0) + (
                time.time() - st.session_state.get('last_resume_time', time.time())
            )
        else:
            cur_elapsed = st.session_state.get('elapsed_before_pause', 0.0)

        answer = {
            "uid": item["uid"],
            "reference": item["reference"],
            "baseline_1best": item["baseline_1best"],
            "gpt_output": item["gpt_output"],
            "nbest": nbest,
            "category": item["category"],
            "behavior_type": item["behavior_type"],
            "selected_text": selected_text,
            "copied_from_nbest": copied_from_nbest,   # 1-based index if exact copy, else None
            "annotation_timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "elapsed_seconds_at_submit": round(cur_elapsed, 1),
        }

        state["answers"].append(answer)
        state["idx"] += 1
        st.session_state.annotation_state = state

        # 清理当前样本的 session state
        for key in [correction_key]:
            if key in st.session_state:
                del st.session_state[key]

        st.success(f"✅ Saved: {selected_text}")
        st.rerun()

# ===== 侧边栏信息 =====
with st.sidebar:
    # ---- 计时器 ----
    st.subheader("⏱️ Timer")
    is_paused = st.session_state.get('is_paused', False)
    elapsed_before_pause = st.session_state.get('elapsed_before_pause', 0.0)
    last_resume_time = st.session_state.get('last_resume_time', time.time())

    if is_paused:
        current_elapsed = elapsed_before_pause
    else:
        current_elapsed = elapsed_before_pause + (time.time() - last_resume_time)

    mins, secs = divmod(int(current_elapsed), 60)
    hours, mins = divmod(mins, 60)
    st.metric("Elapsed", f"{hours:02d}:{mins:02d}:{secs:02d}")

    if is_paused:
        if st.button("▶️ Resume", use_container_width=True):
            st.session_state.last_resume_time = time.time()
            st.session_state.is_paused = False
            st.rerun()
        st.warning("Paused")
    else:
        if st.button("⏸️ Pause", use_container_width=True):
            st.session_state.elapsed_before_pause = elapsed_before_pause + (
                time.time() - last_resume_time
            )
            st.session_state.is_paused = True
            st.rerun()

    st.divider()

    # ---- 统计 ----
    if state["answers"]:
        total_ans = len(state["answers"])
        copied_count = sum(1 for ans in state["answers"] if ans.get("copied_from_nbest") is not None)
        modified_count = total_ans - copied_count

        st.subheader("📋 Annotation Stats")
        st.metric("Copied from N-best", copied_count)
        st.metric("Manually Written", modified_count)
        if total_ans > 0:
            st.metric("Manual Rate", f"{modified_count/total_ans*100:.1f}%")

    st.divider()
    st.subheader("💾 Actions")

    # 中途保存进度
    if state["answers"]:
        total_samples = len(state["subset"])
        completed_samples = len(state["answers"])
        save_data = dict(state)
        save_data["total_elapsed_seconds"] = round(current_elapsed, 1)
        if st.button(f"💾 Save Progress ({completed_samples}/{total_samples})", use_container_width=True):
            ok, err = upload_to_sheets(state["answers"], user_id, current_elapsed)
            if ok:
                st.success("✅ Uploaded to Google Sheets!")
            else:
                st.warning(f"⚠️ Upload failed: {err}")
        st.download_button(
            label=f"📥 Download ({completed_samples}/{total_samples})",
            data=json.dumps(save_data, ensure_ascii=False, indent=2),
            file_name=f"{user_id}_{completed_samples}of{total_samples}_partial.json",
            mime="application/json",
            use_container_width=True,
        )

    if st.button("🔄 Reset Progress", use_container_width=True):
        # 清除session state重新开始
        for k in ['annotation_state', 'task_start_wall', 'elapsed_before_pause',
                  'last_resume_time', 'is_paused']:
            if k in st.session_state:
                del st.session_state[k]
        st.success("Progress reset!")
        st.rerun()