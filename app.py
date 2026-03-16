import streamlit as st
import pandas as pd
import re
import time
import plotly.express as px
from openai import OpenAI

# --- НАСТРОЙКИ СТРАНИЦЫ ---
st.set_page_config(page_title="Smart PC Builder v9.0", page_icon="✨", layout="wide")

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def extract_number(val, default=0):
    if pd.isna(val) or val == "" or val == 0: return default
    match = re.search(r'\d+', str(val))
    return int(match.group()) if match else default

@st.cache_data
def load_data():
    return pd.read_excel('Реальная_База_ПК.xlsx', sheet_name=None)

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

    none_hdd = pd.DataFrame([{"Название": "Нет дополнительного диска", "Цена": 0}])
    if hdds is None or hdds.empty:
        hdds = none_hdd
    else:
        hdds = pd.concat([none_hdd, hdds], ignore_index=True)

except Exception as e:
    st.error(f"Ошибка загрузки базы: {e}")
    st.stop()

if 'smart_generated' not in st.session_state:
    st.session_state.smart_generated = False

# --- ЛОГИКА ОЦЕНКИ РЕЛЕВАНТНОСТИ (БОТТЛНЕК-АНАЛИЗАТОР) ---
def get_relevance(price, category, base_cpu_price):
    """Оценивает деталь относительно цены процессора (Основы)"""
    if base_cpu_price <= 0 or price <= 0: return ""
    
    ratio = price / base_cpu_price
    
    # Идеальные пропорции бюджета: (мин_коэффициент, макс_коэффициент)
    ratios = {
        'GPU': (1.2, 3.2),    # Видеокарта должна быть дороже ЦП в 1.2 - 3 раза
        'Mobo': (0.3, 1.2),   # Плата
        'RAM': (0.15, 0.6),   # Память
        'Cooler': (0.05, 0.4),# Кулер
        'PSU': (0.15, 0.5)    # Блок питания
    }
    
    if category not in ratios:
        return "⚪" # Нейтрально для корпусов и дисков
        
    min_r, max_r = ratios[category]
    if ratio < min_r:
        return "🟡 Слишком слабо"
    elif ratio > max_r:
        return "🔴 Избыточно (Не раскроется)"
    else:
        return "🟢 Оптимально"

def format_item(item_name, df, category, base_cpu_price):
    if item_name == "Нет дополнительного диска": return item_name
    try:
        price = df[df['Название'] == item_name].iloc[0]['Цена']
        rel = get_relevance(price, category, base_cpu_price)
        rel_str = f" [{rel}]" if rel and category != "CPU" else ""
        return f"{item_name}{rel_str}  —  {price} ₽"
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
st.title("✨ Smart PC Builder v9.0")

