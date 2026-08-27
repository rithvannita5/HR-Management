# flask_app.py - CORRECT VERSION
from flask import Flask, request, redirect, url_for, session, render_template_string, jsonify, send_file, send_from_directory
import os
import math
import pytz
import uuid
import io
import threading
import time
from datetime import datetime, timedelta
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill

# ============================================================
# MONGODB CONNECTION
# ============================================================

from mongo_db import (
    init_db,
    get_data_version,
    increment_data_version,
    get_user_by_id,
    get_user_by_username,
    create_user,
    update_user,
    update_password,
    verify_password,
    delete_user,
    get_all_users,
    save_company_location,
    get_company_location,
    check_in,
    check_out,
    get_checkin_status,
    get_system_lock_status,
    update_system_lock,
    toggle_system_lock,
    get_user_lock_status,
    update_user_lock,
    get_all_user_lock_status,
    get_attendance_stats,
    get_all_attendance,
    get_work_history_report,
    get_monthly_summary_report,
    get_attendance_setting,
    save_attendance_setting,
    get_all_attendance_settings,
    create_leave,
    get_pending_leaves,
    approve_leave,
    reject_leave,
    create_mission,
    get_pending_missions,
    approve_mission,
    reject_mission,
    clean_all_data,
    clean_attendance_only,
    clean_leaves_only,
    clean_missions_only,
    get_current_date,
    get_current_datetime,
    get_current_time,
    get_current_time_only,
    get_current_datetime_str,
    get_attendance_report,
    get_attendance_by_id,
    update_attendance,
    delete_attendance,
    check_attendance_deadline,
    check_system_lock_for_user,
    check_user_lock
)

print("✅ Using MongoDB")

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here-123456789')

# ============================================================
# BACKGROUND AUTO-LOCK/UNLOCK THREAD
# ============================================================

def auto_lock_unlock_checker():
    while True:
        try:
            current_time = get_current_time_only()
            current_hhmm = current_time[:5]
            
            lock = get_system_lock_status()
            if lock.get('is_locked', 0) == 1:
                auto_unlock = lock.get('auto_unlock_time')
                if auto_unlock and current_hhmm >= auto_unlock:
                    print(f"🔄 Auto-unlocking system at {current_hhmm}")
                    update_system_lock(0, locked_by=None)
                    increment_data_version()
            
            settings = get_all_attendance_settings()
            for setting in settings:
                if setting.get('is_active') != 1:
                    continue
                user_id = setting.get('user_id')
                deadline = setting.get('check_in_deadline')
                if deadline and current_hhmm >= deadline:
                    user_lock = get_user_lock_status(user_id)
                    if user_lock.get('is_locked', 0) != 1:
                        system_lock = get_system_lock_status()
                        auto_unlock = system_lock.get('auto_unlock_time', '06:00')
                        update_user_lock(user_id, 1, auto_unlock_time=auto_unlock)
                        increment_data_version()
            
            all_users = get_all_users()
            for user in all_users:
                if user.get('role') == 'admin':
                    continue
                user_id = str(user.get('id', user.get('_id')))
                user_lock = get_user_lock_status(user_id)
                if user_lock.get('is_locked', 0) == 1:
                    auto_unlock = user_lock.get('auto_unlock_time')
                    if auto_unlock and current_hhmm >= auto_unlock:
                        update_user_lock(user_id, 0)
                        increment_data_version()
                        
        except Exception as e:
            print(f"❌ Error in auto-lock/unlock checker: {e}")
        time.sleep(30)

def start_auto_lock_unlock_thread():
    thread = threading.Thread(target=auto_lock_unlock_checker, daemon=True)
    thread.start()
    print("✅ Auto-lock/unlock background thread started!")

start_auto_lock_unlock_thread()

# ============================================================
# UPLOAD CONFIGURATION
# ============================================================

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.config['ALLOWED_DISTANCE'] = 150

