import sqlite3
import os
from datetime import datetime, timedelta
import time
import pytz

DB_PATH = os.path.join(os.path.dirname(__file__), 'employees.db')
CAMBODIA_TZ = pytz.timezone('Asia/Phnom_Penh')

def get_current_time():
    return datetime.now(CAMBODIA_TZ)

def get_current_date():
    return get_current_time().strftime('%Y-%m-%d')

def get_current_datetime_str():
    return get_current_time().strftime('%Y-%m-%d %H:%M:%S')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def retry_on_locked(func, *args, **kwargs):
    max_retries = 5
    for i in range(max_retries):
        try:
            return func(*args, **kwargs)
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and i < max_retries - 1:
                print(f"Database locked, retrying... ({i+1}/{max_retries})")
                time.sleep(1)
            else:
                raise
    return None

def column_exists(table_name, column_name):
    """ពិនិត្យមើលថាតើ column មានក្នុងតារាងឬទេ"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        return column_name in columns
    except Exception as e:
        print(f"Error in column_exists: {e}")
        return False

def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # ===== 1. តារាង Users =====
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ===== 2. តារាង Company Location =====
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS company_location (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lat REAL NOT NULL,
                lng REAL NOT NULL,
                address TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ===== 3. តារាង Attendance (បន្ថែម column shift) =====
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date DATE NOT NULL,
                check_in DATETIME NOT NULL,
                check_out DATETIME,
                shift INTEGER DEFAULT 1,
                location_lat REAL,
                location_lng REAL,
                distance REAL,
                total_hours REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # ===== 4. តារាង Leaves =====
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leaves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                days REAL NOT NULL,
                reason TEXT,
                status TEXT DEFAULT 'pending',
                approved_by INTEGER,
                approved_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (approved_by) REFERENCES users (id)
            )
        ''')

        # ===== 5. តារាង Missions =====
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS missions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                days REAL NOT NULL,
                destination TEXT,
                purpose TEXT,
                status TEXT DEFAULT 'pending',
                approved_by INTEGER,
                approved_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (approved_by) REFERENCES users (id)
            )
        ''')

        # ===== 6. តារាង Settings =====
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ===== 7. បញ្ចូល Admin =====
        cursor.execute("SELECT * FROM users WHERE username = 'admin'")
        admin = cursor.fetchone()
        if not admin:
            cursor.execute('''
                INSERT INTO users (username, password, full_name, role)
                VALUES (?, ?, ?, ?)
            ''', ('admin', '1234', 'អ្នកគ្រប់គ្រងប្រព័ន្ធ', 'admin'))
            print("✅ បានបង្កើតគណនី Admin ដំបូង")

        # ===== 8. បញ្ចូលតម្លៃដើមសម្រាប់ Settings =====
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('check_in_start', '08:00')")
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('check_in_end', '17:00')")
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('check_out_start', '08:00')")
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('check_out_end', '17:00')")
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('is_locked', '0')")

        conn.commit()
        conn.close()
        print("✅ Database បានបង្កើតរួចរាល់!")
    except Exception as e:
        print(f"Error in init_db: {e}")
        try:
            conn.close()
        except:
            pass

# ============================================================
# CLEAN DATA FUNCTIONS
# ============================================================

def clean_all_data():
    """លុបទិន្នន័យទាំងអស់ (attendance, leaves, missions) តែរក្សាអ្នកប្រើ"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM attendance")
        cursor.execute("DELETE FROM leaves")
        cursor.execute("DELETE FROM missions")

        cursor.execute("DELETE FROM sqlite_sequence WHERE name='attendance'")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='leaves'")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='missions'")

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in clean_all_data: {e}")
        return False

def clean_attendance_only():
    """លុបតែទិន្នន័យវត្តមាន (attendance)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attendance")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='attendance'")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in clean_attendance_only: {e}")
        return False

def clean_leaves_only():
    """លុបតែទិន្នន័យសុំច្បាប់ (leaves)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM leaves")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='leaves'")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in clean_leaves_only: {e}")
        return False

def clean_missions_only():
    """លុបតែទិន្នន័យបេសកម្ម (missions)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM missions")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='missions'")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in clean_missions_only: {e}")
        return False

# ============================================================
# PASSWORD FUNCTIONS
# ============================================================

def update_password(user_id, new_password):
    """ប្តូរពាក្យសម្ងាត់របស់អ្នកប្រើ"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (new_password, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in update_password: {e}")
        return False

