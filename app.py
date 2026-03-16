import io
from flask import Flask, render_template, request, redirect, url_for, session, send_file
from models import save_response, get_all_responses
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = 'supersecretkey'
ADMIN_PASSWORD = 'admin123'

EMPLOYEES_FILE = 'employees.xlsx'

def load_employees():
    if os.path.exists(EMPLOYEES_FILE):
        df = pd.read_excel(EMPLOYEES_FILE, engine='openpyxl')
        if 'Name' in df.columns:
            employees = df['Name'].dropna().astype(str).str.strip().tolist()
            return employees
    return ["Иванов Иван Иванович", "Петров Петр Петрович", "Сидорова Анна Сергеевна"]

EMPLOYEES_LIST = load_employees()

def get_survey_progress():
    employees = load_employees()
    responses = get_all_responses()
    responded_names = set(responses['Name'].dropna().astype(str).str.strip().tolist())
    total = len(employees)
    responded_count = sum(1 for name in employees if name in responded_names)
    not_responded_count = total - responded_count
    percent = round((responded_count / total * 100) if total > 0 else 0, 1)
    responded_list = [name for name in employees if name in responded_names]
    not_responded_list = [name for name in employees if name not in responded_names]
    return {
        'total': total,
        'responded_count': responded_count,
        'not_responded_count': not_responded_count,
        'percent': percent,
        'responded_list': responded_list,
        'not_responded_list': not_responded_list
    }

@app.route('/')
def index():
    return render_template('index.html', employees=EMPLOYEES_LIST)

@app.route('/submit_survey', methods=['POST'])
def submit_survey():
    name = request.form.get('name', '').strip()
    likes = request.form.get('likes', '').strip()
    dislikes = request.form.get('dislikes', '').strip()
    if not name or not likes or not dislikes:
        return "Ошибка: все поля должны быть заполнены", 400
    save_response(name, likes, dislikes)
    return render_template('success.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_panel'))
        else:
            return render_template('admin_login.html', error='Неверный пароль')
    return render_template('admin_login.html', error=None)

@app.route('/admin/panel')
def admin_panel():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    progress = get_survey_progress()
    return render_template('admin_panel.html', progress=progress)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

@app.route('/export_excel')
def export_excel():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    df = get_all_responses()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Responses')
    output.seek(0)
    return send_file(output, download_name='survey_results.xlsx', as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004, debug=True)
