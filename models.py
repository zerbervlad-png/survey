# ==============================================
# МОДЕЛЬ ДАННЫХ: СОХРАНЕНИЕ И ЗАГРУЗКА ОТВЕТОВ
# ==============================================

import pandas as pd
import os
from datetime import datetime

# Имя файла Excel, где будут храниться все ответы
EXCEL_FILE = 'survey_responses.xlsx'

def save_response(user_name, likes, dislikes):
    """
    Сохраняет один ответ сотрудника в Excel-файл.
    Если файл не существует, создаёт его с заголовками.
    Если существует, добавляет новую строку.
    """
    # Формируем словарь с данными для новой записи
    data = {
        'Timestamp': [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        'Name': [user_name],
        'Likes': [likes],
        'Dislikes': [dislikes]
    }
    df_new = pd.DataFrame(data)

    # Проверяем, существует ли уже файл
    if os.path.exists(EXCEL_FILE):
        # Читаем существующие данные и добавляем новую строку
        df_existing = pd.read_excel(EXCEL_FILE, engine='openpyxl')
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        df_combined.to_excel(EXCEL_FILE, index=False, engine='openpyxl')
    else:
        # Создаём новый файл с первой записью
        df_new.to_excel(EXCEL_FILE, index=False, engine='openpyxl')

def get_all_responses():
    """
    Возвращает все собранные ответы в виде pandas DataFrame.
    Если файла нет, возвращает пустой DataFrame с правильными колонками.
    """
    if os.path.exists(EXCEL_FILE):
        return pd.read_excel(EXCEL_FILE, engine='openpyxl')
    else:
        return pd.DataFrame(columns=['Timestamp', 'Name', 'Likes', 'Dislikes'])