UPLOAD_FOLDER_LEAVES = os.path.join('static', 'uploads', 'leaves')
UPLOAD_FOLDER_MISSIONS = os.path.join('static', 'uploads', 'missions')
os.makedirs(UPLOAD_FOLDER_LEAVES, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_MISSIONS, exist_ok=True)

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def save_uploaded_file(file, user_id, folder_type):
    if file and file.filename:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        file_ext = os.path.splitext(file.filename)[1]
        new_filename = f"{folder_type}_{user_id}_{timestamp}_{unique_id}{file_ext}"
        if folder_type == 'leave':
            upload_folder = UPLOAD_FOLDER_LEAVES
        else:
            upload_folder = UPLOAD_FOLDER_MISSIONS
        file_path = os.path.join(upload_folder, new_filename)
        file.save(file_path)
        return f"/static/uploads/{folder_type}s/{new_filename}"
    return None

# ============================================================
# HTML TEMPLATES (ចម្លងពីកូដចាស់របស់អ្នក)
# ============================================================

# ===== ដាក់ DASHBOARD_HTML, REGISTER_HTML, CHANGE_PASSWORD_HTML, USER_MANAGEMENT_HTML, REPORT_HTML នៅទីនេះ =====

# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def home():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    stats = get_attendance_stats()
    today = datetime.now()
    start_date = today.replace(day=1).strftime('%Y-%m-%d')
    end_date = today.strftime('%Y-%m-%d')
    work_history = get_work_history_report(start_date, end_date, 200)
    monthly_summary = get_monthly_summary_report(start_date, end_date)
    company_loc = get_company_location()
    pending_leaves = get_pending_leaves()
    pending_missions = get_pending_missions()
    pending_count = len(pending_leaves) + len(pending_missions)
    data_version = get_data_version()
    current_month = today.strftime('%m')
    current_year = today.strftime('%Y')
    allowed_distance = app.config['ALLOWED_DISTANCE']
    lock_status = get_system_lock_status()
    user_lock = get_user_lock_status(session.get('user_id'))
    
    return render_template_string(DASHBOARD_HTML,
                                   session=session,
                                   stats=stats,
                                   work_history=work_history,
                                   monthly_summary=monthly_summary,
                                   company_lat=company_loc['lat'] if company_loc else '',
                                   company_lng=company_loc['lng'] if company_loc else '',
                                   pending_count=pending_count,
                                   data_version=data_version,
                                   current_month=current_month,
                                   current_year=current_year,
                                   allowed_distance=allowed_distance,
                                   lock_status=lock_status,
                                   user_lock=user_lock)

@app.route('/get_data_version')
def get_data_version_route():
    if not session.get('logged_in'):
        return jsonify({'version': 0})
    version = get_data_version()
    return jsonify({'version': version})

@app.route('/get_checkin_status')
def get_checkin_status_route():
    if not session.get('logged_in'):
        return jsonify({'has_checkin': False, 'check_in_time': None, 'shift': None})
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'has_checkin': False, 'check_in_time': None, 'shift': None})
    status = get_checkin_status(user_id)
    return jsonify(status)

@app.route('/get_system_lock_status')
def get_system_lock_status_route():
    if not session.get('logged_in'):
        return jsonify({'is_locked': 0, 'auto_unlock_time': '06:00'})
    lock = get_system_lock_status()
    return jsonify(lock)

@app.route('/toggle_system_lock', methods=['POST'])
def toggle_system_lock_route():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'អ្នកមិនមែនជា Admin!'})
    data = request.get_json()
    lock_state = data.get('lock_state', 0)
    auto_unlock_time = data.get('auto_unlock_time', '06:00')
    user_id = session.get('user_id')
    result = toggle_system_lock(lock_state, auto_unlock_time, user_id)
    if result:
        status = "បិទ" if lock_state == 1 else "បើក"
        return jsonify({'success': True, 'message': f'✅ បាន{status}ប្រព័ន្ធចូលធ្វើការជោគជ័យ!'})
    return jsonify({'success': False, 'message': '❌ មិនអាចប្តូរស្ថានភាពបាន!'})

@app.route('/get_user_lock/<int:user_id>')
def get_user_lock_route(user_id):
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    lock = get_user_lock_status(user_id)
    return jsonify(lock)

@app.route('/get_all_user_locks')
def get_all_user_locks_route():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify([]), 403
    locks = get_all_user_lock_status()
    return jsonify(locks)

