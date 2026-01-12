import streamlit as st
import re
import pandas as pd # Новая библиотека для Excel/CSV
from collections import Counter
from PIL import Image
import pytesseract
import pdfplumber
from pdf2image import convert_from_bytes
import requests
from deep_translator import GoogleTranslator
from wordfreq import zipf_frequency
import random

# --- 1. Настройки ---
st.set_page_config(page_title="DE Tutor B2", layout="wide")

STOP_WORDS = {
    "der", "die", "das", "und", "ist", "in", "zu", "den", "dem", "des", 
    "mit", "auf", "für", "von", "ein", "eine", "einen", "sich", "aus",
    "dass", "nicht", "war", "aber", "man", "bei", "wie", "wir", "oder",
    "kann", "sind", "werden", "wird", "auch", "noch", "nur", "vor", "nach",
    "über", "wenn", "zum", "zur", "habe", "hat", "durch", "unter", "diese",
    "telc", "deutsch", "prüfung", "test", "seite", "page", "express", "hueber",
    "aufgabe", "lösung", "antwortbogen", "teil", "kapitel", "übung", "verlag",
    "auflage", "gmbh", "druck", "isbn", "münchen", "klett", "cornelsen",
    "minuten", "punkte", "lesen", "hören", "schreiben", "sprechen",
    "text", "texte", "überschrift", "überschriften", "modelltest",
    "tipps", "tricks", "informationen", "antworten", "ankreuzen", "markieren",
    "richtig", "falsch", "insgesamt", "zeit", "beispiel", "nummer", "email", "euro"
}

# --- 2. Функции ---

@st.cache_data
def estimate_level(word):
    try:
        freq = zipf_frequency(word, 'de')
        if freq == 0: return "—"
        if freq > 5.5: return "A1"
        if freq > 4.5: return "A2"
        if freq > 3.8: return "B1"
        if freq > 2.8: return "B2" # B2 - это редкие слова
        return "C1"
    except: return "?"

@st.cache_data
def get_translation(word):
    try: return GoogleTranslator(source='de', target='ru').translate(word)
    except: return "-"

@st.cache_data
def get_synonyms(word):
    def fetch_api(query):
        url = f"https://www.openthesaurus.de/synonyme/search?q={query}&format=json"
        try:
            r = requests.get(url, timeout=1)
            if r.status_code == 200:
                data = r.json()
                found = []
                for synset in data.get('synsets', []):
                    for term in synset.get('terms', []):
                        t = re.sub(r"\(.*?\)", "", term.get('term')).strip()
                        if t.lower() != query.lower() and len(t.split()) < 3:
                            found.append(t)
                return list(dict.fromkeys(found))
        except: return []
        return []

    syns = fetch_api(word)
    if not syns and len(word) > 4:
        if word.endswith("en"): syns = fetch_api(word[:-2])
        elif word.endswith("s") or word.endswith("n"): syns = fetch_api(word[:-1])
    
    return ", ".join(syns[:4]) if syns else "—"

def extract_text(file_bytes, file_type, start, limit):
    text = ""
    start_idx = start - 1
    if file_type == "application/pdf":
        try:
            with pdfplumber.open(file_bytes) as pdf:
                if start_idx < len(pdf.pages):
                    pages = pdf.pages[start_idx : start_idx + limit]
                    for p in pages:
                        t = p.extract_text()
                        if t: text += t + "\n"
        except: pass

    if len(text) < 50 and file_type == "application/pdf":
        st.info(f"🔎 OCR работает над стр. {start}-{start+limit-1}...")
        try:
            file_bytes.seek(0)
            images = convert_from_bytes(file_bytes.read(), first_page=start, last_page=start+limit-1)
            for img in images:
                text += pytesseract.image_to_string(img, lang='deu') + "\n"
        except: pass
    elif file_type != "application/pdf":
        img = Image.open(file_bytes)
        text = pytesseract.image_to_string(img, lang='deu')
    return text

