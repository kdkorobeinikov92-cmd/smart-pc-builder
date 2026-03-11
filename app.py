import streamlit as st
import pandas as pd
import re
import time
from openai import OpenAI
import plotly.express as px

# --- НАСТРОЙКИ СТРАНИЦЫ ---
st.set_page_config(page_title="Smart PC Builder v8.0", page_icon="✨", layout="wide")

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def extract_number(val, default=0):
    if pd.isna(val) or val == "" or val == 0: return default
    match = re.search(r'\d+', str(val))
    return int(match.group()) if match else default

@st.cache_data
def load_data():
    return pd.read_excel('Реальная_База_ПК.xlsx', sheet_name=None)

# --- ЗАГРУЗКА БАЗЫ ---
try:
    db = load_data()
    cpus = db.get('Процессоры (CPU)')
    mobos = db.get('Материнские платы (Motherboards)') or db.get('Материнские платы (Motherboards')
    gpus = db.get('Видеокарты (GPU)')
    coolers = db.get('Охлаждение (Coolers)')
    cases = db.get('Корпуса (Cases)')
    psus = db.get('Блоки питания (PSU)')
    ram = db.get('Оперативная память (RAM)')
    ssds = db.get('Накопители (SSD)')
    hdds = db.get('Жесткие диски (HDD)')

    # Заглушка для дополнительного диска
    none_hdd = pd.DataFrame([{"Название": "Нет дополнительного диска", "Цена": 0}])
    if hdds is None or hdds.empty:
        hdds = none_hdd
    else:
        hdds = pd.concat([none_hdd, hdds], ignore_index=True)

except Exception as e:
    st.error(f"Ошибка загрузки базы: {e}\nУбедитесь, что файл 'Реальная_База_ПК.xlsx' находится в папке.")
    st.stop()

if 'smart_generated' not in st.session_state:
    st.session_state.smart_generated = False

# --- ФОРМАТИРОВАНИЕ ЦЕН ---
def format_with_price(item_name, df):
    if item_name == "Нет дополнительного диска": return item_name
    try:
        price = df[df['Название'] == item_name].iloc[0]['Цена']
        return f"{item_name}  —  {price} ₽"
    except:
        return item_name

