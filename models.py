import pandas as pd
import os
from datetime import datetime

EXCEL_FILE = 'survey_responses.xlsx'

def save_response(user_name, likes, dislikes):
    data = {
        'Timestamp': [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        'Name': [user_name],
        'Likes': [likes],
        'Dislikes': [dislikes]
    }
    df_new = pd.DataFrame(data)

    if os.path.exists(EXCEL_FILE):
        df_existing = pd.read_excel(EXCEL_FILE, engine='openpyxl')
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        df_combined.to_excel(EXCEL_FILE, index=False, engine='openpyxl')
    else:
        df_new.to_excel(EXCEL_FILE, index=False, engine='openpyxl')

def get_all_responses():
    if os.path.exists(EXCEL_FILE):
        return pd.read_excel(EXCEL_FILE, engine='openpyxl')
    else:
        return pd.DataFrame(columns=['Timestamp', 'Name', 'Likes', 'Dislikes'])
