import streamlit as st
import re
from collections import Counter
from PIL import Image
import pytesseract
import pdfplumber
from pdf2image import convert_from_bytes # Библиотека для превращения PDF в картинки

# --- 1. Настройки ---
st.set_page_config(page_title="Немецкий B2 Pro", layout="wide")
st.title("🇩🇪 Немецкий B2: Анализатор тестов (OCR v3)")

STOP_WORDS = {
    "der", "die", "das", "und", "ist", "in", "zu", "den", "dem", "des", 
    "mit", "auf", "für", "von", "ein", "eine", "einen", "sich", "aus",
    "dass", "nicht", "war", "aber", "man", "bei", "wie", "wir", "oder",
    "kann", "sind", "werden", "wird", "auch", "noch", "nur", "vor", "nach",
    "über", "wenn", "zum", "zur", "habe", "hat", "durch", "unter", "diese",
    "telc", "deutsch", "prüfung", "test", "seite", "page", "express", "hueber"
}

# --- 2. Функции ---

def extract_text_with_fallback(file_bytes, file_type):
    """
    Умная функция: сначала пробует быстрое чтение.
    Если не выходит — включает мощный OCR (медленно, но надежно).
    """
    text = ""
    
    # 1. Попытка быстрого чтения (для цифровых PDF)
    if file_type == "application/pdf":
        try:
            with pdfplumber.open(file_bytes) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
        except:
            pass # Если ошибка, идем дальше к OCR

    # 2. Если текста мало (меньше 50 символов), значит это СКАН. Включаем OCR.
    if len(text) < 50:
        st.info("📄 Это скан. Включаю оптическое распознавание (это займет чуть больше времени)...")
        
        if file_type == "application/pdf":
            # Превращаем PDF в картинки
            images = convert_from_bytes(file_bytes.read())
            progress_bar = st.progress(0)
            
            for i, image in enumerate(images):
                # Распознаем каждую страницу
                text += pytesseract.image_to_string(image, lang='deu') + "\n"
                progress_bar.progress((i + 1) / len(images))
                
        else:
            # Это просто картинка (JPG/PNG)
            image = Image.open(file_bytes)
            text = pytesseract.image_to_string(image, lang='deu')

    return text

def clean_and_count(text, min_len):
    """Фильтрация и подсчет слов"""
    # Оставляем буквы и умлауты
    text = re.sub(r'[^a-zA-ZäöüÄÖÜß\s]', '', text)
    words = text.split()
    
    filtered = []
    for word in words:
        w_lower = word.lower()
        if len(w_lower) >= min_len and w_lower not in STOP_WORDS and not w_lower.isdigit():
            filtered.append(word)
            
    return Counter(filtered).most_common()

# --- 3. Интерфейс ---

with st.sidebar:
    st.header("⚙️ Настройки")
    min_len = st.slider("Мин. длина слова", 3, 12, 4)

st.write("Загрузи PDF учебника или фото страницы.")
uploaded_file = st.file_uploader("Файл", type=['pdf', 'png', 'jpg', 'jpeg'])

if uploaded_file:
    text_content = ""
    
    with st.spinner('Анализирую документ...'):
        try:
            # Передаем файл в функцию
            if uploaded_file.type == "application/pdf":
                # Для PDF нам нужен сам объект файла, поэтому не читаем его сразу в байты тут
                text_content = extract_text_with_fallback(uploaded_file, "application/pdf")
            else:
                # Для картинок
                text_content = extract_text_with_fallback(uploaded_file, uploaded_file.type)
                
        except Exception as e:
            st.error(f"Произошла ошибка: {e}")
            st.error("Попробуй обновить страницу и загрузить файл снова.")

    # Если текст найден
    if text_content and len(text_content) > 10:
        
        words_data = clean_and_count(text_content, min_len)
        
        st.success(f"Успех! Прочитано слов: {len(text_content.split())}. Найдено полезных: {len(words_data)}")
        
        # Данные для таблицы
        table_data = []
        for word, count in words_data:
            table_data.append({
                "Слово": word,
                "Частота": count,
                "Выучить": False
            })
            
        st.data_editor(
            table_data,
            column_config={
                "Выучить": st.column_config.CheckboxColumn(
                    "В словарь",
                    default=False
                ),
                "Частота": st.column_config.NumberColumn(
                    "Повторов",
                    help="Как часто слово встречается в тесте"
                )
            },
            height=600,
            use_container_width=True,
            hide_index=True
        )
        
        with st.expander("Показать 'сырой' текст (для проверки)"):
            st.text(text_content[:1000] + "...")
            
    else:
        if uploaded_file:
            st.warning("⚠️ Текст все еще не найден. Возможно, качество скана слишком низкое.")