@app.route('/toggle_user_lock', methods=['POST'])
def toggle_user_lock_route():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'អ្នកមិនមែនជា Admin!'})
    data = request.get_json()
    user_id = data.get('user_id')
    lock_state = data.get('lock_state', 0)
    auto_unlock_time = data.get('auto_unlock_time', '')
    admin_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'មិនមាន user_id!'})
    if auto_unlock_time:
        try:
            datetime.strptime(auto_unlock_time, '%H:%M')
        except ValueError:
            return jsonify({'success': False, 'message': 'ទ្រង់ទ្រាយម៉ោងមិនត្រឹមត្រូវ! សូមប្រើ HH:MM'})
    if user_id == admin_id:
        return jsonify({'success': False, 'message': '❌ អ្នកមិនអាចបិទគណនីរបស់ខ្លួនឯងបានទេ!'})
    result = toggle_user_lock(user_id, lock_state, auto_unlock_time if auto_unlock_time else None, admin_id)
    if result:
        user = get_user_by_id(user_id)
        status = "បិទ" if lock_state == 1 else "បើក"
        return jsonify({'success': True, 'message': f'✅ បាន{status}ការចូលធ្វើការរបស់ {user["full_name"]} ជោគជ័យ!'})
    return jsonify({'success': False, 'message': '❌ មិនអាចប្តូរស្ថានភាពបាន!'})

