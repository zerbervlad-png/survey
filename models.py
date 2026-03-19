import sqlite3
import pandas as pd
import os
from datetime import datetime

DB_FILE = 'survey.db'

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY (survey_id) REFERENCES surveys (id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            type TEXT NOT NULL,
            options TEXT,
            "order" INTEGER DEFAULT 0,
            FOREIGN KEY (survey_id) REFERENCES surveys (id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (survey_id) REFERENCES surveys (id) ON DELETE CASCADE,
            FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            response_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            value TEXT,
            FOREIGN KEY (response_id) REFERENCES responses (id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
        );
        ''')
        conn.commit()

def create_survey(title, start_date, end_date, employee_names, questions_data):
    import json
    with get_db() as conn:
        cur = conn.execute(
            'INSERT INTO surveys (title, start_date, end_date) VALUES (?, ?, ?)',
            (title, start_date, end_date)
        )
        survey_id = cur.lastrowid
        for name in employee_names:
            conn.execute('INSERT INTO employees (survey_id, name) VALUES (?, ?)', (survey_id, name.strip()))
        for idx, q in enumerate(questions_data):
            options_json = json.dumps(q.get('options', [])) if q.get('options') else None
            conn.execute('''
                INSERT INTO questions (survey_id, text, type, options, "order")
                VALUES (?, ?, ?, ?, ?)
            ''', (survey_id, q['text'], q['type'], options_json, idx))
        conn.commit()
        return survey_id

def get_all_surveys(only_active=False):
    with get_db() as conn:
        today = datetime.now().strftime('%Y-%m-%d')
        if only_active:
            surveys = conn.execute('''
                SELECT * FROM surveys 
                WHERE is_active = 1 AND start_date <= ? AND end_date >= ?
                ORDER BY created_at DESC
            ''', (today, today)).fetchall()
        else:
            surveys = conn.execute('SELECT * FROM surveys ORDER BY created_at DESC').fetchall()
        result = []
        for s in surveys:
            total = conn.execute('SELECT COUNT(*) FROM employees WHERE survey_id = ?', (s['id'],)).fetchone()[0]
            responded = conn.execute('SELECT COUNT(DISTINCT employee_id) FROM responses WHERE survey_id = ?', (s['id'],)).fetchone()[0]
            result.append({
                'id': s['id'],
                'title': s['title'],
                'start_date': s['start_date'],
                'end_date': s['end_date'],
                'is_active': s['is_active'],
                'created_at': s['created_at'],
                'total': total,
                'responded': responded,
                'percent': round(responded/total*100,1) if total else 0
            })
        return result

def get_survey_details(survey_id):
    import json
    with get_db() as conn:
        survey = conn.execute('SELECT * FROM surveys WHERE id = ?', (survey_id,)).fetchone()
        if not survey:
            return None
        employees = conn.execute('SELECT * FROM employees WHERE survey_id = ? ORDER BY name', (survey_id,)).fetchall()
        questions = conn.execute('SELECT * FROM questions WHERE survey_id = ? ORDER BY "order"', (survey_id,)).fetchall()
        questions_list = []
        for q in questions:
            qdict = dict(q)
            qdict['options'] = json.loads(qdict['options']) if qdict['options'] else []
            questions_list.append(qdict)
        responses = conn.execute('''
            SELECT r.id, e.name, r.submitted_at
            FROM responses r
            JOIN employees e ON r.employee_id = e.id
            WHERE r.survey_id = ?
            ORDER BY r.submitted_at DESC
        ''', (survey_id,)).fetchall()
        responded_names = {r['name'] for r in responses}
        total = len(employees)
        responded_count = len(responses)
        not_responded = [e['name'] for e in employees if e['name'] not in responded_names]
        
        question_stats = []
        for q in questions_list:
            if q['type'] == 'text':
                ans = conn.execute('SELECT value FROM answers WHERE question_id = ?', (q['id'],)).fetchall()
                question_stats.append({
                    'question': q,
                    'type': 'text',
                    'answers': [a['value'] for a in ans]
                })
            elif q['type'] in ('single', 'multiple'):
                opt_counts = {opt: 0 for opt in q['options']}
                if q['type'] == 'single':
                    ans = conn.execute('SELECT value FROM answers WHERE question_id = ?', (q['id'],)).fetchall()
                    for a in ans:
                        if a['value'] in opt_counts:
                            opt_counts[a['value']] += 1
                else:
                    ans = conn.execute('SELECT value FROM answers WHERE question_id = ?', (q['id'],)).fetchall()
                    for a in ans:
                        if a['value']:
                            try:
                                chosen = json.loads(a['value'])
                                for opt in chosen:
                                    if opt in opt_counts:
                                        opt_counts[opt] += 1
                            except:
                                pass
                stats = [{'option': opt, 'count': cnt, 'percent': round(cnt/responded_count*100,1) if responded_count else 0}
                         for opt, cnt in opt_counts.items()]
                question_stats.append({
                    'question': q,
                    'type': q['type'],
                    'stats': stats
                })
        return {
            'survey': dict(survey),
            'total': total,
            'responded_count': responded_count,
            'not_responded_count': total - responded_count,
            'percent': round(responded_count/total*100,1) if total else 0,
            'responded_list': [dict(r) for r in responses],
            'not_responded_list': not_responded,
            'employees': [e['name'] for e in employees],
            'questions': questions_list,
            'question_stats': question_stats
        }

def save_response(survey_id, employee_name, answers_dict):
    import json
    with get_db() as conn:
        emp = conn.execute('SELECT id FROM employees WHERE survey_id = ? AND name = ?', (survey_id, employee_name)).fetchone()
        if not emp:
            return False
        existing = conn.execute('SELECT id FROM responses WHERE survey_id = ? AND employee_id = ?', (survey_id, emp['id'])).fetchone()
        if existing:
            return False
        cur = conn.execute('INSERT INTO responses (survey_id, employee_id) VALUES (?, ?)', (survey_id, emp['id']))
        response_id = cur.lastrowid
        for qid, val in answers_dict.items():
            if isinstance(val, list):
                val = json.dumps(val)
            conn.execute('INSERT INTO answers (response_id, question_id, value) VALUES (?, ?, ?)',
                         (response_id, int(qid), str(val) if val else None))
        conn.commit()
        return True

def employee_has_responded(survey_id, employee_name):
    with get_db() as conn:
        emp = conn.execute('SELECT id FROM employees WHERE survey_id = ? AND name = ?', (survey_id, employee_name)).fetchone()
        if not emp:
            return False
        res = conn.execute('SELECT id FROM responses WHERE survey_id = ? AND employee_id = ?', (survey_id, emp['id'])).fetchone()
        return res is not None

def is_survey_active(survey_id):
    with get_db() as conn:
        s = conn.execute('SELECT start_date, end_date, is_active FROM surveys WHERE id = ?', (survey_id,)).fetchone()
        if not s:
            return False
        if not s['is_active']:
            return False
        today = datetime.now().strftime('%Y-%m-%d')
        return s['start_date'] <= today <= s['end_date']

def close_survey(survey_id):
    with get_db() as conn:
        conn.execute('UPDATE surveys SET is_active = 0 WHERE id = ?', (survey_id,))
        conn.commit()
