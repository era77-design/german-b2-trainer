import streamlit as st
import re
from collections import Counter
from PIL import Image
import pytesseract
import pdfplumber

# --- 1. Настройки ---
st.set_page_config(page_title="Немецкий B2 Pro", layout="wide")
st.title("🇩🇪 Немецкий B2: Анализатор тестов")

# Стоп-слова (простые слова, которые нам не нужны)
STOP_WORDS = {
    "der", "die", "das", "und", "ist", "in", "zu", "den", "dem", "des", 
    "mit", "auf", "für", "von", "ein", "eine", "einen", "sich", "aus",
    "dass", "nicht", "war", "aber", "man", "bei", "wie", "wir", "oder",
    "kann", "sind", "werden", "wird", "auch", "noch", "nur", "vor", "nach",
    "über", "wenn", "zum", "zur", "habe", "hat", "durch", "unter", "diese"
}

# --- 2. Функции ---

def extract_text_from_pdf(pdf_file):
    """Надежное чтение PDF"""
    full_text = ""
    with pdfplumber.open(pdf_file) as pdf:
        # Показываем прогресс бар
        progress_bar = st.progress(0)
        total_pages = len(pdf.pages)
        
        for i, page in enumerate(pdf.pages):
            extracted = page.extract_text()
            if extracted:  # Проверяем, что текст есть
                full_text += extracted + "\n"
            # Обновляем прогресс
            progress_bar.progress((i + 1) / total_pages)
            
    return full_text

def extract_text_from_image(image, lang):
    """Чтение с картинки (Tesseract)"""
    try:
        return pytesseract.image_to_string(image, lang=lang)
    except Exception as e:
        return f"Error: {e}"

def clean_and_count(text, min_len):
    """Фильтрация слов"""
    # Оставляем буквы и умлауты
    text = re.sub(r'[^a-zA-ZäöüÄÖÜß\s]', '', text)
    words = text.split()
    
    filtered = []
    for word in words:
        w_lower = word.lower()
        # Фильтр: длина, не стоп-слово, не число
        if len(w_lower) >= min_len and w_lower not in STOP_WORDS and not w_lower.isdigit():
            filtered.append(word) # Берем оригинальное слово (с Большой буквы)
            
    # Считаем частоту
    return Counter(filtered).most_common()

# --- 3. Интерфейс ---

with st.sidebar:
    st.header("⚙️ Настройки")
    min_len = st.slider("Мин. длина слова", 3, 12, 5)
    lang_option = st.selectbox("Язык (для фото)", ["deu", "eng"])

st.write("Загрузи PDF учебника или фото страницы.")
uploaded_file = st.file_uploader("Файл", type=['pdf', 'png', 'jpg', 'jpeg'])

if uploaded_file:
    text_content = ""
    
    with st.spinner('Читаю файл...'):
        try:
            if uploaded_file.type == "application/pdf":
                text_content = extract_text_from_pdf(uploaded_file)
            else:
                image = Image.open(uploaded_file)
                st.image(image, width=300)
                text_content = extract_text_from_image(image, lang_option)
        except Exception as e:
            st.error(f"Ошибка чтения файла: {e}")

    # Если текст найден
    if text_content:
        # Показать кусочек текста для проверки
        with st.expander("Показать найденный текст (первые 500 символов)"):
            st.text(text_content[:500] + "...")

        # Анализ
        words_data = clean_and_count(text_content, min_len)
        
        st.success(f"Готово! Найдено уникальных слов: {len(words_data)}")
        
        # Формируем таблицу
        table_data = []
        for word, count in words_data:
            table_data.append({
                "Слово (DE)": word,
                "Частота": count,
                "Перевод": "", # Сюда потом подключим Google Translate
                "Учить": False
            })
            
        # Вывод интерактивной таблицы
        st.data_editor(
            table_data,
            column_config={
                "Учить": st.column_config.CheckboxColumn(
                    "В словарь",
                    default=False
                ),
                "Частота": st.column_config.NumberColumn(
                    "Сколько раз в тексте"
                )
            },
            height=600,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("⚠️ Текст не найден. Возможно, это скан (картинка внутри PDF). Попробуй сделать скриншот страницы и загрузить как JPG.")