@app.route('/check_in', methods=['POST'])
def check_in_route():
    try:
        if not session.get('logged_in'):
            return jsonify({'success': False, 'message': 'មិនទាន់ Login'})
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': 'មិនមាន user_id ក្នុង Session'})
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'មិនមានទិន្នន័យផ្ញើមក'})
        user_lat = data.get('user_lat')
        user_lng = data.get('user_lng')
        company_lat = data.get('company_lat')
        company_lng = data.get('company_lng')
        shift = data.get('shift', 1)
        if user_lat is None or user_lng is None:
            return jsonify({'success': False, 'message': 'មិនមានទីតាំងរបស់អ្នក!'})
        if company_lat is None or company_lng is None:
            return jsonify({'success': False, 'message': 'សូមឲ្យ Admin កំណត់ទីតាំងក្រុមហ៊ុនជាមុនសិន!'})
        allowed, lock_message = check_system_lock_for_user(user_id)
        if not allowed:
            return jsonify({'success': False, 'message': lock_message})
        allowed, user_lock_message = check_user_lock(user_id)
        if not allowed:
            return jsonify({'success': False, 'message': user_lock_message})
        can_checkin, deadline = check_attendance_deadline(user_id)
        if not can_checkin:
            system_lock = get_system_lock_status()
            auto_unlock = system_lock.get('auto_unlock_time', '06:00')
            update_user_lock(user_id, 1, auto_unlock_time=auto_unlock)
            increment_data_version()
            return jsonify({'success': False, 'message': f'⛔ អ្នកលើសម៉ោងដែល Admin បានកំណត់ (ម៉ោងកំណត់: {deadline})! ប្រព័ន្ធបានបិទការចូលធ្វើការរបស់អ្នកដោយស្វ័យប្រវត្តិ!'})
        distance = haversine_distance(user_lat, user_lng, company_lat, company_lng)
        allowed_distance = app.config['ALLOWED_DISTANCE']
        if distance > allowed_distance:
            return jsonify({'success': False, 'message': f'អ្នកនៅឆ្ងាយពីទីតាំងក្រុមហ៊ុន {round(distance, 2)} ម៉ែត្រ (អនុញ្ញាតត្រឹម {allowed_distance} ម៉ែត្រ)! មិនអាចចូលធ្វើការបាន!'})
        status = get_checkin_status(user_id)
        if status['has_checkin']:
            return jsonify({'success': False, 'message': 'អ្នកបានចូលធ្វើការរួចហើយ! សូមចុច "ចេញពីធ្វើការ" មុនពេលចូលម្តងទៀត!'})
        result, message = check_in(user_id, user_lat, user_lng, distance, shift)
        if result:
            shift_names = {1: 'វគ្គ 1 (ព្រឹក)', 2: 'វគ្គ 2 (រសៀល)', 3: 'វគ្គ 3 (យប់)'}
            return jsonify({'success': True, 'message': f'✅ {message} ({shift_names.get(shift, "វគ្គ " + str(shift))}) (ចម្ងាយ {round(distance, 2)} ម៉ែត្រ)'})
        else:
            return jsonify({'success': False, 'message': '❌ ' + message})
    except Exception as e:
        print(f"Error in check_in: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'កំហុស: {str(e)}'})

@app.route('/check_out', methods=['POST'])
def check_out_route():
    try:
        if not session.get('logged_in'):
            return jsonify({'success': False, 'message': 'មិនទាន់ Login'})
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': 'មិនមាន user_id ក្នុង Session'})
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'មិនមានទិន្នន័យផ្ញើមក'})
        user_lat = data.get('user_lat')
        user_lng = data.get('user_lng')
        company_lat = data.get('company_lat')
        company_lng = data.get('company_lng')
        if user_lat is None or user_lng is None:
            return jsonify({'success': False, 'message': 'មិនមានទីតាំងរបស់អ្នក!'})
        if company_lat is None or company_lng is None:
            return jsonify({'success': False, 'message': 'សូមឲ្យ Admin កំណត់ទីតាំងក្រុមហ៊ុនជាមុនសិន!'})
        allowed, lock_message = check_system_lock_for_user(user_id)
        if not allowed:
            return jsonify({'success': False, 'message': lock_message})
        allowed, user_lock_message = check_user_lock(user_id)
        if not allowed:
            return jsonify({'success': False, 'message': user_lock_message})
        distance = haversine_distance(user_lat, user_lng, company_lat, company_lng)
        allowed_distance = app.config['ALLOWED_DISTANCE']
        if distance > allowed_distance:
            return jsonify({'success': False, 'message': f'អ្នកនៅឆ្ងាយពីទីតាំងក្រុមហ៊ុន {round(distance, 2)} ម៉ែត្រ (អនុញ្ញាតត្រឹម {allowed_distance} ម៉ែត្រ)! មិនអាចចេញធ្វើការបាន!'})
        status = get_checkin_status(user_id)
        if not status['has_checkin']:
            return jsonify({'success': False, 'message': 'អ្នកមិនទាន់ចូលធ្វើការនៅថ្ងៃនេះទេ!'})
        result, message = check_out(user_id, user_lat, user_lng, distance)
        if result:
            return jsonify({'success': True, 'message': '✅ ' + message})
        else:
            return jsonify({'success': False, 'message': '❌ ' + message})
    except Exception as e:
        print(f"Error in check_out: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'កំហុស: {str(e)}'})

@app.route('/get_company_location')
def get_company_location_route():
    location = get_company_location()
    if location:
        return jsonify({'lat': location['lat'], 'lng': location['lng']})
    return jsonify({'lat': None, 'lng': None})

@app.route('/save_location', methods=['POST'])
def save_location():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'មិនទាន់ Login'})
    data = request.get_json()
    lat = data.get('lat')
    lng = data.get('lng')
    if lat is None or lng is None:
        return jsonify({'success': False, 'message': 'ទិន្នន័យមិនត្រឹមត្រូវ'})
    result = save_company_location(lat, lng)
    if result:
        return jsonify({'success': True, 'message': 'រក្សាទុកជោគជ័យ'})
    return jsonify({'success': False, 'message': 'មិនអាចរក្សាទុកបាន'})

@app.route('/register', methods=['GET', 'POST'])
def register():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    message = ''
    message_type = ''
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        role = request.form.get('role')
        if not username or not password or not full_name:
            message = 'សូមបំពេញព័ត៌មានឲ្យបានពេញលេញ!'
            message_type = 'error'
        elif password != confirm_password:
            message = 'ពាក្យសម្ងាត់មិនត្រូវគ្នា!'
            message_type = 'error'
        elif len(password) < 4:
            message = 'ពាក្យសម្ងាត់ត្រូវមានយ៉ាងតិច 4 តួ!'
            message_type = 'error'
        else:
            if create_user(username, password, full_name, email, phone, role):
                message = f'✅ ចុះឈ្មោះអ្នកប្រើ "{username}" ជោគជ័យ!'
                message_type = 'success'
            else:
                message = f'❌ ឈ្មោះអ្នកប្រើ "{username}" មានរួចហើយ!'
                message_type = 'error'
    return render_template_string(REGISTER_HTML, session=session, message=message, message_type=message_type)

