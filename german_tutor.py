import streamlit as st
import re
import pandas as pd
import time
from collections import Counter
from PIL import Image
import pytesseract
import pdfplumber
from pdf2image import convert_from_bytes
import requests
from deep_translator import GoogleTranslator
from wordfreq import zipf_frequency
import gc 

# --- 1. Настройки ---
st.set_page_config(page_title="DE B2 Master", layout="wide")

# Стоп-слова (фильтр мусора + имен собственных из книги)
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
    "richtig", "falsch", "insgesamt", "zeit", "beispiel", "nummer", "email", 
    "euro", "dagmar", "giersberg", "track", "transkriptionen"
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
        if freq > 2.8: return "B2"
        return "C1"
    except: return "?"

@st.cache_data
def get_translation(word):
    try: return GoogleTranslator(source='de', target='ru').translate(word)
    except: return "-"

@st.cache_data
def get_synonyms(word):
    """
    Усиленный поиск синонимов с защитой от блокировки.
    """
    # Заголовки, чтобы притвориться браузером (важно!)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    def fetch_api(query):
        url = f"https://www.openthesaurus.de/synonyme/search?q={query}&format=json"
        try:
            # Увеличили тайм-аут до 5 секунд
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                found = []
                for synset in data.get('synsets', []):
                    for term in synset.get('terms', []):
                        t = re.sub(r"\(.*?\)", "", term.get('term')).strip()
                        # Фильтр: не само слово, не фраза
                        if t.lower() != query.lower() and len(t.split()) < 3:
                            found.append(t)
                return list(dict.fromkeys(found))
        except: return []
        return []

    # Небольшая пауза, чтобы API не забанил нас за спам
    time.sleep(0.1) 
    
    syns = fetch_api(word)
    
    # Если не нашли, пробуем убрать окончания (Plural -> Singular)
    if not syns and len(word) > 4:
        if word.endswith("en"): syns = fetch_api(word[:-2])
        elif word.endswith("s") or word.endswith("n") or word.endswith("e"): 
            syns = fetch_api(word[:-1])
    
    # Возвращаем топ-4
    return ", ".join(syns[:4]) if syns else "—"

def process_text_chunk(text):
    # Оставляем умлауты и буквы
    clean_text = re.sub(r'[^a-zA-ZäöüÄÖÜß\s]', '', text)
    words = clean_text.split()
    filtered = []
    for w in words:
        # Фильтр: длина > 3, не стоп-слово, не число, начинается с Большой (существительные)
        # или просто важные глаголы.
        if len(w) >= 4 and w.lower() not in STOP_WORDS and not w.isdigit():
            filtered.append(w)
    return filtered

def find_context(text, word):
    # Ищем предложение
    sentences = re.split(r'(?<=[.!?])\s+', text)
    for sent in sentences:
        if re.search(r'\b' + re.escape(word) + r'\b', sent, re.IGNORECASE):
            clean = sent.replace("\n", " ").strip()
            return clean[:150]
    return "—"

def process_pdf_full(file_obj, start_p, num_pages):
    all_words = []
    full_context_text = ""
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    file_bytes = file_obj.read()
    
    for i in range(num_pages):
        current_page_idx = start_p - 1 + i
        status_text.text(f"⏳ Сканирую страницу {start_p + i}...")
        
        page_text = ""
        
        # 1. Текст из PDF
        try:
            with pdfplumber.open(file_obj) as pdf:
                if current_page_idx < len(pdf.pages):
                    page_text = pdf.pages[current_page_idx].extract_text()
        except: pass

        # 2. OCR (если текст не найден или его мало)
        if not page_text or len(page_text) < 100:
            try:
                images = convert_from_bytes(
                    file_bytes, 
                    first_page=current_page_idx+1, 
                    last_page=current_page_idx+1
                )
                if images:
                    # psm 6 = block of text (хорошо для книг)
                    config = r'--psm 6' 
                    page_text = pytesseract.image_to_string(images[0], lang='deu', config=config)
                    del images
                    gc.collect()
            except Exception: pass

        if page_text:
            words_in_page = process_text_chunk(page_text)
            all_words.extend(words_in_page)
            full_context_text += page_text + "\n"
        
        progress_bar.progress((i + 1) / num_pages)

    return all_words, full_context_text