# 1. Главный режим теперь выпадающий список
mode = st.selectbox("⚙️ Режим работы конфигуратора:", ["✨ ИИ-Ассистент", "🎮 По задаче (Пресеты)", "🤖 По процессору"])
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
                    Ответь ТОЛЬКО ОДНИМ словом: БЮДЖЕТ, СРЕДНИЙ, МАКСИМУМ."""
                    
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
                                model=model_name, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], timeout=15
                            )
                            ai_answer = str(response.choices[0].message.content).upper()
                            break 
                        except:
                            continue
                            
                    if not ai_answer: raise Exception("Все бесплатные серверы перегружены.")
                        
                    st.toast(f"Ответ ИИ: {ai_answer}")
                    
                    cpus_sorted = cpus[cpus['Цена'] > 0].sort_values('Цена').reset_index(drop=True)
                    gpus_sorted = gpus[gpus['Цена'] > 0].sort_values('Цена').reset_index(drop=True)
                    
                    if "БЮДЖЕТ" in ai_answer: generate_build(cpus_sorted.iloc[0], gpus_sorted.iloc[0])
                    elif "МАКСИМУМ" in ai_answer: generate_build(cpus_sorted.iloc[-1], gpus_sorted.iloc[-1])
                    else: generate_build(cpus_sorted.iloc[len(cpus_sorted)//2], gpus_sorted.iloc[len(gpus_sorted)//2])
                    
                except Exception as e:
                    st.error(f"⚠️ Ошибка ИИ: {e}")

elif mode == "🎮 По задаче (Пресеты)":
    cpus_sorted = cpus[cpus['Цена'] > 0].sort_values('Цена').reset_index(drop=True)
    budget_cpu = cpus_sorted.iloc[0]
    mid_cpu = cpus_sorted.iloc[len(cpus_sorted)//2] if len(cpus_sorted) >= 3 else budget_cpu
    high_cpu = cpus_sorted.iloc[-1] if len(cpus_sorted) >= 3 else budget_cpu

    presets = {"Бюджетный / Офис": budget_cpu, "Оптимальный Гейминг": mid_cpu, "Максимум FPS": high_cpu}
    col_preset, col_btn = st.columns([2, 1])
    with col_preset: sel_preset = st.selectbox("Задача:", list(presets.keys()))
    with col_btn:
        st.write(""); st.write("")
        if st.button("🪄 Собрать", type="primary"): generate_build(presets[sel_preset])

elif mode == "🤖 По процессору":
    col_base, col_btn = st.columns([2, 1])
    with col_base:
        cpu_options = cpus[cpus['Цена'] > 0]['Название'].tolist()
        sel_cpu_name = st.selectbox("Основа (Процессор):", options=cpu_options, format_func=lambda x: format_item(x, cpus, "CPU", 1))
        cpu_series = cpus[cpus['Название'] == sel_cpu_name].iloc[0]
    with col_btn:
        st.write(""); st.write("")
        if st.button("⚖️ Сбалансировать", type="primary"): generate_build(cpu_series)

# ==========================================
# 2. ПЛАВНЫЙ СЛАЙДЕР ВИДА СБОРКИ (Segmented Control)
# ==========================================
st.divider()
view_mode = st.segmented_control("🎨 Вид интерфейса сборки:", ["📝 Карточки (Списки)", "📋 Интерактивная таблица"], default="📝 Карточки (Списки)")

def get_index(options_list, session_key):
    if session_key in st.session_state and st.session_state[session_key] in options_list:
        return options_list.index(st.session_state[session_key])
    return 0

# Базовая цена ЦП для расчета Боттлнеков (Оценок)
active_cpu_name = st.session_state.smart_cpu if st.session_state.smart_generated else cpus['Название'].iloc[0]
base_cpu_price = cpus[cpus['Название'] == active_cpu_name].iloc[0]['Цена']

# --- РЕЖИМ: КАРТОЧКИ ---
if view_mode == "📝 Карточки (Списки)":
    col1, col2 = st.columns(2)
    
    with col1:
        cpu_options = cpus['Название'].tolist()
        sel_cpu_name = st.selectbox("Процессор", options=cpu_options, index=get_index(cpu_options, 'smart_cpu'), format_func=lambda x: format_item(x, cpus, "CPU", base_cpu_price))
        sel_cpu = cpus[cpus['Название'] == sel_cpu_name].iloc[0]
        cpu_socket = sel_cpu['Сокет']

        valid_mobos = mobos[mobos['Сокет'] == cpu_socket]
        mobo_options = valid_mobos['Название'].tolist() if not valid_mobos.empty else mobos['Название'].tolist()
        sel_mobo_name = st.selectbox("Материнская плата", options=mobo_options, index=get_index(mobo_options, 'smart_mobo') if get_index(mobo_options, 'smart_mobo') < len(mobo_options) else 0, format_func=lambda x: format_item(x, mobos, "Mobo", base_cpu_price))
        sel_mobo = mobos[mobos['Название'] == sel_mobo_name].iloc[0]

        valid_ram = ram[ram['Тип'] == sel_mobo['Тип ОЗУ']] if not valid_mobos.empty else ram
        ram_options = valid_ram['Название'].tolist() if not valid_ram.empty else ram['Название'].tolist()
        sel_ram_name = st.selectbox("Оперативная память", options=ram_options, index=get_index(ram_options, 'smart_ram') if get_index(ram_options, 'smart_ram') < len(ram_options) else 0, format_func=lambda x: format_item(x, ram, "RAM", base_cpu_price))
        sel_ram = ram[ram['Название'] == sel_ram_name].iloc[0]

        valid_coolers = coolers[coolers['Совместимые сокеты'].str.contains(cpu_socket, na=False, case=False)]
        cooler_options = valid_coolers['Название'].tolist() if not valid_coolers.empty else coolers['Название'].tolist()
        sel_cooler_name = st.selectbox("Охлаждение процессора", options=cooler_options, index=get_index(cooler_options, 'smart_cooler') if get_index(cooler_options, 'smart_cooler') < len(cooler_options) else 0, format_func=lambda x: format_item(x, coolers, "Cooler", base_cpu_price))
        sel_cooler = coolers[coolers['Название'] == sel_cooler_name].iloc[0]

    with col2:
        gpu_options = gpus['Название'].tolist()
        sel_gpu_name = st.selectbox("Видеокарта", options=gpu_options, index=get_index(gpu_options, 'smart_gpu'), format_func=lambda x: format_item(x, gpus, "GPU", base_cpu_price))
        sel_gpu = gpus[gpus['Название'] == sel_gpu_name].iloc[0]

        psu_options = psus['Название'].tolist()
        sel_psu_name = st.selectbox("Блок питания", options=psu_options, index=get_index(psu_options, 'smart_psu'), format_func=lambda x: format_item(x, psus, "PSU", base_cpu_price))
        sel_psu = psus[psus['Название'] == sel_psu_name].iloc[0]

        case_options = cases['Название'].tolist()
        sel_case_name = st.selectbox("Корпус", options=case_options, index=get_index(case_options, 'smart_case'), format_func=lambda x: format_item(x, cases, "Case", base_cpu_price))
        sel_case = cases[cases['Название'] == sel_case_name].iloc[0]

        ssd_options = ssds['Название'].tolist()
        sel_ssd_name = st.selectbox("Основной накопитель (SSD)", options=ssd_options, index=get_index(ssd_options, 'smart_ssd'), format_func=lambda x: format_item(x, ssds, "SSD", base_cpu_price))
        sel_ssd = ssds[ssds['Название'] == sel_ssd_name].iloc[0]
        
        hdd_options = hdds['Название'].tolist()
        sel_hdd_name = st.selectbox("Дополнительный накопитель (HDD)", options=hdd_options, index=get_index(hdd_options, 'smart_hdd'), format_func=lambda x: format_item(x, hdds, "HDD", base_cpu_price))
        sel_hdd = hdds[hdds['Название'] == sel_hdd_name].iloc[0]

# --- РЕЖИМ: ИНТЕРАКТИВНАЯ ТАБЛИЦА ---
else:
    st.markdown("### 📋 Интерактивная таблица комплектующих")
    
    # Вспомогательная функция для компактной отрисовки строк
    def table_row(label, options, session_key, df, cat, base_price, dependent_filter=None):
        c1, c2 = st.columns([1, 4])
        c1.markdown(f"<p style='padding-top: 8px;'><b>{label}</b></p>", unsafe_allow_html=True)
        idx = get_index(options, session_key) if get_index(options, session_key) < len(options) else 0
        sel = c2.selectbox(f"hidden_{session_key}", options, index=idx, label_visibility="collapsed", format_func=lambda x: format_item(x, df, cat, base_price))
        return df[df['Название'] == sel].iloc[0]

    cpu_options = cpus['Название'].tolist()
    sel_cpu = table_row("Процессор", cpu_options, 'smart_cpu', cpus, "CPU", base_cpu_price)
    
    valid_mobos = mobos[mobos['Сокет'] == sel_cpu['Сокет']]
    mobo_options = valid_mobos['Название'].tolist() if not valid_mobos.empty else mobos['Название'].tolist()
    sel_mobo = table_row("Мат. плата", mobo_options, 'smart_mobo', mobos, "Mobo", base_cpu_price)

    valid_ram = ram[ram['Тип'] == sel_mobo['Тип ОЗУ']] if not valid_mobos.empty else ram
    ram_options = valid_ram['Название'].tolist() if not valid_ram.empty else ram['Название'].tolist()
    sel_ram = table_row("ОЗУ", ram_options, 'smart_ram', ram, "RAM", base_cpu_price)

    valid_coolers = coolers[coolers['Совместимые сокеты'].str.contains(sel_cpu['Сокет'], na=False, case=False)]
    cooler_options = valid_coolers['Название'].tolist() if not valid_coolers.empty else coolers['Название'].tolist()
    sel_cooler = table_row("Охлаждение", cooler_options, 'smart_cooler', coolers, "Cooler", base_cpu_price)

    sel_gpu = table_row("Видеокарта", gpus['Название'].tolist(), 'smart_gpu', gpus, "GPU", base_cpu_price)
    sel_psu = table_row("Блок питания", psus['Название'].tolist(), 'smart_psu', psus, "PSU", base_cpu_price)
    sel_case = table_row("Корпус", cases['Название'].tolist(), 'smart_case', cases, "Case", base_cpu_price)
    sel_ssd = table_row("SSD диск", ssds['Название'].tolist(), 'smart_ssd', ssds, "SSD", base_cpu_price)
    sel_hdd = table_row("HDD диск", hdds['Название'].tolist(), 'smart_hdd', hdds, "HDD", base_cpu_price)


# ==========================================
# ИТОГИ, ГРАФИКИ И СКАЧИВАНИЕ
# ==========================================
st.divider()

total = sum([sel_cpu['Цена'], sel_mobo['Цена'], sel_ram['Цена'], sel_cooler['Цена'], sel_gpu['Цена'], sel_psu['Цена'], sel_case['Цена'], sel_ssd['Цена'], sel_hdd['Цена']])

col_res1, col_res2 = st.columns([3, 1])
with col_res1:
    if st.session_state.smart_generated: st.success("🎉 Сборка готова! Оценки деталей пересчитаны.")
with col_res2:
    st.metric("💰 Итоговая стоимость", f"{total} ₽")

col_chart, col_download = st.columns([1.5, 1])

with col_chart:
    # 3. Плавный слайдер переключения графиков
    chart_mode = st.segmented_control("📈 Вид графика:", ["🍩 Круговая", "📊 Столбчатая"], default="🍩 Круговая")
    
    labels = ['Процессор', 'Мат. плата', 'ОЗУ', 'Охлаждение', 'Видеокарта', 'Блок питания', 'Корпус', 'SSD', 'HDD']
    prices = [sel_cpu['Цена'], sel_mobo['Цена'], sel_ram['Цена'], sel_cooler['Цена'], sel_gpu['Цена'], sel_psu['Цена'], sel_case['Цена'], sel_ssd['Цена'], sel_hdd['Цена']]
    df_chart = pd.DataFrame({'Компонент': labels, 'Цена': prices})
    df_chart = df_chart[df_chart['Цена'] > 0]

    # 4. Отрисовка выбранного графика
    if chart_mode == "🍩 Круговая":
        fig = px.pie(df_chart, values='Цена', names='Компонент', hole=0.4, color_discrete_sequence=px.colors.sequential.Teal)
        fig.update_traces(textposition='inside', textinfo='percent+label')
    else:
        # Столбчатая диаграмма, отсортированная по убыванию цены
        df_chart = df_chart.sort_values(by='Цена', ascending=True)
        fig = px.bar(df_chart, x='Цена', y='Компонент', orientation='h', text='Цена', color='Цена', color_continuous_scale='Teal')
        fig.update_traces(texttemplate='%{text} ₽', textposition='outside')
        fig.update_layout(xaxis_title="Стоимость (₽)", yaxis_title="")

    fig.update_layout(showlegend=False, margin=dict(t=10, b=0, l=0, r=0), height=350)
    st.plotly_chart(fig, use_container_width=True)

with col_download:
    st.markdown("### 💾 Сохранить результат")
    build_text = f"""🖥️ ВАША ИДЕАЛЬНАЯ СБОРКА ПК
======================================
1. Процессор: {sel_cpu['Название']} ({sel_cpu['Цена']} ₽)
2. Материнская плата: {sel_mobo['Название']} ({sel_mobo['Цена']} ₽)
3. Оперативная память: {sel_ram['Название']} ({sel_ram['Цена']} ₽)
4. Охлаждение: {sel_cooler['Название']} ({sel_cooler['Цена']} ₽)
5. Видеокарта: {sel_gpu['Название']} ({sel_gpu['Цена']} ₽)
6. Блок питания: {sel_psu['Название']} ({sel_psu['Цена']} ₽)
7. Корпус: {sel_case['Название']} ({sel_case['Цена']} ₽)
8. SSD: {sel_ssd['Название']} ({sel_ssd['Цена']} ₽)\n"""
    if sel_hdd['Цена'] > 0: build_text += f"9. HDD: {sel_hdd['Название']} ({sel_hdd['Цена']} ₽)\n"
    build_text += f"======================================\n💰 ИТОГОВАЯ СТОИМОСТЬ: {total} ₽\n"

    st.download_button(label="📥 Скачать список покупок (.txt)", data=build_text, file_name="My_PC_Build.txt", mime="text/plain", type="primary", use_container_width=True)