import streamlit as st
import re
from collections import Counter
from PIL import Image
import pytesseract
import pdfplumber
from pdf2image import convert_from_bytes
import requests
from deep_translator import GoogleTranslator

# --- 1. Настройки ---
st.set_page_config(page_title="Немецкий B2 Pro", layout="wide")
st.title("🇩🇪 Немецкий B2: Полный разбор")

# Расширенный список стоп-слов (убираем мусор с титульных листов)
STOP_WORDS = {
    "der", "die", "das", "und", "ist", "in", "zu", "den", "dem", "des", 
    "mit", "auf", "für", "von", "ein", "eine", "einen", "sich", "aus",
    "dass", "nicht", "war", "aber", "man", "bei", "wie", "wir", "oder",
    "kann", "sind", "werden", "wird", "auch", "noch", "nur", "vor", "nach",
    "über", "wenn", "zum", "zur", "habe", "hat", "durch", "unter", "diese",
    "telc", "deutsch", "prüfung", "test", "seite", "page", "express", "hueber",
    "aufgabe", "lösung", "antwortbogen", "teil", "kapitel", "übung", "verlag",
    "auflage", "gmbh", "druck", "isbn", "münchen", "klett", "cornelsen"
}

# --- 2. Функции ---

@st.cache_data
def get_translation(word):
    """Перевод на русский через Google"""
    try:
        return GoogleTranslator(source='de', target='ru').translate(word)
    except:
        return "-"

@st.cache_data
def get_synonyms(word):
    """Синонимы через OpenThesaurus"""
    url = f"https://www.openthesaurus.de/synonyme/search?q={word}&format=json"
    try:
        response = requests.get(url, timeout=2)
        data = response.json()
        synonyms = []
        for synset in data.get('synsets', []):
            for term in synset.get('terms', []):
                term_word = term.get('term')
                if term_word.lower() != word.lower() and len(term_word.split()) < 3:
                    synonyms.append(term_word)
        unique_synonyms = list(dict.fromkeys(synonyms))
        return ", ".join(unique_synonyms[:3]) # Берем топ-3
    except:
        return ""

def find_context_sentence(text, word):
    """Ищет предложение, в котором встретилось слово"""
    sentences = re.split(r'(?<=[.!?]) +', text)
    for sent in sentences:
        if word in sent:
            # Очищаем от лишних пробелов и переносов строк
            clean_sent = sent.replace("\n", " ").strip()
            # Обрезаем, если предложение слишком длинное
            if len(clean_sent) > 150:
                return clean_sent[:150] + "..."
            return clean_sent
    return "-"

def extract_text_advanced(file_bytes, file_type, start_page, num_pages):
    """
    Читает N страниц, начиная со start_page.
    """
    text = ""
    error = None

    # Поправка: для пользователя стр 1, для питона стр 0
    start_idx = start_page - 1 

    # 1. Пробуем PDFPlumber (текст)
    if file_type == "application/pdf":
        try:
            with pdfplumber.open(file_bytes) as pdf:
                # Берем срез страниц
                pages_to_read = pdf.pages[start_idx : start_idx + num_pages]
                for page in pages_to_read:
                    extracted = page.extract_text()
                    if extracted: text += extracted + "\n"
        except Exception:
            pass

    # 2. Если текста нет -> OCR
    if len(text) < 50:
        if file_type == "application/pdf":
            st.warning(f"📄 Сканирую страницы {start_page}-{start_page + num_pages - 1} через OCR...")
            try:
                file_bytes.seek(0)
                images = convert_from_bytes(
                    file_bytes.read(), 
                    first_page=start_page, 
                    last_page=start_page + num_pages - 1
                )
                
                bar = st.progress(0)
                for i, img in enumerate(images):
                    text += pytesseract.image_to_string(img, lang='deu') + "\n"
                    bar.progress((i + 1) / len(images))
            except Exception as e:
                error = str(e)
        else:
            # Картинка
            img = Image.open(file_bytes)
            text = pytesseract.image_to_string(img, lang='deu')

    return text, error

def get_top_words(text, min_len):
    # Очистка
    clean_text = re.sub(r'[^a-zA-ZäöüÄÖÜß\s]', '', text)
    words = clean_text.split()
    filtered = []
    
    for word in words:
        w_lower = word.lower()
        if len(w_lower) >= min_len and w_lower not in STOP_WORDS and not w_lower.isdigit():
            # Оставляем оригинальный регистр, если слово чаще с большой буквы
            filtered.append(word)
            
    return Counter(filtered).most_common()

# --- 3. Интерфейс ---

with st.sidebar:
    st.header("⚙️ Настройки анализа")
    # ВАЖНО: Выбор страницы начала
    start_page = st.number_input("Начать со страницы №", min_value=1, value=5, help="Пропусти первые страницы (обложку), ставь сразу 5 или 10")
    pages_limit = st.slider("Сколько страниц читать", 1, 5, 2)
    max_words_count = st.slider("Сколько слов учить", 5, 30, 15)

st.write("### 🇩🇪 Загрузи учебник")
st.info("💡 Совет: В настройках слева поставь 'Начать со страницы 5' или '10', чтобы пропустить титульный лист.")

uploaded_file = st.file_uploader("Файл (PDF)", type=['pdf', 'jpg'])

if uploaded_file:
    # Кнопка запуска, чтобы не пересчитывать при смене настроек
    if st.button("🚀 Анализировать"):
        with st.spinner('Читаю, перевожу и ищу синонимы...'):
            text_content, err = extract_text_advanced(uploaded_file, uploaded_file.type, start_page, pages_limit)
            
            if err:
                st.error("Ошибка чтения. Попробуй пересохранить PDF.")
            elif len(text_content) < 10:
                st.warning("Текст не найден. Проверь номера страниц.")
            else:
                # 1. Анализ слов
                words_freq = get_top_words(text_content, 4) # мин длина 4
                top_words = words_freq[:max_words_count]
                
                # 2. Сбор данных (Перевод + Синонимы + Контекст)
                table_data = []
                progress = st.progress(0)
                
                for i, (word, count) in enumerate(top_words):
                    translation = get_translation(word)
                    syns = get_synonyms(word)
                    context = find_context_sentence(text_content, word)
                    
                    table_data.append({
                        "Слово": word,
                        "Перевод 🇷🇺": translation,
                        "Синонимы (DE)": syns if syns else "—",
                        "Контекст (фраза)": context,
                        "Выучить": False
                    })
                    progress.progress((i + 1) / len(top_words))
                
                st.success(f"Готово! Обработаны страницы {start_page}-{start_page+pages_limit-1}")
                
                st.data_editor(
                    table_data,
                    column_config={
                        "Выучить": st.column_config.CheckboxColumn("✅", default=False),
                        "Контекст (фраза)": st.column_config.TextColumn("Где встретилось", width="large"),
                    },
                    height=800,
                    hide_index=True
                )