def process_text(text, min_len):
    clean_text = re.sub(r'[^a-zA-ZäöüÄÖÜß\s]', '', text)
    words = clean_text.split()
    filtered = []
    for w in words:
        if len(w) >= min_len and w.lower() not in STOP_WORDS and not w.isdigit():
            filtered.append(w)
    return Counter(filtered).most_common()

def find_context(text, word):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    for sent in sentences:
        if re.search(r'\b' + re.escape(word) + r'\b', sent, re.IGNORECASE):
            return sent.replace("\n", " ").strip()[:150]
    return "—"

# --- 3. Интерфейс ---

st.title("🇩🇪 Немецкий B2: Анализ + Тренировка")

# Вкладки: Анализ текста | Тренировка (Квиз)
tab1, tab2 = st.tabs(["📂 Создать словарь", "🎓 Тренировка (Квиз)"])

# Глобальная переменная для данных
if 'vocab_df' not in st.session_state:
    st.session_state.vocab_df = pd.DataFrame()

with tab1:
    with st.sidebar:
        st.header("Настройки")
        start_page = st.number_input("Страница", 1, 300, 54)
        pages_limit = st.slider("Сколько страниц", 1, 3, 1)
        max_words = st.slider("Слов в словарь", 10, 50, 15)

    uploaded_file = st.file_uploader("Загрузи PDF", type=['pdf', 'jpg'])

    if uploaded_file and st.button("🚀 Анализировать"):
        with st.spinner("Создаю базу данных..."):
            full_text = extract_text(uploaded_file, uploaded_file.type, start_page, pages_limit)
            
            if len(full_text) > 10:
                freq_list = process_text(full_text, 4)
                top_words = freq_list[:max_words]
                
                data = []
                prog = st.progress(0)
                for i, (word, count) in enumerate(top_words):
                    lvl = estimate_level(word)
                    trans = get_translation(word)
                    syns = get_synonyms(word)
                    ctx = find_context(full_text, word)
                    
                    data.append({
                        "Слово": word,
                        "Перевод": trans,
                        "Синонимы": syns,
                        "Контекст": ctx,
                        "Уровень": lvl
                    })
                    prog.progress((i+1)/len(top_words))
                
                # Сохраняем в память сессии
                st.session_state.vocab_df = pd.DataFrame(data)
                st.success(f"Готово! Найдено {len(data)} слов.")
            else:
                st.error("Текст не найден.")

    # Если данные есть, показываем таблицу и кнопку скачивания
    if not st.session_state.vocab_df.empty:
        df = st.session_state.vocab_df
        st.data_editor(df, hide_index=True)
        
        # КНОПКА СКАЧИВАНИЯ (Экспорт в CSV)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="💾 Скачать словарь (CSV для Excel/Anki)",
            data=csv,
            file_name='mein_wortschatz_b2.csv',
            mime='text/csv',
        )

with tab2:
    st.header("Проверь себя")
    
    if st.session_state.vocab_df.empty:
        st.warning("Сначала проанализируй файл во вкладке 'Создать словарь'!")
    else:
        # Логика квиза
        if 'current_word' not in st.session_state:
            st.session_state.current_word = st.session_state.vocab_df.sample(1).iloc[0]
            st.session_state.show_answer = False

        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🇩🇪 Слово:")
            st.markdown(f"# {st.session_state.current_word['Слово']}")
            
            st.info(f"💡 Контекст: *{st.session_state.current_word['Контекст']}*")
            
            if st.button("Показать перевод"):
                st.session_state.show_answer = True

        with col2:
            if st.session_state.show_answer:
                st.subheader("🇷🇺 Перевод:")
                st.success(f"**{st.session_state.current_word['Перевод']}**")
                
                st.subheader("🔗 Синонимы (B2):")
                st.warning(st.session_state.current_word['Синонимы'])
                
                if st.button("➡ Следующее слово"):
                    st.session_state.current_word = st.session_state.vocab_df.sample(1).iloc[0]
                    st.session_state.show_answer = False
                    st.rerun()