@app.route('/manage_users')
def manage_users():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    users = get_all_users()
    settings = get_all_attendance_settings()
    settings_dict = {s.get('user_id'): s for s in settings}
    user_locks = get_all_user_lock_status()
    user_locks_dict = {u.get('id'): u for u in user_locks}
    return render_template_string(USER_MANAGEMENT_HTML,
                                   session=session,
                                   users=users,
                                   settings=settings_dict,
                                   user_locks=user_locks_dict,
                                   message='',
                                   message_type='')

@app.route('/get_user/<int:user_id>')
def get_user(user_id):
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({'id': user.get('id', str(user.get('_id'))), 'username': user['username'], 'full_name': user['full_name'], 'email': user.get('email') or '', 'phone': user.get('phone') or '', 'role': user.get('role')})

@app.route('/get_attendance_setting/<int:user_id>')
def get_attendance_setting_route(user_id):
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    setting = get_attendance_setting(user_id)
    if setting:
        return jsonify(setting)
    return jsonify({'user_id': user_id, 'check_in_deadline': '', 'is_active': 0})

@app.route('/save_attendance_setting', methods=['POST'])
def save_attendance_setting_route():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'អ្នកមិនមែនជា Admin!'})
    data = request.get_json()
    user_id = data.get('user_id')
    check_in_deadline = data.get('check_in_deadline', '').strip()
    is_active = data.get('is_active', 0)
    if not user_id:
        return jsonify({'success': False, 'message': 'មិនមាន user_id!'})
    if check_in_deadline:
        try:
            datetime.strptime(check_in_deadline, '%H:%M')
        except ValueError:
            return jsonify({'success': False, 'message': 'ទ្រង់ទ្រាយម៉ោងមិនត្រឹមត្រូវ! សូមប្រើ HH:MM (ឧទាហរណ៍: 08:00)'})
    result = save_attendance_setting(user_id, check_in_deadline, int(is_active))
    if result:
        return jsonify({'success': True, 'message': '✅ រក្សាទុកការកំណត់ជោគជ័យ!'})
    return jsonify({'success': False, 'message': '❌ មិនអាចរក្សាទុកបាន!'})

@app.route('/update_user/<int:user_id>', methods=['POST'])
def update_user_route(user_id):
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'អ្នកមិនមែនជា Admin!'})
    data = request.get_json()
    result = update_user(user_id, data.get('username'), data.get('full_name'), data.get('email'), data.get('phone'), data.get('role'))
    if result:
        return jsonify({'success': True, 'message': '✅ កែប្រែអ្នកប្រើជោគជ័យ!'})
    return jsonify({'success': False, 'message': '❌ មិនអាចកែប្រែបាន!'})

@app.route('/add_user', methods=['POST'])
def add_user_route():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'អ្នកមិនមែនជា Admin!'})
    data = request.get_json()
    if create_user(data.get('username'), data.get('password'), data.get('full_name'), data.get('email'), data.get('phone'), data.get('role')):
        return jsonify({'success': True, 'message': f'✅ បានបន្ថែមអ្នកប្រើ "{data.get("username")}" ជោគជ័យ!'})
    return jsonify({'success': False, 'message': '❌ ឈ្មោះអ្នកប្រើមានរួចហើយ!'})