# --- УМНАЯ ФУНКЦИЯ ПОДБОРА ---
def generate_build(cpu_series, target_gpu=None):
    cpu_price = cpu_series['Цена']
    cpu_tdp = extract_number(cpu_series.get('TDP (Вт)'), 100) 
    cpu_socket = cpu_series['Сокет']
    
    if target_gpu is not None:
        best_gpu = target_gpu
    else:
        t_min, t_max = cpu_price * 1.2, cpu_price * 3.0
        valid_gpus = gpus[(gpus['Цена'] >= t_min) & (gpus['Цена'] <= t_max)]
        best_gpu = valid_gpus.sort_values(by='Цена', ascending=False).iloc[0] if not valid_gpus.empty else gpus.iloc[0]
    
    gpu_tdp = extract_number(best_gpu.get('TDP (Вт)'), 200)
    gpu_length = extract_number(best_gpu.get('Длина (мм)'), 300)
    
    valid_mobos = mobos[mobos['Сокет'] == cpu_socket].sort_values(by='Цена')
    best_mobo = valid_mobos.iloc[len(valid_mobos)//2] if len(valid_mobos) > 1 else valid_mobos.iloc[0]
    
    valid_ram = ram[ram['Тип'] == best_mobo['Тип ОЗУ']].sort_values(by='Цена')
    best_ram = valid_ram.iloc[-1] if not valid_ram.empty else ram.iloc[0]
    
    valid_coolers = coolers[coolers['Совместимые сокеты'].str.contains(cpu_socket, na=False, case=False)]
    valid_coolers = valid_coolers[valid_coolers['TDP кулера'].apply(lambda x: extract_number(x, 150)) >= cpu_tdp * 1.2]
    best_cooler = valid_coolers.sort_values(by='Цена').iloc[0] if not valid_coolers.empty else coolers.iloc[0]
    cooler_height = extract_number(best_cooler.get('Габарит (Высота/Длина)'), 160)
    
    sys_tdp = cpu_tdp + gpu_tdp + 150
    valid_psus = psus[psus['Мощность'].apply(lambda x: extract_number(x, 500)) >= sys_tdp].sort_values(by='Цена')
    best_psu = valid_psus.iloc[0] if not valid_psus.empty else psus.iloc[-1]
    
    valid_cases = cases[(cases['Макс. длина GPU'].apply(lambda x: extract_number(x, 350)) >= gpu_length) & 
                        (cases['Макс. высота кулера'].apply(lambda x: extract_number(x, 170)) >= cooler_height)]
    best_case = valid_cases.iloc[0] if not valid_cases.empty else cases.iloc[-1]
    
    best_ssd = ssds.iloc[1] if len(ssds) > 1 else ssds.iloc[0]
    best_hdd = hdds.iloc[0] 
    
    st.session_state.smart_cpu = cpu_series['Название']
    st.session_state.smart_mobo = best_mobo['Название']
    st.session_state.smart_gpu = best_gpu['Название']
    st.session_state.smart_ram = best_ram['Название']
    st.session_state.smart_cooler = best_cooler['Название']
    st.session_state.smart_psu = best_psu['Название']
    st.session_state.smart_case = best_case['Название']
    st.session_state.smart_ssd = best_ssd['Название']
    st.session_state.smart_hdd = best_hdd['Название']
    st.session_state.smart_generated = True

# ==========================================
# ИНТЕРФЕЙС ПРИЛОЖЕНИЯ
# ==========================================
st.title("✨ Smart PC Builder: AI Edition")

mode = st.radio("Режим подбора:", ["✨ ИИ-Ассистент", "🎮 По задаче (Пресеты)", "🤖 По процессору"], horizontal=True)
st.divider()

if mode == "✨ ИИ-Ассистент":
    st.subheader("Опишите компьютер вашей мечты")
    user_prompt = st.text_area("Например: 'Нужен комп для доты и КС2, чтобы не лагало, но денег мало'", height=100)
    
    if st.button("Сгенерировать сборку", type="primary"):
        if not user_prompt:
            st.warning("Пожалуйста, опишите ваши пожелания!")
        else:
            with st.spinner("🧠 ИИ анализирует запрос и подбирает компоненты..."):
                try:
                    system_prompt = """Ты эксперт по сборке ПК. Проанализируй запрос клиента и определи категорию.
                    Ответь ТОЛЬКО ОДНИМ словом:
                    БЮДЖЕТ - если игры легкие (CS, Dota), учеба, офис, или мало денег.
                    СРЕДНИЙ - если современные игры, 2K разрешение, стриминг, хороший бюджет.
                    МАКСИМУМ - если 4K, 3D монтаж, киберпанк на ультрах, или бюджет не ограничен."""
                    
                    client = OpenAI(
                        base_url="https://openrouter.ai/api/v1",
                        api_key=st.secrets["OPENROUTER_API_KEY"],
                        
                    )
                    models_to_try = [
                        "mistralai/ministral-14b-2512",       
                        "meta-llama/llama-3.3-70b-instruct:free",  
                        "deepseek/deepseek-chat-v3.1"               
                    ]
                    
                    ai_answer = None
                    
                    for model_name in models_to_try:
                        try:
                            response = client.chat.completions.create(
                                model=model_name,
                                messages=[
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": user_prompt}
                                ],
                                timeout=15
                            )
                            ai_answer = str(response.choices[0].message.content).upper()
                            break 
                        except Exception as e:
                            print(f"⚠️ Модель {model_name} занята. Переключаюсь...")
                            continue
                            
                    if not ai_answer:
                        raise Exception("Все бесплатные серверы сейчас перегружены.")
                        
                    st.toast(f"Ответ ИИ: {ai_answer}")
                    
                    cpus_sorted = cpus[cpus['Цена'] > 0].sort_values('Цена').reset_index(drop=True)
                    gpus_sorted = gpus[gpus['Цена'] > 0].sort_values('Цена').reset_index(drop=True)
                    
                    if "БЮДЖЕТ" in ai_answer:
                        target_cpu = cpus_sorted.iloc[0]
                        target_gpu = gpus_sorted.iloc[0]
                    elif "МАКСИМУМ" in ai_answer:
                        target_cpu = cpus_sorted.iloc[-1]
                        target_gpu = gpus_sorted.iloc[-1]
                    else:
                        target_cpu = cpus_sorted.iloc[len(cpus_sorted)//2]
                        target_gpu = gpus_sorted.iloc[len(gpus_sorted)//2]
                    
                    generate_build(target_cpu, target_gpu)
                    
                except Exception as e:
                    st.error(f"⚠️ Ошибка ИИ: {e}")

elif mode == "🎮 По задаче (Пресеты)":
    cpus_sorted = cpus[cpus['Цена'] > 0].sort_values('Цена').reset_index(drop=True)
    if len(cpus_sorted) >= 3:
        budget_cpu, mid_cpu, high_cpu = cpus_sorted.iloc[0], cpus_sorted.iloc[len(cpus_sorted)//2], cpus_sorted.iloc[-1]
    else:
        budget_cpu = mid_cpu = high_cpu = cpus_sorted.iloc[0]

    presets = {"Бюджетный / Офис": budget_cpu, "Оптимальный Гейминг": mid_cpu, "Максимум FPS": high_cpu}
    col_preset, col_btn = st.columns([2, 1])
    with col_preset: sel_preset = st.selectbox("Задача:", list(presets.keys()))
    with col_btn:
        st.write(""); st.write("")
        if st.button("🪄 Собрать", type="primary"):
            generate_build(presets[sel_preset])

elif mode == "🤖 По процессору":
    col_base, col_btn = st.columns([2, 1])
    with col_base:
        cpu_options = cpus[cpus['Цена'] > 0]['Название'].tolist()
        sel_cpu_name = st.selectbox("Основа (Процессор):", options=cpu_options, format_func=lambda x: format_with_price(x, cpus))
        cpu_series = cpus[cpus['Название'] == sel_cpu_name].iloc[0]
    with col_btn:
        st.write(""); st.write("")
        if st.button("⚖️ Сбалансировать", type="primary"):
            generate_build(cpu_series)

# ==========================================
# ИНТЕРАКТИВНЫЙ БЛОК ДЕТАЛЕЙ (С ЦЕНАМИ)
# ==========================================
st.markdown("### 🛠️ Детали вашей сборки")

def get_index(options_list, session_key):
    if session_key in st.session_state and st.session_state[session_key] in options_list:
        return options_list.index(st.session_state[session_key])
    return 0

col1, col2 = st.columns(2)

active_cpu_name = st.session_state.smart_cpu if st.session_state.smart_generated else cpus['Название'].iloc[0]
sel_cpu = cpus[cpus['Название'] == active_cpu_name].iloc[0]
cpu_socket = sel_cpu['Сокет']

with col1:
    cpu_options = cpus['Название'].tolist()
    sel_cpu_name = st.selectbox("Процессор", options=cpu_options, index=get_index(cpu_options, 'smart_cpu'), format_func=lambda x: format_with_price(x, cpus))
    sel_cpu = cpus[cpus['Название'] == sel_cpu_name].iloc[0]

    valid_mobos = mobos[mobos['Сокет'] == cpu_socket]
    mobo_options = valid_mobos['Название'].tolist() if not valid_mobos.empty else mobos['Название'].tolist()
    sel_mobo_name = st.selectbox("Материнская плата", options=mobo_options, index=get_index(mobo_options, 'smart_mobo') if get_index(mobo_options, 'smart_mobo') < len(mobo_options) else 0, format_func=lambda x: format_with_price(x, mobos))
    sel_mobo = mobos[mobos['Название'] == sel_mobo_name].iloc[0]

    valid_ram = ram[ram['Тип'] == sel_mobo['Тип ОЗУ']] if not valid_mobos.empty else ram
    ram_options = valid_ram['Название'].tolist() if not valid_ram.empty else ram['Название'].tolist()
    sel_ram_name = st.selectbox("Оперативная память", options=ram_options, index=get_index(ram_options, 'smart_ram') if get_index(ram_options, 'smart_ram') < len(ram_options) else 0, format_func=lambda x: format_with_price(x, ram))
    sel_ram = ram[ram['Название'] == sel_ram_name].iloc[0]

    valid_coolers = coolers[coolers['Совместимые сокеты'].str.contains(cpu_socket, na=False, case=False)]
    cooler_options = valid_coolers['Название'].tolist() if not valid_coolers.empty else coolers['Название'].tolist()
    sel_cooler_name = st.selectbox("Охлаждение процессора", options=cooler_options, index=get_index(cooler_options, 'smart_cooler') if get_index(cooler_options, 'smart_cooler') < len(cooler_options) else 0, format_func=lambda x: format_with_price(x, coolers))
    sel_cooler = coolers[coolers['Название'] == sel_cooler_name].iloc[0]

with col2:
    gpu_options = gpus['Название'].tolist()
    sel_gpu_name = st.selectbox("Видеокарта", options=gpu_options, index=get_index(gpu_options, 'smart_gpu'), format_func=lambda x: format_with_price(x, gpus))
    sel_gpu = gpus[gpus['Название'] == sel_gpu_name].iloc[0]

    psu_options = psus['Название'].tolist()
    sel_psu_name = st.selectbox("Блок питания", options=psu_options, index=get_index(psu_options, 'smart_psu'), format_func=lambda x: format_with_price(x, psus))
    sel_psu = psus[psus['Название'] == sel_psu_name].iloc[0]

    case_options = cases['Название'].tolist()
    sel_case_name = st.selectbox("Корпус", options=case_options, index=get_index(case_options, 'smart_case'), format_func=lambda x: format_with_price(x, cases))
    sel_case = cases[cases['Название'] == sel_case_name].iloc[0]

    ssd_options = ssds['Название'].tolist()
    sel_ssd_name = st.selectbox("Основной накопитель (SSD)", options=ssd_options, index=get_index(ssd_options, 'smart_ssd'), format_func=lambda x: format_with_price(x, ssds))
    sel_ssd = ssds[ssds['Название'] == sel_ssd_name].iloc[0]
    
    hdd_options = hdds['Название'].tolist()
    sel_hdd_name = st.selectbox("Дополнительный накопитель (HDD)", options=hdd_options, index=get_index(hdd_options, 'smart_hdd'), format_func=lambda x: format_with_price(x, hdds))
    sel_hdd = hdds[hdds['Название'] == sel_hdd_name].iloc[0]

st.divider()

# Считаем итоговую стоимость
total = sum([
    sel_cpu['Цена'], sel_mobo['Цена'], sel_ram['Цена'], 
    sel_cooler['Цена'], sel_gpu['Цена'], sel_psu['Цена'], 
    sel_case['Цена'], sel_ssd['Цена'], sel_hdd['Цена']
])

# --- ФИНАЛЬНЫЙ БЛОК: ИТОГИ, ГРАФИК И СКАЧИВАНИЕ ---
col_res1, col_res2 = st.columns([3, 1])

with col_res1:
    if st.session_state.smart_generated:
        st.success("🎉 Сборка готова! Все детали совместимы.")
    else:
        st.info("💡 Ваша текущая конфигурация:")

with col_res2:
    st.metric("💰 Итоговая стоимость", f"{total} ₽")

st.write("") # Небольшой отступ

# Разделяем экран на график (слева) и список для скачивания (справа)
col_chart, col_download = st.columns([1.5, 1])

with col_chart:
    # Подготовка данных для графика
    labels = ['Процессор', 'Мат. плата', 'ОЗУ', 'Охлаждение', 'Видеокарта', 'Блок питания', 'Корпус', 'SSD', 'HDD']
    prices = [sel_cpu['Цена'], sel_mobo['Цена'], sel_ram['Цена'], sel_cooler['Цена'], sel_gpu['Цена'], sel_psu['Цена'], sel_case['Цена'], sel_ssd['Цена'], sel_hdd['Цена']]

    # Создаем таблицу для графика и убираем детали с ценой 0 (например, если нет HDD)
    df_chart = pd.DataFrame({'Компонент': labels, 'Цена': prices})
    df_chart = df_chart[df_chart['Цена'] > 0]

    # Строим красивый круговой график (donut chart)
    fig = px.pie(df_chart, values='Цена', names='Компонент', hole=0.4)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=300)
    
    st.plotly_chart(fig, use_container_width=True)

with col_download:
    st.markdown("### Сохранить результат")
    st.markdown("Скачайте вашу сборку в виде текстового файла со списком покупок, чтобы отправить ее друзьям или показать в магазине.")
    
    # Формируем красивый текст для скачивания
    build_text = f"""🖥️ ВАША ИДЕАЛЬНАЯ СБОРКА ПК
======================================
1. Процессор: {sel_cpu['Название']} ({sel_cpu['Цена']} ₽)
2. Материнская плата: {sel_mobo['Название']} ({sel_mobo['Цена']} ₽)
3. Оперативная память: {sel_ram['Название']} ({sel_ram['Цена']} ₽)
4. Охлаждение: {sel_cooler['Название']} ({sel_cooler['Цена']} ₽)
5. Видеокарта: {sel_gpu['Название']} ({sel_gpu['Цена']} ₽)
6. Блок питания: {sel_psu['Название']} ({sel_psu['Цена']} ₽)
7. Корпус: {sel_case['Название']} ({sel_case['Цена']} ₽)
8. SSD: {sel_ssd['Название']} ({sel_ssd['Цена']} ₽)
"""
    # Добавляем HDD только если он выбран
    if sel_hdd['Цена'] > 0:
        build_text += f"9. HDD: {sel_hdd['Название']} ({sel_hdd['Цена']} ₽)\n"

    build_text += f"""======================================
💰 ИТОГОВАЯ СТОИМОСТЬ: {total} ₽
======================================
Сгенерировано в Smart PC Builder ✨
"""

    # Кнопка скачивания
    st.download_button(
        label="📥 Скачать список покупок (.txt)",
        data=build_text,
        file_name="My_PC_Build.txt",
        mime="text/plain",
        type="primary",
        use_container_width=True
    )