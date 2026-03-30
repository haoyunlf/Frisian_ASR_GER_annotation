import streamlit as st
import json
import random
import os
import glob
import re

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
You will help evaluate and correct Frisian automatic speech recognition (ASR) outputs. For each sample, you'll be shown:
- Multiple candidate transcriptions ranked by the ASR system's confidence (from highest to lowest probability)
- Your task is to **select the best transcription** or provide a manual correction if none are satisfactory
- Ignore capitalization and punctuation differences - all texts have been normalized
- When making manual corrections, please indicate the types of errors you found in the candidates
""")

st.write(f"Total samples available: {len(samples)}")

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
        label=None,  # 空标签
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
    manual_corrections = sum(1 for ans in state["answers"] if ans["choice"] == "manual_correction")
    nbest_selections = len(state["answers"]) - manual_corrections
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Annotations", len(state["answers"]))
        st.metric("N-best Selections", nbest_selections)
    with col2:
        st.metric("Manual Corrections", manual_corrections)
        st.metric("Manual Rate", f"{manual_corrections/len(state['answers'])*100:.1f}%")
    
    if st.button("Download Results"):
        total_samples = len(state["subset"])
        completed_samples = len(state["answers"])
        st.download_button(
            label="📥 Download Annotation Results",
            data=json.dumps(state, ensure_ascii=False, indent=2),
            file_name=f"{user_id}_{completed_samples}of{total_samples}_annotations.json",
            mime="application/json"
        )
    
    if st.button("🔄 Start New Task"):
        # 清除session state重新开始
        if 'annotation_state' in st.session_state:
            del st.session_state.annotation_state
        st.rerun()
    
    st.stop()

# ===== 显示进度 =====
progress = state["idx"] / len(state["subset"])
st.progress(progress)
st.write(f"**Sample {state['idx'] + 1} / {len(state['subset'])}** ({progress*100:.1f}% completed)")

# ===== 当前样本 =====
item = state["subset"][state["idx"]]

st.subheader("🎯 Select the Best Transcription")
st.write("Choose the best option from the N-best list below:")

# N-best选项（按顺序显示，不显示额外信息）
nbest = item["nbest"][:5] if len(item["nbest"]) >= 5 else item["nbest"]

# 简单的选项列表
options = []
for i, text in enumerate(nbest):
    options.append(f"{i+1}: {text}")

options.append("None of the above")

choice = st.radio("Select the best transcription:", options, key=f"transcription_choice_{state['idx']}")

# ===== 自己改写 =====
correction = ""
error_types = []

if choice and choice == "None of the above":
    st.markdown("**Enter your correction:**")
    correction = st.text_area(
        "", 
        placeholder="Type your correction here...", 
        height=100,
        key=f"manual_correction_{state['idx']}",
        help="",
    )
    
    # 添加错误类型选择
    if correction.strip():  # 只有当用户输入了内容才显示错误类型选择
        st.markdown("**What types of errors did you find? (Select all that apply)**")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            spelling_error = st.checkbox(
                "Spelling", 
                key=f"error_spelling_{state['idx']}"
            )
            morphological_error = st.checkbox(
                "Morphological", 
                key=f"error_morphological_{state['idx']}"
            )
        
        with col2:
            syntactic_error = st.checkbox(
                "Syntactic", 
                key=f"error_syntactic_{state['idx']}"
            )
            pragmatic_error = st.checkbox(
                "Pragmatic", 
                key=f"error_pragmatic_{state['idx']}"
            )
        
        with col3:
            others_error = st.checkbox(
                "Others", 
                key=f"error_others_{state['idx']}"
            )
        
        # 收集选择的错误类型
        if spelling_error:
            error_types.append("spelling")
        if morphological_error:
            error_types.append("morphological")
        if syntactic_error:
            error_types.append("syntactic")
        if pragmatic_error:
            error_types.append("pragmatic")
        if others_error:
            error_types.append("others")

# ===== 验证和提交 =====
st.divider()

# 显示当前选择摘要
if choice:
    if choice == "None of the above":
        if correction.strip():
            st.success(f"📝 **Manual correction:** {correction.strip()}")
        else:
            st.warning("⚠️ Please enter your manual correction above")
    else:
        selected_num = choice.split(":")[0]
        selected_text = choice.split(":", 1)[1].strip()
        st.info(f"✅ **Selected option {selected_num}:** {selected_text}")

# ===== 导航按钮 =====
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    # 上一个按钮
    if state["idx"] > 0:
        if st.button("⬅️ Previous", use_container_width=True):
            state["idx"] -= 1
            
            # 如果有答案，移除最后一个答案
            if state["answers"] and len(state["answers"]) > state["idx"]:
                state["answers"] = state["answers"][:state["idx"]]
            
            # 更新session state
            st.session_state.annotation_state = state
            
            st.success("⬅️ Moved to previous sample")
            st.rerun()
    else:
        st.button("⬅️ Previous", disabled=True, use_container_width=True, help="No previous sample")

with col2:
    # 空白中间列
    st.write("")

with col3:
    # 提交按钮 - 检查是否可以提交
    can_submit = False
    submit_label = "➡️ Submit & Next"
    
    if choice:
        if choice == "None of the above":
            if correction and correction.strip():
                can_submit = True
            else:
                submit_label = "⚠️ Enter Correction First"
        else:
            can_submit = True
    else:
        submit_label = "⚠️ Select Option First"
    
    # 提交按钮
    if st.button(submit_label, type="primary", disabled=not can_submit, use_container_width=True):
        
        # 获取手动输入的文本（如果有）
        manual_text = st.session_state.get(f"manual_correction_{state['idx']}", "")

        # 解析选择
        if choice == "None of the above":
            selected_option = "manual_correction"
            selected_text = manual_text.strip() if manual_text else correction.strip()
        else:
            # 提取选择的编号 - 修复解析逻辑
            try:
                # choice格式: "1: 文本内容" 或 "2: 文本内容"
                option_num = int(choice.split(":")[0]) - 1  # 简化解析
                selected_option = f"nbest_{option_num + 1}"
                selected_text = nbest[option_num]
                
            except (ValueError, IndexError) as e:
                st.error(f"❌ Error parsing choice: {e}")
                st.stop()

        # 保存答案
        answer = {
            "uid": item["uid"],
            "reference": item["reference"],
            "baseline_1best": item["baseline_1best"],
            "gpt_output": item["gpt_output"],
            "nbest": nbest,
            "category": item["category"],
            "behavior_type": item["behavior_type"],
            "choice": selected_option,
            "selected_text": selected_text,
            "is_manual": choice == "None of the above",
            "annotation_timestamp": st.session_state.get('current_time', ''),
            "error_types": error_types if choice == "None of the above" else []  # 只在手动纠正时包含错误类型
        }
        
        state["answers"].append(answer)
        state["idx"] += 1

        # 更新session state
        st.session_state.annotation_state = state

        # 清理当前样本的session state
        current_choice_key = f"transcription_choice_{state['idx']-1}"
        current_manual_key = f"manual_correction_{state['idx']-1}"
        
        if current_choice_key in st.session_state:
            del st.session_state[current_choice_key]
        if current_manual_key in st.session_state:
            del st.session_state[current_manual_key]

        # 显示确认信息
        st.success(f"✅ Saved: {selected_text}")
        st.rerun()

# ===== 侧边栏信息 =====
with st.sidebar:
    if state["answers"]:
        manual_count = sum(1 for ans in state["answers"] if ans["is_manual"])
        nbest_count = len(state["answers"]) - manual_count
        
        st.subheader("📋 Annotation Stats")
        st.metric("N-best Selections", nbest_count)
        st.metric("Manual Corrections", manual_count)
        if len(state["answers"]) > 0:
            st.metric("Manual Rate", f"{manual_count/len(state['answers'])*100:.1f}%")
    
    st.subheader("💾 Actions")
    
    if st.button("🔄 Reset Progress"):
        # 清除session state重新开始
        if 'annotation_state' in st.session_state:
            del st.session_state.annotation_state
        st.success("Progress reset!")
        st.rerun()