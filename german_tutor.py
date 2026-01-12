import streamlit as st
import re
from collections import Counter
from PIL import Image
import pytesseract
import pdfplumber
from pdf2image import convert_from_bytes
import requests

# --- 1. Настройки ---
st.set_page_config(page_title="Немецкий B2 Trainer", layout="wide")
st.title("🇩🇪 Немецкий B2: Словарь + Синонимы")

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

@st.cache_data
def get_german_synonyms(word):
    """Ищет синонимы через OpenThesaurus API"""
    url = f"https://www.openthesaurus.de/synonyme/search?q={word}&format=json"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        synonyms = []
        for synset in data.get('synsets', []):
            for term in synset.get('terms', []):
                term_word = term.get('term')
                if term_word.lower() != word.lower() and len(term_word.split()) < 3:
                    synonyms.append(term_word)
        unique_synonyms = list(dict.fromkeys(synonyms))
        return ", ".join(unique_synonyms[:4])
    except Exception:
        return ""

def extract_text_with_fallback(file_bytes, file_type):
    """Читает текст. Обрабатывает битые PDF."""
    text = ""
    error_message = None

    # 1. Быстрое чтение PDF (текстовый слой)
    if file_type == "application/pdf":
        try:
            with pdfplumber.open(file_bytes) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted: text += extracted + "\n"
        except Exception:
            pass # Игнорируем ошибки тут, попробуем OCR

    # 2. Если текста мало — включаем OCR
    if len(text) < 50:
        if file_type == "application/pdf":
            st.info("🔎 Это скан или сложный PDF. Включаю OCR (это может занять время)...")
            try:
                # ВАЖНО: Читаем байты заново, так как pdfplumber мог сдвинуть курсор
                file_bytes.seek(0)
                images = convert_from_bytes(file_bytes.read())
                
                progress_bar = st.progress(0)
                for i, image in enumerate(images):
                    text += pytesseract.image_to_string(image, lang='deu') + "\n"
                    progress_bar.progress((i + 1) / len(images))
            except Exception as e:
                # Ловим ошибку битого PDF
                error_message = f"CRITICAL_PDF_ERROR: {str(e)}"
        else:
            # Картинка
            try:
                image = Image.open(file_bytes)
                text = pytesseract.image_to_string(image, lang='deu')
            except Exception as e:
                error_message = str(e)

    if error_message:
        return f"ERROR: {error_message}"
        
    return text

def clean_and_count(text, min_len):
    """Фильтрация слов"""
    text = re.sub(r'[^a-zA-ZäöüÄÖÜß\s]', '', text)
    words = text.split()
    filtered = []
    for word in words:
        w_lower = word.lower()
        if len(w_lower) >= min_len and w_lower not in STOP_WORDS and not w_lower.isdigit():
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

st.write("### 🚀 Загрузи тест (PDF/JPG)")
st.info("💡 Если вылетает ошибка 'Syntax Error' — открой PDF в браузере и нажми 'Печать' -> 'Сохранить как PDF'. Это исправит файл.")

uploaded_file = st.file_uploader("Загрузить файл", type=['pdf', 'png', 'jpg', 'jpeg'])

if uploaded_file:
    text_content = ""
    
    with st.spinner('Обработка...'):
        if uploaded_file.type == "application/pdf":
            text_content = extract_text_with_fallback(uploaded_file, "application/pdf")
        else:
            text_content = extract_text_with_fallback(uploaded_file, uploaded_file.type)

    # Проверяем на критическую ошибку
    if text_content.startswith("ERROR:"):
        st.error("❌ Ошибка чтения файла.")
        st.warning("Файл поврежден (сломана внутренняя структура XRef).")
        st.markdown("**Как исправить:**\n1. Открой этот PDF на компьютере (в Chrome или Adobe).\n2. Нажми **Печать** -> Выбери принтер **'Сохранить как PDF'**.\n3. Загрузи новый файл сюда.")
        with st.expander("Технические детали ошибки"):
            st.code(text_content)
            
    elif text_content and len(text_content) > 10:
        all_words_data = clean_and_count(text_content, min_len)
        top_words = all_words_data[:max_words]
        
        st.success(f"Найдено слов: {len(all_words_data)}. Подбираю синонимы к топ-{max_words}...")
        
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
            
        st.markdown("### 📚 Словарь для урока")
        st.data_editor(
            table_data,
            column_config={
                "Выучить": st.column_config.CheckboxColumn("В словарь", default=False),
                "Синонимы (для B2)": st.column_config.TextColumn("Синонимы"),
                "Частота": st.column_config.NumberColumn("Повторов")
            },
            height=600,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("Текст не найден или файл пуст.")
