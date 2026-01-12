import streamlit as st
import re
from collections import Counter
from PIL import Image
import pytesseract
import pdfplumber
from pdf2image import convert_from_bytes
import requests
from deep_translator import GoogleTranslator
from wordfreq import zipf_frequency

# --- 1. Настройки ---
st.set_page_config(page_title="DE Tutor Pro", layout="wide")
st.title("🇩🇪 Немецкий B2: Умный словарь + Синонимы")

STOP_WORDS = {
    "der", "die", "das", "und", "ist", "in", "zu", "den", "dem", "des", 
    "mit", "auf", "für", "von", "ein", "eine", "einen", "sich", "aus",
    "dass", "nicht", "war", "aber", "man", "bei", "wie", "wir", "oder",
    "kann", "sind", "werden", "wird", "auch", "noch", "nur", "vor", "nach",
    "über", "wenn", "zum", "zur", "habe", "hat", "durch", "unter", "diese",
    "dieser", "ihre", "seine", "meine", "vom", "am", "im", "um", "als",
    "es", "sie", "er", "du", "ich", "mich", "mir", "dir", "uns", "ihnen",
    "diesen", "demnach", "dabei", "damit", "dafür",
    "telc", "deutsch", "prüfung", "test", "seite", "page", "express", "hueber",
    "aufgabe", "lösung", "antwortbogen", "teil", "kapitel", "übung", "verlag",
    "auflage", "gmbh", "druck", "isbn", "münchen", "klett", "cornelsen",
    "minuten", "punkte", "lesen", "hören", "schreiben", "sprechen",
    "text", "texte", "überschrift", "überschriften", "modelltest",
    "tipps", "tricks", "informationen", "antworten", "ankreuzen", "markieren",
    "richtig", "falsch", "insgesamt", "zeit", "beispiel", "nummer", "email"
}

# --- 2. Функции ---

@st.cache_data
def estimate_level(word):
    """Определяет уровень (A1-C2)"""
    try:
        freq = zipf_frequency(word, 'de')
        if freq == 0: return "—"
        if freq > 5.5: return "A1"
        if freq > 4.5: return "A2"
        if freq > 3.8: return "B1" # Чуть снизил порог для B1
        if freq > 3.0: return "B2"
        return "C1"
    except:
        return "?"

@st.cache_data
def get_translation(word):
    try:
        return GoogleTranslator(source='de', target='ru').translate(word)
    except:
        return "-"

@st.cache_data
def get_synonyms(word):
    """
    Агрессивный поиск синонимов.
    Пробует разные варианты слова (убирает окончания), пока не найдет ответ.
    """
    
    def fetch_api(query):
        # Запрос к OpenThesaurus
        url = f"https://www.openthesaurus.de/synonyme/search?q={query}&format=json"
        try:
            r = requests.get(url, timeout=1)
            if r.status_code == 200:
                data = r.json()
                found = []
                for synset in data.get('synsets', []):
                    for term in synset.get('terms', []):
                        t = term.get('term')
                        # Чистим от мусора (убираем скобки и фразы)
                        t_clean = re.sub(r"\(.*?\)", "", t).strip()
                        if t_clean.lower() != query.lower() and len(t_clean.split()) < 3:
                            found.append(t_clean)
                return list(dict.fromkeys(found))
        except:
            return []
        return []

    # 1. Пробуем слово как есть
    syns = fetch_api(word)
    
    # 2. Если пусто, пробуем отрезать окончания (превращаем Plural в Singular)
    if not syns and len(word) > 4:
        # Mahlzeiten -> Mahlzeit
        if word.endswith("en"): syns = fetch_api(word[:-2])
        # Autos -> Auto
        elif word.endswith("s"): syns = fetch_api(word[:-1])
        # Schule -> Schul (иногда помогает)
        elif word.endswith("e"): syns = fetch_api(word[:-1])
        # Lehrern -> Lehrer
        elif word.endswith("n"): syns = fetch_api(word[:-1])

    if syns:
        # Возвращаем топ-4 синонима
        return ", ".join(syns[:4])
    
    return "—" # Если совсем ничего не нашли