@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user_route(user_id):
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'អ្នកមិនមែនជា Admin!'})
    if user_id == session.get('user_id'):
        return jsonify({'success': False, 'message': '❌ អ្នកមិនអាចលុបគណនីរបស់ខ្លួនឯងបានទេ!'})
    if delete_user(user_id):
        return jsonify({'success': True, 'message': '✅ លុបអ្នកប្រើជោគជ័យ!'})
    return jsonify({'success': False, 'message': '❌ មិនអាចលុបបាន!'})

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    message = ''
    message_type = ''
    user_id = session.get('user_id')
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if not current_password or not new_password or not confirm_password:
            message = 'សូមបំពេញព័ត៌មានឲ្យបានពេញលេញ!'
            message_type = 'error'
        elif new_password != confirm_password:
            message = 'ពាក្យសម្ងាត់ថ្មីមិនត្រូវគ្នា!'
            message_type = 'error'
        elif len(new_password) < 4:
            message = 'ពាក្យសម្ងាត់ថ្មីត្រូវមានយ៉ាងតិច 4 តួ!'
            message_type = 'error'
        elif not verify_password(user_id, current_password):
            message = 'ពាក្យសម្ងាត់បច្ចុប្បន្នមិនត្រឹមត្រូវ!'
            message_type = 'error'
        else:
            if update_password(user_id, new_password):
                message = '✅ បានប្តូរពាក្យសម្ងាត់ជោគជ័យ!'
                message_type = 'success'
            else:
                message = '❌ មិនអាចប្តូរពាក្យសម្ងាត់បាន!'
                message_type = 'error'
    return render_template_string(CHANGE_PASSWORD_HTML, session=session, message=message, message_type=message_type)

@app.route('/admin_reset_password/<int:user_id>', methods=['POST'])
def admin_reset_password(user_id):
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'អ្នកមិនមែនជា Admin!'})
    data = request.get_json()
    new_password = data.get('new_password')
    if not new_password or len(new_password) < 4:
        return jsonify({'success': False, 'message': 'ពាក្យសម្ងាត់ត្រូវមានយ៉ាងតិច 4 តួ!'})
    if update_password(user_id, new_password):
        return jsonify({'success': True, 'message': '✅ បានកំណត់ពាក្យសម្ងាត់ថ្មីជោគជ័យ!'})
    return jsonify({'success': False, 'message': '❌ មិនអាចកំណត់ពាក្យសម្ងាត់បាន!'})

@app.route('/clean_data', methods=['POST'])
def clean_data():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'អ្នកមិនមែនជា Admin!'})
    data = request.get_json()
    clean_type = data.get('type', 'all')
    if clean_type == 'all':
        result = clean_all_data()
        message = '✅ បានសម្អាតទិន្នន័យទាំងអស់ជោគជ័យ!'
    elif clean_type == 'attendance':
        result = clean_attendance_only()
        message = '✅ បានសម្អាតទិន្នន័យវត្តមានជោគជ័យ!'
    elif clean_type == 'leaves':
        result = clean_leaves_only()
        message = '✅ បានសម្អាតទិន្នន័យសុំច្បាប់ជោគជ័យ!'
    elif clean_type == 'missions':
        result = clean_missions_only()
        message = '✅ បានសម្អាតទិន្នន័យបេសកម្មជោគជ័យ!'
    else:
        return jsonify({'success': False, 'message': 'ប្រភេទមិនត្រឹមត្រូវ!'})
    if result:
        return jsonify({'success': True, 'message': message})
    return jsonify({'success': False, 'message': '❌ មិនអាចសម្អាតទិន្នន័យបាន!'})

@app.route('/request_leave', methods=['POST'])
def request_leave():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'មិនទាន់ Login'})
    user_id = session.get('user_id')
    attachment = None
    if 'attachment' in request.files:
        file = request.files['attachment']
        attachment = save_uploaded_file(file, user_id, 'leave')
    if request.is_json:
        data = request.get_json()
        result = create_leave(user_id, data.get('start_date'), data.get('end_date'), data.get('days'), data.get('reason', ''), attachment)
        days = data.get('days')
    else:
        result = create_leave(user_id, request.form.get('start_date'), request.form.get('end_date'), request.form.get('days'), request.form.get('reason', ''), attachment)
        days = request.form.get('days')
    if result:
        return jsonify({'success': True, 'message': f'✅ បានសុំច្បាប់ {days} ថ្ងៃរួចហើយ! រង់ចាំការអនុម័តពី Admin'})
    return jsonify({'success': False, 'message': '❌ មិនអាចសុំច្បាប់បាន!'})

