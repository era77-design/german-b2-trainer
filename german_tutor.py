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
import gc # Сборщик мусора для очистки памяти

# --- 1. Настройки страницы ---
st.set_page_config(page_title="DE B2 Master", layout="wide")

# Стоп-слова (фильтр мусора)
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

# --- 2. Функции логики ---

@st.cache_data
def estimate_level(word):
    """Оценка уровня сложности (A1-C2)"""
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
    """Перевод Google"""
    try: return GoogleTranslator(source='de', target='ru').translate(word)
    except: return "-"

@st.cache_data
def get_synonyms(word):
    """
    Агрессивный поиск синонимов.
    Если не находит слово, пытается убрать окончания (Plural -> Singular).
    """
    def fetch_api(query):
        url = f"https://www.openthesaurus.de/synonyme/search?q={query}&format=json"
        try:
            r = requests.get(url, timeout=1)
            if r.status_code == 200:
                data = r.json()
                found = []
                for synset in data.get('synsets', []):
                    for term in synset.get('terms', []):
                        # Чистим от скобок (ugs.)
                        t = re.sub(r"\(.*?\)", "", term.get('term')).strip()
                        # Фильтр: не само слово и не фраза из 3 слов
                        if t.lower() != query.lower() and len(t.split()) < 3:
                            found.append(t)
                return list(dict.fromkeys(found))
        except: return []
        return []

    syns = fetch_api(word)
    # Если не нашли, пробуем резать окончания
    if not syns and len(word) > 4:
        if word.endswith("en"): syns = fetch_api(word[:-2])
        elif word.endswith("s") or word.endswith("n"): syns = fetch_api(word[:-1])
    
    return ", ".join(syns[:4]) if syns else "—"

def process_text_chunk(text):
    """Чистит кусок текста и возвращает список слов"""
    clean_text = re.sub(r'[^a-zA-ZäöüÄÖÜß\s]', '', text)
    words = clean_text.split()
    filtered = []
    for w in words:
        # Фильтр: мин длина 4, не стоп-слово, не число
        if len(w) >= 4 and w.lower() not in STOP_WORDS and not w.isdigit():
            filtered.append(w)
    return filtered

def find_context(text, word):
    """Ищет пример использования слова"""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    for sent in sentences:
        if re.search(r'\b' + re.escape(word) + r'\b', sent, re.IGNORECASE):
            return sent.replace("\n", " ").strip()[:120]
    return "—"

def process_pdf_full(file_obj, start_p, num_pages):
    """
    Умная обработка PDF постранично, чтобы не переполнить память.
    Возвращает список всех найденных слов и сырой текст (для контекста).
    """
    all_words = []
    full_context_text = ""
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    file_bytes = file_obj.read()
    
    # Цикл по страницам
    for i in range(num_pages):
        current_page_idx = start_p - 1 + i
        status_text.text(f"⏳ Обрабатываю страницу {start_p + i}...")
        
        page_text = ""
        
        # 1. Пробуем вытащить текст (быстро)
        try:
            with pdfplumber.open(file_obj) as pdf:
                if current_page_idx < len(pdf.pages):
                    page_text = pdf.pages[current_page_idx].extract_text()
        except: pass

        # 2. Если текста нет -> OCR (медленно, но надежно)
        if not page_text or len(page_text) < 50:
            try:
                # Конвертируем ТОЛЬКО одну страницу в картинку
                images = convert_from_bytes(
                    file_bytes, 
                    first_page=current_page_idx+1, 
                    last_page=current_page_idx+1
                )
                if images:
                    page_text = pytesseract.image_to_string(images[0], lang='deu')
                    del images # Удаляем картинку из памяти
                    gc.collect() # Принудительная чистка памяти
            except Exception as e:
                print(f"Ошибка OCR на стр {current_page_idx+1}: {e}")

        if page_text:
            # Собираем слова
            words_in_page = process_text_chunk(page_text)
            all_words.extend(words_in_page)
            full_context_text += page_text + "\n"
        
        # Обновляем прогресс
        progress_bar.progress((i + 1) / num_pages)

    return all_words, full_context_text

# --- 3. Интерфейс ---

