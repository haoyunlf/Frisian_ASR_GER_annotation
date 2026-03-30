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

# ===== 自动生成用户ID =====
def get_next_user_id():
    """自动生成下一个用户编号"""
    import glob
    import re
    
    # 查找现有的标注文件
    existing_files = glob.glob("Frisian_A*_annotations.json")
    
    if not existing_files:
        return "Frisian_A01"
    
    # 提取现有编号
    numbers = []
    for file in existing_files:
        match = re.search(r'Frisian_A(\d+)_annotations\.json', file)
        if match:
            numbers.append(int(match.group(1)))
    
    if numbers:
        next_num = max(numbers) + 1
        return f"Frisian_A{next_num:02d}"
    else:
        return "Frisian_A01"

st.title("Frisian ASR Human Annotation")
st.write(f"Total samples available: {len(samples)}")

# 添加重要说明
st.write("**Note:** Please ignore differences in capitalization and punctuation in the sentences, as all texts have been normalized.")

# 自动生成或选择用户ID
if 'user_id' not in st.session_state:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        option = st.radio(
            "Choose user ID option:",
            ["Auto-generate ID", "Use existing ID", "Custom ID"]
        )
    
    with col2:
        if option == "Auto-generate ID":
            suggested_id = get_next_user_id()
            st.info(f"Next ID: {suggested_id}")
            
        elif option == "Use existing ID":
            existing_files = glob.glob("Frisian_A*_annotations.json")
            if existing_files:
                existing_ids = [os.path.basename(f).replace("_annotations.json", "") for f in existing_files]
                selected_id = st.selectbox("Select existing ID:", existing_ids)
            else:
                st.warning("No existing annotation files found")
                selected_id = None
                
        else:  # Custom ID
            custom_id = st.text_input("Enter custom ID:", placeholder="e.g., Frisian_B01")
    
    if st.button("Confirm User ID", type="primary"):
        if option == "Auto-generate ID":
            st.session_state.user_id = get_next_user_id()
        elif option == "Use existing ID" and 'selected_id' in locals() and selected_id:
            st.session_state.user_id = selected_id
        elif option == "Custom ID" and 'custom_id' in locals() and custom_id.strip():
            st.session_state.user_id = custom_id.strip()
        else:
            st.error("Please provide a valid user ID")
            st.stop()
        
        st.success(f"✅ User ID set to: {st.session_state.user_id}")
        st.rerun()
    else:
        st.info("👆 Please confirm your user ID to continue")
        st.stop()

user_id = st.session_state.user_id
st.write(f"**Current User:** {user_id}")

os.makedirs("annotation", exist_ok=True)
save_path = f"annotation/{user_id}_annotations.json"

# ===== 配置参数 =====
# 管理员可在此修改标注任务的配置
USE_ALL_DATA = False             # 默认使用随机抽样而不是全部数据
ANNOTATION_SAMPLE_SIZE = 20      # 默认样本数量
ALLOW_CUSTOM_SIZE = True         # 是否允许用户自定义样本数量

# ===== 读取进度 =====
if os.path.exists(save_path):
    state = json.load(open(save_path))
    # 确保状态数据完整性
    if "subset" not in state or "idx" not in state or "answers" not in state:
        st.warning("⚠️ Invalid save file, starting fresh")
        state = None
    else:
        st.success(f"🔄 Resumed existing annotation task with {len(state['subset'])} samples")
        st.write(f"📊 Progress: {state['idx']}/{len(state['subset'])} completed ({state['idx']/len(state['subset'])*100:.1f}%)")

if not os.path.exists(save_path) or state is None:
    # 创建新的标注任务
    st.subheader("🆕 Create New Annotation Task")
    
    # 让用户选择任务类型
    task_option = st.radio(
        "Choose annotation task type:",
        ["Quick test (20 random samples)", "Full dataset (all samples)", "Custom size"]
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

        # 保存初始状态
        with open(save_path, "w", encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        st.success("✅ New annotation task created!")
        st.rerun()
    else:
        st.stop()

if 'state' not in locals() or state is None:
    st.stop()

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
        st.download_button(
            label="📥 Download Annotation Results",
            data=json.dumps(state, ensure_ascii=False, indent=2),
            file_name=f"{user_id}_annotations.json",
            mime="application/json"
        )
    
    if st.button("🔄 Start New Task"):
        os.remove(save_path) if os.path.exists(save_path) else None
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
            
            # 保存状态
            with open(save_path, "w", encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            
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

        # 保存进度
        with open(save_path, "w", encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

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
    st.subheader("User Info")
    st.write(f"**User ID:** {user_id}")
    
    if state["answers"]:
        manual_count = sum(1 for ans in state["answers"] if ans["is_manual"])
        nbest_count = len(state["answers"]) - manual_count
        
        st.subheader("📋 Annotation Stats")
        st.metric("N-best Selections", nbest_count)
        st.metric("Manual Corrections", manual_count)
        if len(state["answers"]) > 0:
            st.metric("Manual Rate", f"{manual_count/len(state['answers'])*100:.1f}%")
    
    st.subheader("💾 Data")
    st.write(f"Save file: `{save_path}`")
    
    if st.button("🔄 Reset Progress"):
        if os.path.exists(save_path):
            os.remove(save_path)
            st.success("Progress reset!")
            st.rerun()