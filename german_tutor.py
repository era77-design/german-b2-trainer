import streamlit as st
import re
from collections import Counter
from PIL import Image
import pytesseract
import pdfplumber
from pdf2image import convert_from_bytes
import requests
from deep_translator import GoogleTranslator
from wordfreq import zipf_frequency # Библиотека для оценки уровня слов

# --- 1. Настройки ---
st.set_page_config(page_title="DE Tutor Pro", layout="wide")
st.title("🇩🇪 Немецкий: Словарь, Уровни и Примеры")

# Оставляем только грамматический мусор. Полезные глаголы и существительные оставляем.
STOP_WORDS = {
    "der", "die", "das", "und", "ist", "in", "zu", "den", "dem", "des", 
    "mit", "auf", "für", "von", "ein", "eine", "einen", "sich", "aus",
    "dass", "nicht", "war", "aber", "man", "bei", "wie", "wir", "oder",
    "kann", "sind", "werden", "wird", "auch", "noch", "nur", "vor", "nach",
    "über", "wenn", "zum", "zur", "habe", "hat", "durch", "unter", "diese",
    "dieser", "ihre", "seine", "meine", "vom", "am", "im", "um", "als",
    "es", "sie", "er", "du", "ich", "mich", "mir", "dir", "uns", "ihnen"
}

# --- 2. Функции ---

@st.cache_data
def estimate_level(word):
    """
    Определяет уровень слова (A1-C1) на основе частоты использования.
    Использует шкалу Zipf (от 1 до 7).
    """
    freq = zipf_frequency(word, 'de')
    
    if freq == 0: return "N/A" # Слово не найдено в базе
    if freq > 5.5: return "A1" # Очень частое
    if freq > 4.5: return "A2"
    if freq > 4.0: return "B1"
    if freq > 3.0: return "B2"
    return "C1+" # Редкое

@st.cache_data
def get_translation(word):
    try:
        return GoogleTranslator(source='de', target='ru').translate(word)
    except:
        return "-"

@st.cache_data
def get_synonyms(word):
    """Улучшенный поиск синонимов"""
    url = f"https://www.openthesaurus.de/synonyme/search?q={word}&format=json"
    try:
        response = requests.get(url, timeout=3)
        data = response.json()
        synonyms = []
        
        # Перебираем все группы синонимов
        for synset in data.get('synsets', []):
            for term in synset.get('terms', []):
                term_word = term.get('term')
                # Фильтруем: не само слово, не фразы из 3+ слов
                if term_word.lower() != word.lower() and len(term_word.split()) < 3:
                    # Убираем скобки типа "(ugs.)"
                    clean_syn = re.sub(r"\(.*?\)", "", term_word).strip()
                    synonyms.append(clean_syn)
        
        # Убираем дубликаты и берем топ-3
        unique = list(dict.fromkeys(synonyms))
        return ", ".join(unique[:3])
    except:
        return ""

def find_context(text, word):
    """Ищет предложение с этим словом в тексте"""
    # Разбиваем текст на предложения (по точке, вопросу, воскл. знаку)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    for sent in sentences:
        # Ищем целое слово (чтобы "in" не находило "Berlin")
        if re.search(r'\b' + re.escape(word) + r'\b', sent, re.IGNORECASE):
            clean_sent = sent.replace("\n", " ").strip()
            if len(clean_sent) > 200: return clean_sent[:200] + "..."
            return clean_sent
    return "-"

def extract_text(file_bytes, file_type, start, limit):
    text = ""
    error = None
    start_idx = start - 1
    
    # 1. Попытка PDF text
    if file_type == "application/pdf":
        try:
            with pdfplumber.open(file_bytes) as pdf:
                pages = pdf.pages[start_idx : start_idx + limit]
                for p in pages:
                    t = p.extract_text()
                    if t: text += t + "\n"
        except: pass

    # 2. Попытка OCR
    if len(text) < 50:
        if file_type == "application/pdf":
            st.warning(f"📄 Работает OCR (стр. {start}-{start+limit-1})...")
            try:
                file_bytes.seek(0)
                images = convert_from_bytes(file_bytes.read(), first_page=start, last_page=start+limit-1)
                bar = st.progress(0)
                for i, img in enumerate(images):
                    text += pytesseract.image_to_string(img, lang='deu') + "\n"
                    bar.progress((i+1)/len(images))
            except Exception as e: error = str(e)
        else:
            img = Image.open(file_bytes)
            text = pytesseract.image_to_string(img, lang='deu')
            
    return text, error

def process_text(text, min_len):
    # Убираем всё кроме букв
    clean_text = re.sub(r'[^a-zA-ZäöüÄÖÜß\s]', '', text)
    words = clean_text.split()
    
    filtered = []
    for w in words:
        w_clean = w.strip()
        if len(w_clean) >= min_len and w_clean.lower() not in STOP_WORDS:
            filtered.append(w_clean)
            
    return Counter(filtered).most_common()

# --- 3. Интерфейс ---

with st.sidebar:
    st.header("Настройки")
    start_page = st.number_input("Начать со стр.", 1, 100, 7)
    pages_to_read = st.slider("Сколько страниц", 1, 5, 2)
    min_word_len = st.slider("Мин. длина слова", 2, 8, 3, help="Ставь 3, чтобы видеть слова типа 'tun' или 'neu'")
    max_words_show = st.slider("Сколько слов показать", 10, 50, 20)

st.write("### 🇩🇪 Умный анализ текста")
uploaded_file = st.file_uploader("Загрузи PDF или фото", type=['pdf', 'jpg', 'png'])

if uploaded_file and st.button("🚀 Анализировать"):
    with st.spinner("Читаем, переводим, оцениваем уровень..."):
        full_text, err = extract_text(uploaded_file, uploaded_file.type, start_page, pages_to_read)
        
        if err:
            st.error(f"Ошибка: {err}")
        elif len(full_text) < 10:
            st.warning("Текст не найден. Попробуй другие страницы.")
        else:
            # 1. Частотный анализ
            freq_list = process_text(full_text, min_word_len)
            top_words = freq_list[:max_words_show]
            
            # 2. Сбор данных
            table_data = []
            prog = st.progress(0)
            
            for i, (word, count) in enumerate(top_words):
                lvl = estimate_level(word)
                trans = get_translation(word)
                syns = get_synonyms(word)
                ctx = find_context(full_text, word)
                
                table_data.append({
                    "Уровень": lvl,
                    "Слово": word,
                    "Перевод": trans,
                    "Синонимы": syns if syns else "—",
                    "Пример из текста": ctx,
                    "В словарь": False
                })
                prog.progress((i+1)/len(top_words))
            
            st.success("Готово!")
            
            # 3. Вывод таблицы
            st.data_editor(
                table_data,
                column_config={
                    "Уровень": st.column_config.TextColumn("Uvl", help="A1-C2 (оценка)", width="small"),
                    "В словарь": st.column_config.CheckboxColumn("✅"),
                    "Пример из текста": st.column_config.TextColumn("Контекст", width="large")
                },
                height=800,
                hide_index=True
            )