@app.route('/request_mission', methods=['POST'])
def request_mission():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'មិនទាន់ Login'})
    user_id = session.get('user_id')
    attachment = None
    if 'attachment' in request.files:
        file = request.files['attachment']
        attachment = save_uploaded_file(file, user_id, 'mission')
    if request.is_json:
        data = request.get_json()
        result = create_mission(user_id, data.get('start_date'), data.get('end_date'), data.get('days'), data.get('destination', ''), data.get('purpose', ''), attachment)
        days = data.get('days')
    else:
        result = create_mission(user_id, request.form.get('start_date'), request.form.get('end_date'), request.form.get('days'), request.form.get('destination', ''), request.form.get('purpose', ''), attachment)
        days = request.form.get('days')
    if result:
        return jsonify({'success': True, 'message': f'✅ បានសុំបេសកម្ម {days} ថ្ងៃរួចហើយ! រង់ចាំការអនុម័តពី Admin'})
    return jsonify({'success': False, 'message': '❌ មិនអាចសុំបេសកម្មបាន!'})

@app.route('/get_pending_requests')
def get_pending_requests():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'leaves': [], 'missions': []})
    leaves = get_pending_leaves()
    missions = get_pending_missions()
    return jsonify({'leaves': leaves, 'missions': missions})

@app.route('/check_new_requests')
def check_new_requests():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'new': False, 'count': 0, 'message': ''})
    pending_leaves = get_pending_leaves()
    pending_missions = get_pending_missions()
    total_pending = len(pending_leaves) + len(pending_missions)
    last_count = session.get('last_pending_count', 0)
    is_new = total_pending > last_count
    session['last_pending_count'] = total_pending
    message = ''
    if is_new and total_pending > 0:
        new_count = total_pending - last_count
        message = f'📬 មានសំណើថ្មី {new_count} ករណី! សូមចុច "📬 សំណើ" ដើម្បីអនុម័ត'
    return jsonify({'new': is_new, 'count': total_pending, 'message': message})

@app.route('/approve_request', methods=['POST'])
def approve_request():
    try:
        if not session.get('logged_in'):
            return jsonify({'success': False, 'message': 'សូម Login ជាមុន!'})
        if session.get('role') != 'admin':
            return jsonify({'success': False, 'message': 'អ្នកមិនមែនជា Admin!'})
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'មិនមានទិន្នន័យផ្ញើមក!'})
        req_type = data.get('type')
        req_id = data.get('id')
        admin_id = session.get('user_id')
        if req_type == 'leave':
            result = approve_leave(req_id, admin_id)
        elif req_type == 'mission':
            result = approve_mission(req_id, admin_id)
        else:
            return jsonify({'success': False, 'message': 'ប្រភេទមិនត្រឹមត្រូវ'})
        if result:
            return jsonify({'success': True, 'message': '✅ បានអនុម័តជោគជ័យ!'})
        return jsonify({'success': False, 'message': '❌ មិនអាចអនុម័តបាន!'})
    except Exception as e:
        print(f"❌ Error in approve_request: {e}")
        return jsonify({'success': False, 'message': f'កំហុស: {str(e)}'})

@app.route('/reject_request', methods=['POST'])
def reject_request():
    try:
        if not session.get('logged_in'):
            return jsonify({'success': False, 'message': 'សូម Login ជាមុន!'})
        if session.get('role') != 'admin':
            return jsonify({'success': False, 'message': 'អ្នកមិនមែនជា Admin!'})
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'មិនមានទិន្នន័យផ្ញើមក!'})
        req_type = data.get('type')
        req_id = data.get('id')
        if req_type == 'leave':
            result = reject_leave(req_id)
        elif req_type == 'mission':
            result = reject_mission(req_id)
        else:
            return jsonify({'success': False, 'message': 'ប្រភេទមិនត្រឹមត្រូវ'})
        if result:
            return jsonify({'success': True, 'message': '✅ បានបដិសេធជោគជ័យ!'})
        return jsonify({'success': False, 'message': '❌ មិនអាចបដិសេធបាន!'})
    except Exception as e:
        print(f"❌ Error in reject_request: {e}")
        return jsonify({'success': False, 'message': f'កំហុស: {str(e)}'})