def find_context(text, word):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    for sent in sentences:
        if re.search(r'\b' + re.escape(word) + r'\b', sent, re.IGNORECASE):
            clean = sent.replace("\n", " ").strip()
            return clean[:120] + "..." if len(clean) > 120 else clean
    return "—"

def extract_text(file_bytes, file_type, start, limit):
    text = ""
    start_idx = start - 1
    
    # PDF текст
    if file_type == "application/pdf":
        try:
            with pdfplumber.open(file_bytes) as pdf:
                if start_idx < len(pdf.pages):
                    pages = pdf.pages[start_idx : start_idx + limit]
                    for p in pages:
                        t = p.extract_text()
                        if t: text += t + "\n"
        except: pass

    # OCR
    if len(text) < 50:
        if file_type == "application/pdf":
            st.info(f"🔎 Включаю OCR для страниц {start}-{start+limit-1}...")
            try:
                file_bytes.seek(0)
                images = convert_from_bytes(file_bytes.read(), first_page=start, last_page=start+limit-1)
                for img in images:
                    text += pytesseract.image_to_string(img, lang='deu') + "\n"
            except: pass
        else:
            img = Image.open(file_bytes)
            text = pytesseract.image_to_string(img, lang='deu')
            
    return text

def process_text(text, min_len):
    clean_text = re.sub(r'[^a-zA-ZäöüÄÖÜß\s]', '', text)
    words = clean_text.split()
    filtered = []
    for w in words:
        w_clean = w.strip()
        if len(w_clean) >= min_len and w_clean.lower() not in STOP_WORDS and not w_clean.isdigit():
            filtered.append(w_clean)
    return Counter(filtered).most_common()

# --- 3. Интерфейс ---

with st.sidebar:
    st.header("Настройки")
    # Твой файл начинается с рекламы, тексты идут позже.
    # Для теста про еду ставь 15. Для текста про Resilienz ставь 54.
    start_page = st.number_input("Начать со стр.", 1, 200, 54, help="Страница учебника")
    pages_to_read = st.slider("Читать страниц", 1, 3, 1)
    max_words = st.slider("Количество слов", 10, 40, 15)

st.write("### 🇩🇪 B2 Trainer: Слова + Перевод + Синонимы")

uploaded_file = st.file_uploader("Файл", type=['pdf', 'jpg', 'png'])

if uploaded_file and st.button("🚀 Начать тренировку"):
    with st.spinner("Работаем: читаю, перевожу, ищу синонимы в словаре..."):
        full_text = extract_text(uploaded_file, uploaded_file.type, start_page, pages_to_read)
        
        if len(full_text) < 10:
            st.error("Текст не найден. Возможно пустая страница.")
        else:
            # Анализ
            freq_list = process_text(full_text, 4) # мин длина слова 4 буквы
            top_words = freq_list[:max_words]
            
            table_data = []
            bar = st.progress(0)
            
            for i, (word, count) in enumerate(top_words):
                lvl = estimate_level(word)
                trans = get_translation(word)
                syns = get_synonyms(word) # Тут теперь работает "Агрессивный поиск"
                ctx = find_context(full_text, word)
                
                table_data.append({
                    "Уровень": lvl,
                    "Слово": word,
                    "Перевод (RU)": trans,
                    "Синонимы (B2)": syns,
                    "Контекст": ctx,
                    "Выучить": False
                })
                bar.progress((i+1)/len(top_words))
            
            st.success(f"Готово! Словарь обновлен.")
            
            st.data_editor(
                table_data,
                column_config={
                    "Уровень": st.column_config.TextColumn("Lvl", width="small"),
                    "Синонимы (B2)": st.column_config.TextColumn("Синонимы (B2)", width="large", help="Слова для замены на экзамене"),
                    "Выучить": st.column_config.CheckboxColumn("✅")
                },
                height=800,
                hide_index=True
            )