# --- 3. Интерфейс ---

st.title("🇩🇪 Генератор слов для Quizlet (B2)")
st.markdown("Загрузи учебник, выбери страницы, и я создам файл с **синонимами** и **переводом**.")

if 'vocab_df' not in st.session_state:
    st.session_state.vocab_df = pd.DataFrame()

with st.sidebar:
    st.header("⚙️ Настройки")
    st.info("Лучшие тексты в твоей книге: \n- Стр. 15 (Питание)\n- Стр. 54 (Resilienz)\n- Стр. 69 (Завтрак)")
    
    start_page = st.number_input("Начать со стр.", 1, 500, 54)
    pages_to_scan = st.number_input("Сколько страниц читать?", 1, 50, 1)
    max_vocab_size = st.slider("Сколько слов сохранить", 10, 100, 20)

uploaded_file = st.file_uploader("PDF файл", type=['pdf'])

if uploaded_file and st.button("🚀 Создать словарь"):
    st.session_state.vocab_df = pd.DataFrame()
    
    with st.spinner("Анализ текста..."):
        uploaded_file.seek(0)
        raw_words, full_text = process_pdf_full(uploaded_file, start_page, pages_to_scan)
        
    if not raw_words:
        st.error("Слов не найдено.")
    else:
        st.info(f"Найдено {len(raw_words)} слов. Перевожу и ищу синонимы для топ-{max_vocab_size}...")
        
        # Считаем частоту
        top_words_tuples = Counter(raw_words).most_common(max_vocab_size)
        
        data = []
        vocab_bar = st.progress(0)
        
        for idx, (word, count) in enumerate(top_words_tuples):
            if len(word) < 3: continue
                
            lvl = estimate_level(word)
            trans = get_translation(word)
            syns = get_synonyms(word) # ТЕПЕРЬ РАБОТАЕТ ЛУЧШЕ
            ctx = find_context(full_text, word)
            
            data.append({
                "Слово": word,
                "Перевод": trans,
                "Синонимы": syns,
                "Уровень": lvl,
                "Контекст": ctx
            })
            vocab_bar.progress((idx + 1) / len(top_words_tuples))
            
        st.session_state.vocab_df = pd.DataFrame(data)
        st.success("Готово! Синонимы загружены.")

# --- 4. Результат и Скачивание ---

if not st.session_state.vocab_df.empty:
    df = st.session_state.vocab_df
    
    # Показываем таблицу (можно редактировать)
    edited_df = st.data_editor(df, hide_index=True)
    
    st.write("### 📥 Скачать файлы")
    c1, c2 = st.columns(2)
    
    with c1:
        # Для Excel/GitHub
        csv = edited_df.to_csv(index=False, sep=';').encode('utf-8-sig')
        st.download_button("💾 CSV для Excel/GitHub", csv, "wortschatz.csv", "text/csv")
        
    with c2:
        # Для Quizlet (Специальный формат)
        # Формат: Слово (tab) Перевод; Синонимы
        quizlet_text = ""
        for index, row in edited_df.iterrows():
            term = row['Слово']
            # Объединяем перевод и синонимы в "Определение"
            defin = f"{row['Перевод']} (Syn: {row['Синонимы']}) [Lvl: {row['Уровень']}]"
            quizlet_text += f"{term}\t{defin}\n"
            
        st.download_button("🦉 Файл для Quizlet", quizlet_text.encode('utf-8'), "quizlet_import.txt", "text/plain")
        
    st.info("**Инструкция для Quizlet:**\n1. Нажми 'Create set'.\n2. Нажми ссылку 'Import from Word, Excel...'.\n3. Скопируй текст из скачанного файла и вставь в поле.")
