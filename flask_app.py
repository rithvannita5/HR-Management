import os
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, 
    url_for, flash, jsonify, session
)

# Import មុខងារទាំងអស់ចេញពី mongo_db.py
import mongo_db as db

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'my_secret_key_attendance_2026')

# បង្កើត Database Index ពេលចាប់ផ្ដើម App
db.init_db()


# ============================================================
# AUTHENTICATION DECORATORS
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("សូមចូលប្រើប្រាស់ប្រព័ន្ធជាមុនសិន!", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("សូមចូលប្រើប្រាស់ប្រព័ន្ធជាមុនសិន!", "warning")
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash("អ្នកមិនមានសិទ្ធិចូលប្រើប្រាស់ទំព័រនេះទេ!", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# AUTHENTICATION ROUTES
# ============================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        user = db.get_user_by_username(username)
        if user and user.get('password') == password:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user.get('role', 'user')
            flash("ចូលប្រព័ន្ធជោគជ័យ!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("ឈ្មោះអ្នកប្រើប្រាស់ ឬពាក្យសម្ងាត់មិនត្រឹមត្រូវទេ!", "danger")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("ចាកចេញពីប្រព័ន្ធជោគជ័យ!", "info")
    return redirect(url_for('login'))


# ============================================================
# DASHBOARD & MAIN ROUTES
# ============================================================

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    stats = db.get_attendance_stats()
    checkin_status = db.get_checkin_status(user_id)
    system_lock = db.get_system_lock_status()
    user_lock = db.get_user_lock_status(user_id)
    company_loc = db.get_company_location()

    return render_template(
        'dashboard.html',
        stats=stats,
        checkin_status=checkin_status,
        system_lock=system_lock,
        user_lock=user_lock,
        company_loc=company_loc
    )


# ============================================================
# ATTENDANCE ACTION ROUTES (API / JSON)
# ============================================================

@app.route('/checkin', methods=['POST'])
@login_required
def check_in():
    user_id = session['user_id']
    
    # ពិនិត្យ System Lock
    sys_ok, sys_msg = db.check_system_lock_for_user(user_id)
    if not sys_ok:
        return jsonify({"success": False, "message": sys_msg})

    # ពិនិត្យ User Lock
    usr_ok, usr_msg = db.check_user_lock(user_id)
    if not usr_ok:
        return jsonify({"success": False, "message": usr_msg})

    data = request.get_json() or {}
    lat = data.get('lat', 0.0)
    lng = data.get('lng', 0.0)
    distance = data.get('distance', 0.0)
    shift = data.get('shift', 1)

    success, message = db.check_in(user_id, lat, lng, distance, shift)
    return jsonify({"success": success, "message": message})

@app.route('/checkout', methods=['POST'])
@login_required
def check_out():
    user_id = session['user_id']
    data = request.get_json() or {}
    lat = data.get('lat', 0.0)
    lng = data.get('lng', 0.0)
    distance = data.get('distance', 0.0)

    success, message = db.check_out(user_id, lat, lng, distance)
    return jsonify({"success": success, "message": message})


# ============================================================
# LEAVE & MISSION REQUEST ROUTES
# ============================================================

@app.route('/leave/request', methods=['POST'])
@login_required
def request_leave():
    user_id = session['user_id']
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    days = request.form.get('days', 1)
    reason = request.form.get('reason')

    if start_date and end_date and reason:
        db.create_leave(user_id, start_date, end_date, days, reason)
        flash("ផ្ញើការស្នើសុំច្បាប់បានជោគជ័យ!", "success")
    else:
        flash("សូមបំពេញព័ត៌មានស្នើសុំឲ្យបានគ្រប់គ្រាន់!", "danger")

    return redirect(url_for('dashboard'))

@app.route('/mission/request', methods=['POST'])
@login_required
def request_mission():
    user_id = session['user_id']
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    days = request.form.get('days', 1)
    destination = request.form.get('destination')

    if start_date and end_date and destination:
        db.create_mission(user_id, start_date, end_date, days, destination)
        flash("ផ្ញើការស្នើសុំបេសកកម្មបានជោគជ័យ!", "success")
    else:
        flash("សូមបំពេញព័ត៌មានស្នើសុំឲ្យបានគ្រប់គ្រាន់!", "danger")

    return redirect(url_for('dashboard'))


# ============================================================
# ADMIN - USER MANAGEMENT
# ============================================================

@app.route('/admin/users', methods=['GET', 'POST'])
@admin_required
def manage_users():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        role = request.form.get('role', 'user')

        if db.create_user(username, password, full_name, email, phone, role):
            flash("បង្កើតអ្នកប្រើប្រាស់ថ្មីជោគជ័យ!", "success")
        else:
            flash("ឈ្មោះអ្នកប្រើប្រាស់នេះមានរួចហើយនៅក្នុងប្រព័ន្ធ!", "danger")

    users = db.get_all_users()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/update/<user_id>', methods=['POST'])
@admin_required
def update_user(user_id):
    username = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    role = request.form.get('role', 'user')

    if db.update_user(user_id, username, full_name, email, phone, role):
        flash("កែប្រែព័ត៌មានអ្នកប្រើប្រាស់ជោគជ័យ!", "success")
    else:
        flash("មានបញ្ហាក្នុងការកែប្រែ ឬឈ្មោះអ្នកប្រើប្រាស់ជាន់គ្នា!", "danger")

    return redirect(url_for('manage_users'))

@app.route('/admin/users/password/<user_id>', methods=['POST'])
@admin_required
def change_user_password(user_id):
    new_password = request.form.get('new_password', '').strip()
    if new_password and db.update_password(user_id, new_password):
        flash("ប្ដូរពាក្យសម្ងាត់ជោគជ័យ!", "success")
    else:
        flash("មានបញ្ហាក្នុងការប្ដូរពាក្យសម្ងាត់!", "danger")

    return redirect(url_for('manage_users'))

@app.route('/admin/users/delete/<user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    if db.delete_user(user_id):
        flash("លុបអ្នកប្រើប្រាស់ និងទិន្នន័យពាក់ព័ន្ធជោគជ័យ!", "success")
    else:
        flash("មានបញ្ហាក្នុងការលុបអ្នកប្រើប្រាស់!", "danger")

    return redirect(url_for('manage_users'))


# ============================================================
# ADMIN - LOCK & LOCATION CONTROLS
# ============================================================

@app.route('/admin/locks')
@admin_required
def lock_management():
    system_lock = db.get_system_lock_status()
    user_locks = db.get_all_user_lock_status()
    return render_template('admin_locks.html', system_lock=system_lock, user_locks=user_locks)

@app.route('/admin/system-lock', methods=['POST'])
@admin_required
def toggle_system_lock():
    data = request.get_json() or {}
    lock_state = data.get('is_locked', 0)
    auto_unlock = data.get('auto_unlock_time')

    db.toggle_system_lock(
        lock_state, 
        auto_unlock_time=auto_unlock, 
        locked_by=session.get('username')
    )
    return jsonify({"success": True, "message": "ប្ដូរស្ថានភាព System Lock រួចរាល់!"})

@app.route('/admin/user-lock', methods=['POST'])
@admin_required
def toggle_user_lock():
    data = request.get_json() or {}
    user_id = data.get('user_id')
    is_locked = data.get('is_locked', 0)
    auto_unlock = data.get('auto_unlock_time')

    db.update_user_lock(
        user_id, 
        is_locked, 
        auto_unlock_time=auto_unlock, 
        locked_by=session.get('username')
    )
    return jsonify({"success": True, "message": "ប្ដូរស្ថានភាព User Lock រួចរាល់!"})

@app.route('/admin/company-location', methods=['POST'])
@admin_required
def set_company_location():
    lat = request.form.get('lat')
    lng = request.form.get('lng')

    if lat and lng:
        db.save_company_location(lat, lng)
        flash("កំណត់ទីតាំងក្រុមហ៊ុនជោគជ័យ!", "success")
    else:
        flash("សូមបញ្ចូល Lat និង Lng ឲ្យបានត្រឹមត្រូវ!", "danger")

    return redirect(url_for('dashboard'))


# ============================================================
# ADMIN - LEAVE & MISSION APPROVALS
# ============================================================

@app.route('/admin/approvals')
@admin_required
def manage_approvals():
    pending_leaves = db.get_pending_leaves()
    pending_missions = db.get_pending_missions()
    return render_template('admin_approvals.html', leaves=pending_leaves, missions=pending_missions)

@app.route('/admin/leave/approve/<leave_id>', methods=['POST'])
@admin_required
def approve_leave(leave_id):
    db.approve_leave(leave_id)
    flash("បានអនុម័តការច្បាប់!", "success")
    return redirect(url_for('manage_approvals'))

@app.route('/admin/leave/reject/<leave_id>', methods=['POST'])
@admin_required
def reject_leave(leave_id):
    db.reject_leave(leave_id)
    flash("បានបដិសេធការច្បាប់!", "info")
    return redirect(url_for('manage_approvals'))

@app.route('/admin/mission/approve/<mission_id>', methods=['POST'])
@admin_required
def approve_mission(mission_id):
    db.approve_mission(mission_id)
    flash("បានអនុម័តបេសកកម្ម!", "success")
    return redirect(url_for('manage_approvals'))

@app.route('/admin/mission/reject/<mission_id>', methods=['POST'])
@admin_required
def reject_mission(mission_id):
    db.reject_mission(mission_id)
    flash("បានបដិសេធបេសកកម្ម!", "info")
    return redirect(url_for('manage_approvals'))


# ============================================================
# ADMIN - ATTENDANCE SETTINGS & DEADLINES
# ============================================================

@app.route('/admin/attendance-settings', methods=['GET', 'POST'])
@admin_required
def attendance_settings():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        deadline = request.form.get('check_in_deadline')
        is_active = request.form.get('is_active', 1)

        db.save_attendance_setting(user_id, deadline, is_active)
        flash("រក្សាទុកកំណត់ម៉ោង Deadline រួចរាល់!", "success")

    users = db.get_all_users()
    settings = db.get_all_attendance_settings()
    return render_template('admin_attendance_settings.html', users=users, settings=settings)


# ============================================================
# REPORTS & DATA CLEANING
# ============================================================

@app.route('/reports/work-history')
@login_required
def work_history_report():
    start_date = request.args.get('start_date', datetime.now().replace(day=1).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))

    report_data = db.get_work_history_report(start_date, end_date)
    return render_template('report_work_history.html', report_data=report_data, start_date=start_date, end_date=end_date)

@app.route('/reports/monthly-summary')
@admin_required
def monthly_summary_report():
    start_date = request.args.get('start_date', datetime.now().replace(day=1).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))

    summary_data = db.get_monthly_summary_report(start_date, end_date)
    return render_template('report_monthly_summary.html', summary_data=summary_data, start_date=start_date, end_date=end_date)

@app.route('/admin/clean-data', methods=['POST'])
@admin_required
def clean_data():
    clean_type = request.form.get('clean_type')

    if clean_type == 'attendance':
        db.clean_attendance_only()
        flash("បានលុបទិន្នន័យវត្តមានទាំងអស់!", "success")
    elif clean_type == 'leaves':
        db.clean_leaves_only()
        flash("បានលុបទិន្នន័យច្បាប់ទាំងអស់!", "success")
    elif clean_type == 'missions':
        db.clean_missions_only()
        flash("បានលុបទិន្នន័យបេសកកម្មទាំងអស់!", "success")
    elif clean_type == 'all':
        db.clean_all_data()
        flash("បានលុបទិន្នន័យចាស់ៗទាំងអស់សម្អាតស្អាត!", "success")

    return redirect(url_for('dashboard'))


# ============================================================
# REAL-TIME API SYNC
# ============================================================

@app.route('/api/data-version')
def get_data_version():
    """ ប្រើសម្រាប់ឲ្យ Mobile ឬ Frontend ឆែកមើលថាមាន Data ថ្មីដែរឬទេ """
    return jsonify({"version": db.get_data_version()})


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