@app.route('/report')
def report():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    month = request.args.get('month')
    year = request.args.get('year')
    current_year = datetime.now().year
    if month and year:
        month = int(month)
        year = int(year)
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year}-12-31"
        else:
            next_month = month + 1
            end_dt = datetime(year, next_month, 1) - timedelta(days=1)
            end_date = end_dt.strftime('%Y-%m-%d')
    elif start_date and end_date:
        pass
    else:
        today = datetime.now()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    result = get_attendance_report(start_date, end_date)
    daily_data = result.get('daily', [])
    summary_data = result.get('summary', [])
    return render_template_string(REPORT_HTML,
                                   session=session,
                                   daily=daily_data,
                                   summary=summary_data,
                                   start_date=start_date,
                                   end_date=end_date,
                                   current_year=current_year,
                                   user_role=session.get('role', 'user'))

@app.route('/export_excel')
def export_excel():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    month = request.args.get('month')
    year = request.args.get('year')
    if month and year:
        month = int(month)
        year = int(year)
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year}-12-31"
        else:
            next_month = month + 1
            end_dt = datetime(year, next_month, 1) - timedelta(days=1)
            end_date = end_dt.strftime('%Y-%m-%d')
    elif start_date and end_date:
        pass
    else:
        today = datetime.now()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    result = get_attendance_report(start_date, end_date)
    daily_data = result.get('daily', [])
    summary_data = result.get('summary', [])
    
    # ... (Excel export code - same as your original) ...
    # ចម្លងកូដ export_excel ពីកូដចាស់របស់អ្នកមកទីនេះ
    
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/check_auto_unlock')
def check_auto_unlock():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    try:
        current_time = get_current_time_only()[:5]
        unlocked_items = []
        lock = get_system_lock_status()
        if lock.get('is_locked', 0) == 1:
            auto_unlock = lock.get('auto_unlock_time')
            if auto_unlock and current_time >= auto_unlock:
                update_system_lock(0, locked_by=None)
                unlocked_items.append('system')
        all_users = get_all_users()
        for user in all_users:
            if user.get('role') == 'admin':
                continue
            user_id = str(user.get('id', user.get('_id')))
            user_lock = get_user_lock_status(user_id)
            if user_lock.get('is_locked', 0) == 1:
                auto_unlock = user_lock.get('auto_unlock_time')
                if auto_unlock and current_time >= auto_unlock:
                    update_user_lock(user_id, 0)
                    unlocked_items.append(f"user_{user_id}")
        if unlocked_items:
            increment_data_version()
            return jsonify({'success': True, 'message': f'Auto-unlocked: {", ".join(unlocked_items)}', 'unlocked': unlocked_items})
        else:
            return jsonify({'success': True, 'message': 'No auto-unlock needed at this time', 'unlocked': []})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/static/manifest.json')
def manifest():
    return {
        "name": "ប្រព័ន្ធគ្រប់គ្រងបុគ្គលិក",
        "short_name": "HR System",
        "start_url": "/dashboard",
        "display": "standalone",
        "background_color": "#1a73e8",
        "theme_color": "#1a73e8",
        "orientation": "portrait",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
        ]
    }

@app.route('/static/sw.js')
def service_worker():
    return '''...''' # same as your original

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/edit_attendance/<int:attendance_id>', methods=['GET', 'POST'])
def edit_attendance(attendance_id):
    # ... same as your original ...

@app.route('/delete_attendance/<int:attendance_id>', methods=['POST'])
def delete_attendance_route(attendance_id):
    # ... same as your original ...

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(os.path.join('static', 'uploads'), filename)

@app.route('/login', methods=['GET', 'POST'])
def login():
    # ... same as your original ...

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ============================================================
# HTML TEMPLATES - ដាក់នៅទីនេះ
# ============================================================

DASHBOARD_HTML = r'''...'''  # ចម្លងពីកូដចាស់
REGISTER_HTML = r'''...'''   # ចម្លងពីកូដចាស់
CHANGE_PASSWORD_HTML = r'''...'''  # ចម្លងពីកូដចាស់
USER_MANAGEMENT_HTML = r'''...'''  # ចម្លងពីកូដចាស់
REPORT_HTML = r'''...'''     # ចម្លងពីកូដចាស់

# ============================================================
# MAIN
# ============================================================

with app.app_context():
    try:
        init_db()
        print("✅ Database initialized successfully!")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