def verify_password(user_id, current_password):
    """ផ្ទៀងផ្ទាត់ពាក្យសម្ងាត់បច្ចុប្បន្ន"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        if result and result['password'] == current_password:
            return True
        return False
    except Exception as e:
        print(f"Error in verify_password: {e}")
        return False

# ============================================================
# USER MANAGEMENT FUNCTIONS
# ============================================================

def create_user(username, password, full_name, email=None, phone=None, role='user'):
    """បង្កើតអ្នកប្រើថ្មី"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (username, password, full_name, email, phone, role)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (username, password, full_name, email, phone, role))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False
    except Exception as e:
        print(f"Error in create_user: {e}")
        return False

def update_user(user_id, username=None, full_name=None, email=None, phone=None, role=None):
    """កែប្រែព័ត៌មានអ្នកប្រើ"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        updates = []
        params = []

        if username is not None:
            updates.append("username = ?")
            params.append(username)
        if full_name is not None:
            updates.append("full_name = ?")
            params.append(full_name)
        if email is not None:
            updates.append("email = ?")
            params.append(email)
        if phone is not None:
            updates.append("phone = ?")
            params.append(phone)
        if role is not None:
            updates.append("role = ?")
            params.append(role)

        if not updates:
            conn.close()
            return False

        params.append(user_id)
        sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(sql, params)
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False
    except Exception as e:
        print(f"Error in update_user: {e}")
        return False

def delete_user(user_id):
    """លុបអ្នកប្រើ"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM attendance WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            cursor.execute("DELETE FROM attendance WHERE user_id = ?", (user_id,))

        cursor.execute("SELECT * FROM leaves WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            cursor.execute("DELETE FROM leaves WHERE user_id = ?", (user_id,))

        cursor.execute("SELECT * FROM missions WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            cursor.execute("DELETE FROM missions WHERE user_id = ?", (user_id,))

        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in delete_user: {e}")
        return False

def get_user_by_id(user_id):
    """រកអ្នកប្រើតាម ID"""
    try:
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        return user
    except Exception as e:
        print(f"Error in get_user_by_id: {e}")
        return None

def get_user_by_username(username):
    """រកអ្នកប្រើតាមឈ្មោះអ្នកប្រើ"""
    try:
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        return user
    except Exception as e:
        print(f"Error in get_user_by_username: {e}")
        return None

def get_all_users():
    """ទទួលអ្នកប្រើទាំងអស់"""
    try:
        conn = get_db_connection()
        users = conn.execute('SELECT * FROM users ORDER BY id DESC').fetchall()
        conn.close()
        return users
    except Exception as e:
        print(f"Error in get_all_users: {e}")
        return []

# ============================================================
# COMPANY LOCATION FUNCTIONS
# ============================================================

def save_company_location(lat, lng, address=None):
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM company_location')
        conn.execute('''
            INSERT INTO company_location (lat, lng, address)
            VALUES (?, ?, ?)
        ''', (lat, lng, address))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in save_company_location: {e}")
        return False

def get_company_location():
    try:
        conn = get_db_connection()
        location = conn.execute('SELECT * FROM company_location ORDER BY id DESC LIMIT 1').fetchone()
        conn.close()
        return location
    except Exception as e:
        print(f"Error in get_company_location: {e}")
        return None

# ============================================================
# ATTENDANCE FUNCTIONS (កែប្រែដើម្បីគាំទ្រវគ្គ)
# ============================================================

def check_in(user_id, lat=None, lng=None, distance=None, shift=1):
    """ចូលធ្វើការជាមួយវគ្គដែលបានជ្រើស"""
    def _check_in():
        if not user_id:
            print("Error: user_id is None in check_in")
            return False

        now = get_current_time()
        date = now.strftime('%Y-%m-%d')
        datetime_str = now.strftime('%Y-%m-%d %H:%M:%S')

        conn = get_db_connection()
        cursor = conn.cursor()

        # ពិនិត្យមើលថាតើមានការចូលវគ្គនេះហើយឬនៅ
        cursor.execute('''
            SELECT id FROM attendance
            WHERE user_id = ? AND date = ? AND shift = ? AND check_out IS NULL
        ''', (user_id, date, shift))
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            return False

        cursor.execute('''
            INSERT INTO attendance (user_id, date, check_in, shift, location_lat, location_lng, distance)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, date, datetime_str, shift, lat, lng, distance))

        conn.commit()
        print(f"✅ Check-in successful for user {user_id} at {datetime_str} (Shift {shift})")
        conn.close()
        return True

    try:
        return retry_on_locked(_check_in)
    except Exception as e:
        print(f"Error in check_in function: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_out(user_id, shift=None):
    """ចេញធ្វើការ អាចបញ្ជាក់វគ្គបាន"""
    def _check_out():
        now = get_current_time()
        datetime_str = now.strftime('%Y-%m-%d %H:%M:%S')

        conn = get_db_connection()
        cursor = conn.cursor()

        if shift is not None:
            # ចេញតាមវគ្គដែលបានបញ្ជាក់
            cursor.execute('''
                SELECT * FROM attendance
                WHERE user_id = ? AND shift = ? AND check_out IS NULL
                ORDER BY id DESC LIMIT 1
            ''', (user_id, shift))
        else:
            # ចេញវគ្គចុងក្រោយដែលមិនទាន់ចេញ
            cursor.execute('''
                SELECT * FROM attendance
                WHERE user_id = ? AND check_out IS NULL
                ORDER BY id DESC LIMIT 1
            ''', (user_id,))

        last_att = cursor.fetchone()

        if not last_att:
            print(f"❌ No open attendance for user {user_id}")
            conn.close()
            return False

        check_in_time = datetime.strptime(last_att['check_in'], '%Y-%m-%d %H:%M:%S')
        now_naive = now.replace(tzinfo=None)
        total_seconds = (now_naive - check_in_time).total_seconds()
        total_hours = total_seconds / 3600

        # កែតម្រូវសម្រាប់វគ្គយប់ (Shift 3)
        att_shift = last_att['shift'] if 'shift' in last_att.keys() else 1
        if att_shift == 3:
            # បើចូលយប់ ហើយចេញព្រឹក (ចេញមុនពេលចូល)
            # ឧទាហរណ៍: ចូល 18:00 ចេញ 08:00 = 14 ម៉ោង
            if total_hours < 0:
                # បើម៉ោងសរុបជាអវិជ្ជមាន មានន័យថាចេញថ្ងៃបន្ទាប់
                total_hours += 24

        cursor.execute('''
            UPDATE attendance
            SET check_out = ?, total_hours = ?
            WHERE id = ?
        ''', (datetime_str, total_hours, last_att['id']))

        conn.commit()
        print(f"✅ Check-out successful for user {user_id} at {datetime_str} (Total: {total_hours:.2f} hours)")
        conn.close()
        return True

    try:
        return retry_on_locked(_check_out)
    except Exception as e:
        print(f"Error in check_out function: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_user_attendance(user_id, limit=50):
    try:
        conn = get_db_connection()
        atts = conn.execute('''
            SELECT a.*, u.full_name
            FROM attendance a
            JOIN users u ON u.id = a.user_id
            WHERE a.user_id = ?
            ORDER BY a.id DESC
            LIMIT ?
        ''', (user_id, limit)).fetchall()
        conn.close()
        return atts
    except Exception as e:
        print(f"Error in get_user_attendance: {e}")
        return []

def get_all_attendance(limit=100):
    try:
        conn = get_db_connection()
        atts = conn.execute('''
            SELECT a.*, u.full_name, u.username
            FROM attendance a
            JOIN users u ON u.id = a.user_id
            ORDER BY a.id DESC
            LIMIT ?
        ''', (limit,)).fetchall()
        conn.close()
        return atts
    except Exception as e:
        print(f"Error in get_all_attendance: {e}")
        return []

def get_attendance_stats():
    try:
        today = get_current_date()
        conn = get_db_connection()

        total_users = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
        present_today = conn.execute('''
            SELECT COUNT(DISTINCT user_id) as count FROM attendance
            WHERE date = ?
        ''', (today,)).fetchone()['count']
        leave_today = conn.execute('''
            SELECT COUNT(*) as count FROM leaves
            WHERE ? BETWEEN start_date AND end_date AND status = 'approved'
        ''', (today,)).fetchone()['count']
        mission_today = conn.execute('''
            SELECT COUNT(*) as count FROM missions
            WHERE ? BETWEEN start_date AND end_date AND status = 'approved'
        ''', (today,)).fetchone()['count']

        conn.close()
        return {
            'total_users': total_users,
            'present_today': present_today,
            'leave_today': leave_today,
            'mission_today': mission_today
        }
    except Exception as e:
        print(f"Error in get_attendance_stats: {e}")
        return {'total_users': 0, 'present_today': 0, 'leave_today': 0, 'mission_today': 0}

def get_today_attendance_details():
    """ទទួលព័ត៌មានលម្អិតនៃការចូលធ្វើការថ្ងៃនេះ"""
    try:
        today = get_current_date()
        conn = get_db_connection()
        details = conn.execute('''
            SELECT 
                a.*,
                u.full_name,
                u.username,
                CASE 
                    WHEN a.shift = 1 THEN 'វគ្គ 1 (ព្រឹក)'
                    WHEN a.shift = 2 THEN 'វគ្គ 2 (រសៀល)'
                    WHEN a.shift = 3 THEN 'វគ្គ 3 (យប់)'
                    ELSE 'មិនបានកំណត់'
                END as shift_name,
                CASE 
                    WHEN a.check_out IS NOT NULL THEN 'បានបិទ'
                    ELSE 'កំពុងធ្វើការ'
                END as status
            FROM attendance a
            JOIN users u ON u.id = a.user_id
            WHERE a.date = ?
            ORDER BY a.shift, a.check_in DESC
        ''', (today,)).fetchall()
        conn.close()
        return details
    except Exception as e:
        print(f"Error in get_today_attendance_details: {e}")
        return []

# ============================================================
# LEAVE FUNCTIONS
# ============================================================

def create_leave(user_id, start_date, end_date, days, reason):
    try:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO leaves (user_id, start_date, end_date, days, reason, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        ''', (user_id, start_date, end_date, days, reason))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in create_leave: {e}")
        return False

def get_pending_leaves():
    try:
        conn = get_db_connection()
        leaves = conn.execute('''
            SELECT l.*, u.full_name, u.username
            FROM leaves l
            JOIN users u ON u.id = l.user_id
            WHERE l.status = 'pending'
            ORDER BY l.created_at DESC
        ''').fetchall()
        conn.close()
        return leaves
    except Exception as e:
        print(f"Error in get_pending_leaves: {e}")
        return []

def get_approved_leaves_today():
    try:
        today = get_current_date()
        conn = get_db_connection()
        leaves = conn.execute('''
            SELECT l.*, u.full_name, u.username
            FROM leaves l
            JOIN users u ON u.id = l.user_id
            WHERE l.status = 'approved'
            AND ? BETWEEN l.start_date AND l.end_date
            ORDER BY l.start_date DESC
        ''', (today,)).fetchall()
        conn.close()
        return leaves
    except Exception as e:
        print(f"Error in get_approved_leaves_today: {e}")
        return []

def approve_leave(leave_id, admin_id):
    try:
        conn = get_db_connection()
        conn.execute('''
            UPDATE leaves
            SET status = 'approved', approved_by = ?, approved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (admin_id, leave_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in approve_leave: {e}")
        return False

def reject_leave(leave_id):
    try:
        conn = get_db_connection()
        conn.execute('''
            UPDATE leaves SET status = 'rejected' WHERE id = ?
        ''', (leave_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in reject_leave: {e}")
        return False

# ============================================================
# MISSION FUNCTIONS
# ============================================================

def create_mission(user_id, start_date, end_date, days, destination, purpose):
    try:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO missions (user_id, start_date, end_date, days, destination, purpose, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        ''', (user_id, start_date, end_date, days, destination, purpose))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in create_mission: {e}")
        return False

def get_pending_missions():
    try:
        conn = get_db_connection()
        missions = conn.execute('''
            SELECT m.*, u.full_name, u.username
            FROM missions m
            JOIN users u ON u.id = m.user_id
            WHERE m.status = 'pending'
            ORDER BY m.created_at DESC
        ''').fetchall()
        conn.close()
        return missions
    except Exception as e:
        print(f"Error in get_pending_missions: {e}")
        return []

def get_approved_missions_today():
    try:
        today = get_current_date()
        conn = get_db_connection()
        missions = conn.execute('''
            SELECT m.*, u.full_name, u.username
            FROM missions m
            JOIN users u ON u.id = m.user_id
            WHERE m.status = 'approved'
            AND ? BETWEEN m.start_date AND m.end_date
            ORDER BY m.start_date DESC
        ''', (today,)).fetchall()
        conn.close()
        return missions
    except Exception as e:
        print(f"Error in get_approved_missions_today: {e}")
        return []

def approve_mission(mission_id, admin_id):
    try:
        conn = get_db_connection()
        conn.execute('''
            UPDATE missions
            SET status = 'approved', approved_by = ?, approved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (admin_id, mission_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in approve_mission: {e}")
        return False

def reject_mission(mission_id):
    try:
        conn = get_db_connection()
        conn.execute('''
            UPDATE missions SET status = 'rejected' WHERE id = ?
        ''', (mission_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in reject_mission: {e}")
        return False

# ============================================================
# REPORT FUNCTIONS (កែប្រែថ្មី)
# ============================================================

def get_attendance_report(start_date, end_date):
    """ទទួលរបាយការណ៍វត្តមានតាមកាលបរិច្ឆេទ (ជាមួយវគ្គ)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # ===== 1. របាយការណ៍ប្រចាំថ្ងៃ =====
        daily_report = cursor.execute('''
            SELECT
                a.id,
                a.user_id,
                u.full_name,
                u.username,
                a.date,
                a.shift,
                a.check_in,
                a.check_out,
                a.total_hours,
                CASE 
                    WHEN a.shift = 1 THEN 'វគ្គ 1 (ព្រឹក)'
                    WHEN a.shift = 2 THEN 'វគ្គ 2 (រសៀល)'
                    WHEN a.shift = 3 THEN 'វគ្គ 3 (យប់)'
                    ELSE 'មិនបានកំណត់'
                END as shift_name,
                CASE 
                    WHEN a.check_in IS NOT NULL AND a.check_out IS NOT NULL THEN 'បានបិទ'
                    WHEN a.check_in IS NOT NULL AND a.check_out IS NULL THEN 'កំពុងធ្វើការ'
                    ELSE 'មិនទាន់ចូល'
                END as status
            FROM attendance a
            JOIN users u ON u.id = a.user_id
            WHERE a.date BETWEEN ? AND ?
            ORDER BY a.date DESC, a.user_id, a.shift
        ''', (start_date, end_date)).fetchall()

        # ===== 2. របាយការណ៍សង្ខេបប្រចាំខែ =====
        summary = cursor.execute('''
            SELECT
                u.id,
                u.username,
                u.full_name,
                u.role,
                COUNT(DISTINCT a.date) as days_worked,
                COALESCE(SUM(a.total_hours), 0) as total_hours,
                COUNT(DISTINCT CASE WHEN a.shift = 3 THEN a.date END) as night_shifts,
                COALESCE(SUM(CASE WHEN a.shift = 3 THEN a.total_hours ELSE 0 END), 0) as night_hours,
                COUNT(a.id) as total_attendance
            FROM users u
            LEFT JOIN attendance a ON u.id = a.user_id 
                AND a.date BETWEEN ? AND ?
                AND a.check_in IS NOT NULL
            WHERE u.role != 'admin'
            GROUP BY u.id
            ORDER BY total_hours DESC
        ''', (start_date, end_date)).fetchall()

        # ===== 3. ថ្ងៃសុំច្បាប់ =====
        leave_days = cursor.execute('''
            SELECT 
                user_id,
                SUM(days) as total_leave_days
            FROM leaves
            WHERE status = 'approved'
                AND start_date >= ? AND end_date <= ?
            GROUP BY user_id
        ''', (start_date, end_date)).fetchall()

        # ===== 4. ថ្ងៃបេសកម្ម =====
        mission_days = cursor.execute('''
            SELECT 
                user_id,
                SUM(days) as total_mission_days
            FROM missions
            WHERE status = 'approved'
                AND start_date >= ? AND end_date <= ?
            GROUP BY user_id
        ''', (start_date, end_date)).fetchall()

        # ===== 5. បញ្ចូលទិន្នន័យច្បាប់ និងបេសកម្ម =====
        leave_dict = {row['user_id']: row['total_leave_days'] for row in leave_days}
        mission_dict = {row['user_id']: row['total_mission_days'] for row in mission_days}

        summary_with_leave_mission = []
        for emp in summary:
            emp_dict = dict(emp)
            emp_dict['total_leave_days'] = leave_dict.get(emp['id'], 0)
            emp_dict['total_mission_days'] = mission_dict.get(emp['id'], 0)
            summary_with_leave_mission.append(emp_dict)

        # ===== 6. ស្ថិតិ =====
        stats = cursor.execute('''
            SELECT
                COUNT(DISTINCT user_id) as total_users,
                COUNT(*) as total_attendance,
                COALESCE(SUM(total_hours), 0) as total_hours,
                COALESCE(AVG(total_hours), 0) as avg_hours
            FROM attendance
            WHERE date BETWEEN ? AND ?
        ''', (start_date, end_date)).fetchone()

        # ===== 7. ទិន្នន័យប្រចាំថ្ងៃសម្រាប់ក្រាហ្វ =====
        daily_stats = cursor.execute('''
            SELECT
                date,
                COUNT(DISTINCT user_id) as users,
                COUNT(*) as checkins,
                COALESCE(SUM(total_hours), 0) as hours
            FROM attendance
            WHERE date BETWEEN ? AND ?
            GROUP BY date
            ORDER BY date
        ''', (start_date, end_date)).fetchall()

        conn.close()

        return {
            'daily': daily_report,
            'summary': summary_with_leave_mission,
            'stats': stats,
            'daily_stats': daily_stats
        }
    except Exception as e:
        print(f"Error in get_attendance_report: {e}")
        import traceback
        traceback.print_exc()
        return {'daily': [], 'summary': [], 'stats': None, 'daily_stats': []}

def get_monthly_summary(year, month):
    """ទទួលរបាយការណ៍ប្រចាំខែ"""
    try:
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year}-12-31"
        else:
            next_month = month + 1
            end_dt = datetime(year, next_month, 1) - timedelta(days=1)
            end_date = end_dt.strftime('%Y-%m-%d')

        return get_attendance_report(start_date, end_date)
    except Exception as e:
        print(f"Error in get_monthly_summary: {e}")
        return {'daily': [], 'summary': [], 'stats': None, 'daily_stats': []}

# ============================================================
# SETTINGS FUNCTIONS
# ============================================================

def get_setting(key):
    """ទទួលតម្លៃកំណត់"""
    try:
        conn = get_db_connection()
        result = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        conn.close()
        return result['value'] if result else None
    except Exception as e:
        print(f"Error in get_setting: {e}")
        return None

def set_setting(key, value):
    """កំណត់តម្លៃកំណត់"""
    try:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
        ''', (key, value, value))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in set_setting: {e}")
        return False

def get_all_settings():
    """ទទួលតម្លៃកំណត់ទាំងអស់"""
    try:
        conn = get_db_connection()
        settings = conn.execute('SELECT * FROM settings').fetchall()
        conn.close()
        result = {}
        for row in settings:
            result[row['key']] = row['value']
        return result
    except Exception as e:
        print(f"Error in get_all_settings: {e}")
        return {}

# ============================================================
# DATA VERSION (សម្រាប់ Auto Refresh)
# ============================================================

def get_data_version():
    """ទទួល version ទិន្នន័យបច្ចុប្បន្ន"""
    try:
        conn = get_db_connection()
        result = conn.execute('''
            SELECT value FROM settings WHERE key = 'data_version'
        ''').fetchone()
        conn.close()
        if result:
            return int(result['value'])
        return 1
    except Exception as e:
        print(f"Error in get_data_version: {e}")
        return 1

def increment_data_version():
    """បង្កើន version ទិន្នន័យ (ហៅពេលមានការផ្លាស់ប្តូរ)"""
    try:
        current = get_data_version()
        new_version = current + 1
        set_setting('data_version', str(new_version))
        return new_version
    except Exception as e:
        print(f"Error in increment_data_version: {e}")
        return 1

# ============================================================
# INIT DATABASE
# ============================================================

if not os.path.exists(DB_PATH):
    init_db()
else:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        required_tables = ['users', 'company_location', 'attendance', 'leaves', 'missions', 'settings']
        if not all(table in tables for table in required_tables):
            init_db()
        else:
            # ពិនិត្យមើលថាតើ column shift មានក្នុងតារាង attendance ដែរឬទេ
            if not column_exists('attendance', 'shift'):
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("ALTER TABLE attendance ADD COLUMN shift INTEGER DEFAULT 1")
                    conn.commit()
                    conn.close()
                    print("✅ Added 'shift' column to attendance table")
                except Exception as e:
                    print(f"⚠️ Could not add 'shift' column: {e}")
            
            # ពិនិត្យមើលថាតើ data_version មានក្នុង settings ដែរឬទេ
            if not get_setting('data_version'):
                set_setting('data_version', '1')
                print("✅ Added data_version to settings")

    except Exception as e:
        print(f"Error checking database: {e}")
        init_db()