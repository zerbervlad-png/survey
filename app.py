import io
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, send_file
import pandas as pd
import os
from models import (
    init_db, create_survey, get_all_surveys, get_survey_details,
    save_response, employee_has_responded, is_survey_active, close_survey
)

app = Flask(__name__)
app.secret_key = 'supersecretkey'
ADMIN_PASSWORD = 'admin123'

init_db()

@app.route('/')
def index():
    surveys = get_all_surveys(only_active=True)
    return render_template('index.html', surveys=surveys)

@app.route('/survey/<int:survey_id>')
def survey_form(survey_id):
    if not is_survey_active(survey_id):
        return render_template('survey_closed.html')
    details = get_survey_details(survey_id)
    if not details:
        return "Опрос не найден", 404
    employees = sorted(details['employees'])
    responded_names = {r['name'] for r in details['responded_list']}
    available = [name for name in employees if name not in responded_names]
    return render_template('survey.html',
                           survey=details['survey'],
                           employees=available,
                           questions=details['questions'],
                           survey_id=survey_id)

@app.route('/submit_survey/<int:survey_id>', methods=['POST'])
def submit_survey(survey_id):
    if not is_survey_active(survey_id):
        return render_template('survey_closed.html')
    name = request.form.get('name', '').strip()
    if not name:
        return "Не выбрано имя", 400
    if employee_has_responded(survey_id, name):
        return "Вы уже проходили этот опрос", 400

    answers = {}
    # Обрабатываем множественные выборы (поля с именами, оканчивающимися на [])
    for key in request.form:
        if key.startswith('q_') and key.endswith('[]'):
            qid = key[2:-2]  # убираем 'q_' и '[]'
            try:
                qid = int(qid)
            except ValueError:
                continue
            values = request.form.getlist(key)
            answers[qid] = values
    # Обрабатываем одиночные выборы и текстовые поля
    for key, value in request.form.items():
        if key.startswith('q_') and not key.endswith('[]'):
            qid = key[2:]
            try:
                qid = int(qid)
            except ValueError:
                continue
            answers[qid] = value

    save_response(survey_id, name, answers)
    return render_template('success.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error='Неверный пароль')
    return render_template('admin_login.html', error=None)

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    surveys = get_all_surveys(only_active=False)
    return render_template('admin_dashboard.html', surveys=surveys)

@app.route('/admin/create_survey', methods=['GET', 'POST'])
def create_survey_route():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        start_date = request.form.get('start_date', '').strip()
        end_date = request.form.get('end_date', '').strip()
        if not title or not start_date or not end_date:
            return "Заполните все поля", 400
        file = request.files.get('employee_file')
        if not file:
            return "Файл не загружен", 400
        try:
            df = pd.read_excel(file, engine='openpyxl')
            if 'Name' not in df.columns:
                return "Файл должен содержать колонку 'Name'", 400
            names = df['Name'].dropna().astype(str).str.strip().tolist()
            if not names:
                return "Список сотрудников пуст", 400
        except Exception as e:
            return f"Ошибка обработки файла: {e}", 400

        questions_data = []
        i = 0
        while True:
            qtext = request.form.get(f'question_text_{i}')
            if qtext is None:
                break
            qtext = qtext.strip()
            qtype = request.form.get(f'question_type_{i}')
            if not qtext or not qtype:
                i += 1
                continue
            options = []
            if qtype in ('single', 'multiple'):
                opts = request.form.getlist(f'options_{i}[]')
                options = [o.strip() for o in opts if o.strip()]
            questions_data.append({
                'text': qtext,
                'type': qtype,
                'options': options
            })
            i += 1

        if not questions_data:
            return "Добавьте хотя бы один вопрос", 400

        survey_id = create_survey(title, start_date, end_date, names, questions_data)
        return redirect(url_for('survey_detail', survey_id=survey_id))

    return render_template('create_survey.html')

@app.route('/admin/survey/<int:survey_id>')
def survey_detail(survey_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    details = get_survey_details(survey_id)
    if not details:
        return "Опрос не найден", 404
    details['is_active'] = is_survey_active(survey_id)
    return render_template('survey_detail.html', details=details)

@app.route('/admin/close_survey/<int:survey_id>', methods=['POST'])
def close_survey_route(survey_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    close_survey(survey_id)
    return redirect(url_for('survey_detail', survey_id=survey_id))

@app.route('/admin/export/<int:survey_id>')
def export_survey(survey_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    details = get_survey_details(survey_id)
    if not details:
        return "Опрос не найден", 404
    import sqlite3
    conn = sqlite3.connect('survey.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    rows = c.execute('''
        SELECT e.name as employee, r.submitted_at, q.text as question, q.type, a.value
        FROM answers a
        JOIN questions q ON a.question_id = q.id
        JOIN responses r ON a.response_id = r.id
        JOIN employees e ON r.employee_id = e.id
        WHERE r.survey_id = ?
        ORDER BY r.submitted_at, e.name, q."order"
    ''', (survey_id,)).fetchall()
    conn.close()
    data = []
    for row in rows:
        data.append({
            'Сотрудник': row['employee'],
            'Дата': row['submitted_at'],
            'Вопрос': row['question'],
            'Ответ': row['value']
        })
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Детальные ответы')
        stats_data = []
        for qstat in details['question_stats']:
            q = qstat['question']
            if qstat['type'] in ('single', 'multiple'):
                for s in qstat['stats']:
                    stats_data.append({
                        'Вопрос': q['text'],
                        'Вариант': s['option'],
                        'Количество': s['count'],
                        'Процент': s['percent']
                    })
        df_stats = pd.DataFrame(stats_data)
        if not df_stats.empty:
            df_stats.to_excel(writer, sheet_name='Статистика по вариантам', index=False)
    output.seek(0)
    return send_file(output, download_name=f'survey_{survey_id}_results.xlsx', as_attachment=True)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5005
    app.run(host='0.0.0.0', port=port, debug=True)
