import streamlit as st
import re
from collections import Counter
from PIL import Image
import pytesseract
import pdfplumber
from pdf2image import convert_from_bytes
import requests # Библиотека для запросов в интернет

# --- 1. Настройки ---
st.set_page_config(page_title="Немецкий B2 Trainer", layout="wide")
st.title("🇩🇪 Немецкий B2: Словарь + Синонимы")

# Эти слова мы игнорируем (слишком простые для B2)
STOP_WORDS = {
    "der", "die", "das", "und", "ist", "in", "zu", "den", "dem", "des", 
    "mit", "auf", "für", "von", "ein", "eine", "einen", "sich", "aus",
    "dass", "nicht", "war", "aber", "man", "bei", "wie", "wir", "oder",
    "kann", "sind", "werden", "wird", "auch", "noch", "nur", "vor", "nach",
    "über", "wenn", "zum", "zur", "habe", "hat", "durch", "unter", "diese",
    "telc", "deutsch", "prüfung", "test", "seite", "page", "express", "hueber",
    "aufgabe", "lösung", "antwortbogen", "teil", "kapitel", "übung"
}

# --- 2. Функции ---

@st.cache_data # Кэшируем, чтобы не искать одно и то же 100 раз
def get_german_synonyms(word):
    """
    Ищет синонимы через OpenThesaurus API.
    Возвращает строку с топ-3 синонимами.
    """
    url = f"https://www.openthesaurus.de/synonyme/search?q={word}&format=json"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        
        synonyms = []
        # Разбираем ответ API
        for synset in data.get('synsets', []):
            for term in synset.get('terms', []):
                term_word = term.get('term')
                # Не добавляем само слово и слишком длинные фразы
                if term_word.lower() != word.lower() and len(term_word.split()) < 3:
                    synonyms.append(term_word)
        
        # Берем только уникальные и первые 3-4 штуки
        unique_synonyms = list(dict.fromkeys(synonyms))
        return ", ".join(unique_synonyms[:4])
        
    except Exception:
        return ""

def extract_text_with_fallback(file_bytes, file_type):
    """Читает текст из PDF или Картинок (включая OCR)"""
    text = ""
    # 1. Быстрое чтение PDF
    if file_type == "application/pdf":
        try:
            with pdfplumber.open(file_bytes) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted: text += extracted + "\n"
        except: pass

    # 2. Если текста мало — включаем OCR (для сканов)
    if len(text) < 50:
        st.info("🔎 Это скан. Включаю глубокое сканирование (OCR)...")
        if file_type == "application/pdf":
            images = convert_from_bytes(file_bytes.read())
            progress_bar = st.progress(0)
            for i, image in enumerate(images):
                text += pytesseract.image_to_string(image, lang='deu') + "\n"
                progress_bar.progress((i + 1) / len(images))
        else:
            image = Image.open(file_bytes)
            text = pytesseract.image_to_string(image, lang='deu')
    return text

def clean_and_count(text, min_len):
    """Фильтрация слов"""
    text = re.sub(r'[^a-zA-ZäöüÄÖÜß\s]', '', text) # Оставляем только буквы
    words = text.split()
    filtered = []
    for word in words:
        w_lower = word.lower()
        if len(w_lower) >= min_len and w_lower not in STOP_WORDS and not w_lower.isdigit():
            # Сохраняем слово с Заглавной буквы, если это существительное (простая эвристика)
            if word[0].isupper():
                filtered.append(word)
            else:
                filtered.append(w_lower)
    return Counter(filtered).most_common()

# --- 3. Интерфейс ---

with st.sidebar:
    st.header("⚙️ Настройки")
    min_len = st.slider("Мин. длина слова", 3, 12, 5)
    max_words = st.slider("Сколько слов анализировать", 10, 50, 20)

st.write("### 🚀 Загрузи тест, и я создам таблицу с синонимами")
uploaded_file = st.file_uploader("Загрузить файл (PDF/JPG)", type=['pdf', 'png', 'jpg', 'jpeg'])

if uploaded_file:
    text_content = ""
    with st.spinner('Читаю текст...'):
        try:
            if uploaded_file.type == "application/pdf":
                text_content = extract_text_with_fallback(uploaded_file, "application/pdf")
            else:
                text_content = extract_text_with_fallback(uploaded_file, uploaded_file.type)
        except Exception as e:
            st.error(f"Ошибка: {e}")

    if text_content and len(text_content) > 10:
        # 1. Считаем слова
        all_words_data = clean_and_count(text_content, min_len)
        
        # Берем только топ N слов, чтобы не ждать вечность
        top_words = all_words_data[:max_words]
        
        st.success(f"Найдено слов: {len(all_words_data)}. Анализируем топ-{max_words}...")
        
        # 2. Ищем синонимы (с прогресс-баром)
        table_data = []
        synonym_bar = st.progress(0)
        
        for i, (word, count) in enumerate(top_words):
            syns = get_german_synonyms(word)
            table_data.append({
                "Слово": word,
                "Синонимы (для B2)": syns if syns else "—",
                "Частота": count,
                "Выучить": False
            })
            synonym_bar.progress((i + 1) / len(top_words))
            
        # 3. Вывод таблицы
        st.markdown("### 📚 Твой словарь для этого урока")
        st.data_editor(
            table_data,
            column_config={
                "Выучить": st.column_config.CheckboxColumn("В словарь", default=False),
                "Синонимы (для B2)": st.column_config.TextColumn("Синонимы", help="Используй эти слова, чтобы разнообразить речь"),
                "Частота": st.column_config.NumberColumn("Повторов")
            },
            height=600,
            use_container_width=True,
            hide_index=True
        )
        
    else:
        st.warning("Не удалось прочитать текст. Попробуй файл лучшего качества.")
