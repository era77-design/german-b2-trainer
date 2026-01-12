import streamlit as st
import re
from collections import Counter
from PIL import Image
import pytesseract # Библиотека для распознавания текста
import pdfplumber # Библиотека для чтения PDF

# --- 1. Настройка страницы ---
st.set_page_config(page_title="Немецкий B2 OCR", layout="wide")
st.title("🇩🇪 Немецкий B2: Из фото в словарь")

# --- 2. Боковая панель ---
with st.sidebar:
    st.header("Настройки")
    min_len = st.slider("Минимальная длина слова", 2, 10, 4)
    # Выбор языка для OCR (важно для умлаутов ä, ö, ü)
    lang_option = st.selectbox("Язык текста", ["deu", "eng"], index=0)

STOP_WORDS = {
    "der", "die", "das", "und", "ist", "in", "zu", "den", "dem", "des", 
    "mit", "auf", "für", "von", "ein", "eine", "einen", "sich", "aus",
    "dass", "nicht", "war", "aber", "man", "bei", "wie", "wir"
}

# --- 3. Функции обработки ---

def extract_text_from_image(image, lang):
    """Превращает картинку в текст с помощью Tesseract"""
    try:
        # Указываем язык 'deu' для немецкого
        text = pytesseract.image_to_string(image, lang=lang)
        return text
    except Exception as e:
        st.error(f"Ошибка OCR: {e}")
        return ""

def extract_text_from_pdf(pdf_file):
    """Вытаскивает текст из PDF"""
    text = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def clean_and_count(text):
    """Чистит текст и считает слова"""
    # Оставляем буквы и умлауты
    text = re.sub(r'[^a-zA-ZäöüÄÖÜß\s]', '', text)
    words = text.split()
    
    filtered = []
    for word in words:
        w_lower = word.lower()
        if len(w_lower) >= min_len and w_lower not in STOP_WORDS:
            filtered.append(word) # Сохраняем оригинальный регистр для существительных
            
    return Counter(filtered).most_common()

# --- 4. Интерфейс загрузки ---

st.write("Загрузи фото теста (JPG/PNG) или PDF-файл.")
uploaded_file = st.file_uploader("Перетащи файл сюда", type=['png', 'jpg', 'jpeg', 'pdf'])

extracted_text = ""

if uploaded_file is not None:
    # Определяем тип файла и извлекаем текст
    with st.spinner('Идет распознавание...'):
        if uploaded_file.type == "application/pdf":
            extracted_text = extract_text_from_pdf(uploaded_file)
        else:
            # Это картинка
            image = Image.open(uploaded_file)
            st.image(image, caption='Загруженное фото', width=300)
            extracted_text = extract_text_from_image(image, lang=lang_option)

    st.success("Текст распознан!")
    
    # Показываем распознанный текст (можно скрыть под спойлер)
    with st.expander("Показать "сырой" текст"):
        st.text(extracted_text)

    # --- 5. Анализ и Таблица ---
    if extracted_text:
        word_counts = clean_and_count(extracted_text)
        
        st.divider()
        st.subheader(f"Найдено слов для B2: {len(word_counts)}")
        
        data = []
        for word, count in word_counts:
            data.append({
                "Слово": word,
                "Встретилось раз": count,
                "Выучить": False
            })
            
        st.data_editor(
            data,
            column_config={
                "Выучить": st.column_config.CheckboxColumn(
                    "В словарь",
                    default=True
                )
            },
            hide_index=True
        )