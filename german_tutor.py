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
        response = requests.get(url, timeout=3) # Тайм-аут 3 сек, чтобы не висело
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

def extract_text_safe(file_bytes, file_type, pages_to_scan):
    """
    Безопасное чтение. Если OCR — читаем только указанное количество страниц.
    """
    text = ""
    error_message = None

    # 1. Сначала пробуем вытащить текст без OCR (это быстро и не ест память)
    if file_type == "application/pdf":
        try:
            with pdfplumber.open(file_bytes) as pdf:
                # Читаем только первые N страниц или все, если текст цифровой
                for i, page in enumerate(pdf.pages):
                    if i >= pages_to_scan: break 
                    extracted = page.extract_text()
                    if extracted: text += extracted + "\n"
        except Exception:
            pass 

    # 2. Если текста нет (< 50 символов), значит это СКАН. Включаем OCR с лимитом.
    if len(text) < 50:
        if file_type == "application/pdf":
            st.warning(f"📄 Это скан. Распознаю первые {pages_to_scan} стр., чтобы сберечь память...")
            try:
                # ВАЖНО: seek(0) возвращает курсор в начало файла
                file_bytes.seek(0)
                
                # Конвертируем ТОЛЬКО нужные страницы (first_page, last_page)
                # Это спасет сервер от падения!
                images = convert_from_bytes(
                    file_bytes.read(), 
                    first_page=1, 
                    last_page=pages_to_scan
                )
                
                progress_bar = st.progress(0)
                for i, image in enumerate(images):
                    text += pytesseract.image_to_string(image, lang='deu') + "\n"
                    progress_bar.progress((i + 1) / len(images))
                    
            except Exception as e:
                error_message = f"Ошибка PDF: {str(e)}"
        else:
            # Обычная картинка
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
    max_words = st.slider("Сколько слов брать в словарь", 10, 50, 20)
    # НОВАЯ НАСТРОЙКА: Лимит страниц
    pages_limit = st.slider("Сколько страниц сканировать (OCR)", 1, 10, 3, help="Если файл большой, ставь меньше 5, иначе сервер зависнет!")

st.write("### 🚀 Загрузи тест (PDF/JPG)")
st.info("💡 Совет: Для больших книг (PDF > 5 МБ) выбирай в настройках слева сканирование 3-5 страниц за раз.")

uploaded_file = st.file_uploader("Загрузить файл", type=['pdf', 'png', 'jpg', 'jpeg'])

if uploaded_file:
    text_content = ""
    
    with st.spinner('Обработка...'):
        if uploaded_file.type == "application/pdf":
            text_content = extract_text_safe(uploaded_file, "application/pdf", pages_limit)
        else:
            text_content = extract_text_safe(uploaded_file, uploaded_file.type, 1)

    if text_content.startswith("ERROR:"):
        st.error("❌ Ошибка чтения файла.")
        st.warning("Файл поврежден или слишком тяжелый.")
        st.code(text_content)
        st.markdown("**Решение:** Попробуй 'распечатать' этот PDF в новый файл через 'Сохранить как PDF' на компьютере.")
            
    elif text_content and len(text_content) > 10:
        all_words_data = clean_and_count(text_content, min_len)
        top_words = all_words_data[:max_words]
        
        st.success(f"Прочитано. Найдено слов: {len(all_words_data)}. Ищу синонимы...")
        
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
            
        st.markdown("### 📚 Словарь")
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
        st.warning("Текст не найден. Если это PDF, убедитесь, что он не пустой.")