st.title("🇩🇪 Немецкий B2: Генератор Базы для Quizlet")
st.markdown("Загрузи PDF, выбери страницы, и я создам файл для импорта слов.")

# Глобальное хранилище данных
if 'vocab_df' not in st.session_state:
    st.session_state.vocab_df = pd.DataFrame()

with st.sidebar:
    st.header("⚙️ Настройки сканирования")
    st.info("⚠️ Сканирование всей книги может занять 5-10 минут. Для теста выбери 2-3 страницы.")
    
    start_page = st.number_input("С какой страницы начать?", 1, 500, 54)
    pages_to_scan = st.number_input("Сколько страниц сканировать?", 1, 50, 2)
    max_vocab_size = st.slider("Максимум слов в словаре", 10, 100, 20)

uploaded_file = st.file_uploader("Загрузи учебник (PDF)", type=['pdf'])

if uploaded_file and st.button("🚀 Начать сканирование"):
    # Сбрасываем старые данные
    st.session_state.vocab_df = pd.DataFrame()
    
    # 1. Сбор слов
    with st.spinner("Читаю книгу..."):
        # Передаем файл в функцию (важно: seek(0) внутри pdfplumber может требоваться)
        uploaded_file.seek(0)
        raw_words, full_text = process_pdf_full(uploaded_file, start_page, pages_to_scan)
        
    if not raw_words:
        st.error("Слов не найдено. Попробуй другие страницы.")
    else:
        # 2. Анализ частотности (топ слов)
        st.info(f"Найдено {len(raw_words)} слов. Отбираю топ-{max_vocab_size} самых важных...")
        top_words_tuples = Counter(raw_words).most_common(max_vocab_size)
        
        # 3. Перевод и Синонимы (самая долгая часть)
        data = []
        vocab_bar = st.progress(0)
        
        for idx, (word, count) in enumerate(top_words_tuples):
            # Пропускаем, если слово слишком короткое или мусор
            if len(word) < 3: continue
                
            lvl = estimate_level(word)
            trans = get_translation(word)
            syns = get_synonyms(word)
            ctx = find_context(full_text, word)
            
            data.append({
                "Слово (Term)": word,
                "Перевод (Definition)": trans,
                "Синонимы": syns,
                "Уровень": lvl,
                "Контекст": ctx
            })
            vocab_bar.progress((idx + 1) / len(top_words_tuples))
            
        st.session_state.vocab_df = pd.DataFrame(data)
        st.success("Готово! Словарь создан.")

# --- 4. Результаты и Экспорт ---

if not st.session_state.vocab_df.empty:
    df = st.session_state.vocab_df
    
    # Показываем таблицу
    st.subheader("Твой Словарь")
    st.data_editor(df, hide_index=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Экспорт для Excel/GitHub (CSV с точкой с запятой)
        csv_excel = df.to_csv(index=False, sep=';').encode('utf-8-sig')
        st.download_button(
            label="💾 Скачать CSV (для Excel/GitHub)",
            data=csv_excel,
            file_name=f'german_b2_pages_{start_page}_{start_page+pages_to_scan}.csv',
            mime='text/csv',
        )
        
    with col2:
        # Экспорт специально для Quizlet
        # Формат: Слово [TAB] Перевод + Синонимы
        # Объединяем перевод и синонимы в одно поле определения
        quizlet_data = ""
        for index, row in df.iterrows():
            term = row['Слово (Term)']
            # В определение пишем: Перевод (Синонимы: ...) [Контекст: ...]
            definition = f"{row['Перевод (Definition)']} (Syn: {row['Синонимы']})"
            quizlet_data += f"{term}\t{definition}\n"
            
        st.download_button(
            label="🦉 Скачать для Quizlet (Copy-Paste)",
            data=quizlet_data.encode('utf-8'),
            file_name='quizlet_import.txt',
            mime='text/plain',
            help="Загрузи этот файл в Quizlet через функцию 'Import from Word, Excel, Google Docs'"
        )

    st.info("💡 **Как загрузить в Quizlet:**\n1. Открой Quizlet -> 'Create Set'.\n2. Нажми '+ Import from Word, Excel, Google Docs'.\n3. Открой скачанный txt-файл, скопируй весь текст и вставь туда.")
