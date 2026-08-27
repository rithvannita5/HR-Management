import os
import pytz
from datetime import datetime, timedelta
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson.objectid import ObjectId

# ============================================================
# MONGODB CONNECTION SETUP
# ============================================================

MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
DB_NAME = os.environ.get('MONGO_DB_NAME', 'attendance_system')

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# Collections
users_col = db['users']
attendance_col = db['attendance']
leaves_col = db['leaves']
missions_col = db['missions']
settings_col = db['attendance_settings']
system_lock_col = db['system_attendance_lock']
user_lock_col = db['user_attendance_lock']
company_location_col = db['company_location']
data_version_col = db['data_version']


def init_db():
    """ Initialize indexes and setup initial data version if needed """
    users_col.create_index([("username", ASCENDING)], unique=True)
    attendance_col.create_index([("user_id", ASCENDING), ("date", ASCENDING)])
    leaves_col.create_index([("user_id", ASCENDING), ("status", ASCENDING)])
    missions_col.create_index([("user_id", ASCENDING), ("status", ASCENDING)])
    settings_col.create_index([("user_id", ASCENDING)], unique=True)
    user_lock_col.create_index([("user_id", ASCENDING)], unique=True)

    if data_version_col.count_documents({}) == 0:
        data_version_col.insert_one({"version": 1})


# ============================================================
# TIME & HELPER FUNCTIONS
# ============================================================

def get_current_datetime():
    tz = pytz.timezone('Asia/Phnom_Penh')
    return datetime.now(tz)

def get_current_date():
    return get_current_datetime().strftime('%Y-%m-%d')

def get_current_time():
    return get_current_datetime().strftime('%Y-%m-%d %H:%M:%S')

def get_current_time_only():
    return get_current_datetime().strftime('%H:%M:%S')

def get_current_datetime_str():
    return get_current_time()

def convert_id(doc):
    """ Utility to convert MongoDB _id to string id for compatibility """
    if not doc:
        return None
    doc['id'] = str(doc['_id'])
    return doc


# ============================================================
# DATA VERSION FUNCTIONS
# ============================================================

def get_data_version():
    ver = data_version_col.find_one({})
    return ver['version'] if ver else 1

def increment_data_version():
    data_version_col.update_one({}, {"$inc": {"version": 1}}, upsert=True)


# ============================================================
# USER FUNCTIONS
# ============================================================

def get_user_by_id(user_id):
    try:
        doc = users_col.find_one({"_id": ObjectId(user_id)})
        return convert_id(doc)
    except Exception:
        return None

def get_user_by_username(username):
    doc = users_col.find_one({"username": username})
    return convert_id(doc)

def create_user(username, password, full_name, email=None, phone=None, role='user'):
    if users_col.find_one({"username": username}):
        return False
    
    users_col.insert_one({
        "username": username,
        "password": password,
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "role": role,
        "created_at": get_current_time()
    })
    increment_data_version()
    return True

def update_user(user_id, username, full_name, email, phone, role):
    try:
        existing = users_col.find_one({"username": username, "_id": {"$ne": ObjectId(user_id)}})
        if existing:
            return False
            
        users_col.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {
                "username": username,
                "full_name": full_name,
                "email": email,
                "phone": phone,
                "role": role
            }}
        )
        increment_data_version()
        return True
    except Exception:
        return False

def update_password(user_id, new_password):
    try:
        users_col.update_one({"_id": ObjectId(user_id)}, {"$set": {"password": new_password}})
        increment_data_version()
        return True
    except Exception:
        return False

def verify_password(user_id, password):
    user = get_user_by_id(user_id)
    return user and user.get('password') == password

def delete_user(user_id):
    try:
        uid_str = str(user_id)
        attendance_col.delete_many({"user_id": uid_str})
        leaves_col.delete_many({"user_id": uid_str})
        missions_col.delete_many({"user_id": uid_str})
        settings_col.delete_many({"user_id": uid_str})
        user_lock_col.delete_many({"user_id": uid_str})
        users_col.delete_one({"_id": ObjectId(user_id)})
        increment_data_version()
        return True
    except Exception:
        return False

def get_all_users():
    docs = list(users_col.find().sort("_id", DESCENDING))
    return [convert_id(doc) for doc in docs]


# ============================================================
# SYSTEM & USER LOCK FUNCTIONS
# ============================================================

def get_system_lock_status():
    doc = system_lock_col.find_one({}, sort=[("_id", DESCENDING)])
    return convert_id(doc) or {'is_locked': 0, 'auto_unlock_time': None}

def update_system_lock(is_locked, lock_start_time=None, lock_end_time=None, auto_unlock_time=None, locked_by=None):
    current = system_lock_col.find_one({}, sort=[("_id", DESCENDING)])
    update_data = {
        "is_locked": int(is_locked),
        "updated_at": get_current_time()
    }
    if lock_start_time: update_data["lock_start_time"] = lock_start_time
    if lock_end_time: update_data["lock_end_time"] = lock_end_time
    if auto_unlock_time: update_data["auto_unlock_time"] = auto_unlock_time
    if locked_by: update_data["locked_by"] = locked_by

    if current:
        system_lock_col.update_one({"_id": current["_id"]}, {"$set": update_data})
    else:
        system_lock_col.insert_one(update_data)

    increment_data_version()
    return True

def toggle_system_lock(lock_state, auto_unlock_time=None, locked_by=None):
    current_time = get_current_time()
    if lock_state == 1:
        lock = get_system_lock_status()
        return update_system_lock(
            is_locked=1,
            lock_start_time=current_time,
            auto_unlock_time=auto_unlock_time or lock.get('auto_unlock_time', '06:00'),
            locked_by=locked_by
        )
    else:
        return update_system_lock(is_locked=0, lock_end_time=current_time, locked_by=locked_by)

def check_system_lock_for_user(user_id):
    lock = get_system_lock_status()
    if lock.get('is_locked', 0) != 1:
        return True, None

    auto_unlock = lock.get('auto_unlock_time')
    if auto_unlock:
        current_hhmm = get_current_time_only()[:5]
        if current_hhmm >= auto_unlock:
            update_system_lock(0, locked_by=None)
            return True, None

    return False, "⛔ ប្រព័ន្ធកំពុងបិទការចូលធ្វើការ! សូមរង់ចាំរហូតដល់ម៉ោងបើកដោយស្វ័យប្រវត្តិ ឬទាក់ទង Admin!"

def get_user_lock_status(user_id):
    doc = user_lock_col.find_one({"user_id": str(user_id)})
    return convert_id(doc) or {'is_locked': 0, 'auto_unlock_time': None}

def update_user_lock(user_id, is_locked, auto_unlock_time=None, locked_by=None):
    uid_str = str(user_id)
    current_time = get_current_time()
    
    update_data = {
        "is_locked": int(is_locked),
        "updated_at": current_time
    }
    if auto_unlock_time: update_data["auto_unlock_time"] = auto_unlock_time
    if locked_by: update_data["locked_by"] = locked_by
    if is_locked == 1:
        update_data["lock_start_time"] = current_time
    else:
        update_data["lock_end_time"] = current_time

    user_lock_col.update_one(
        {"user_id": uid_str},
        {"$set": update_data},
        upsert=True
    )
    increment_data_version()
    return True

def check_user_lock(user_id):
    lock = get_user_lock_status(user_id)
    if lock.get('is_locked', 0) != 1:
        return True, None

    auto_unlock = lock.get('auto_unlock_time')
    if auto_unlock:
        current_hhmm = get_current_time_only()[:5]
        if current_hhmm >= auto_unlock:
            update_user_lock(user_id, 0)
            return True, None

    return False, "⛔ អ្នកត្រូវបានបិទការចូលធ្វើការដោយ Admin! សូមទាក់ទង Admin!"

def get_all_user_lock_status():
    users = get_all_users()
    results = []
    for user in users:
        if user.get('role') == 'admin':
            continue
        uid_str = str(user['id'])
        lock = get_user_lock_status(uid_str)
        results.append({
            "id": user['id'],
            "username": user.get('username'),
            "full_name": user.get('full_name'),
            "is_locked": lock.get('is_locked', 0),
            "auto_unlock_time": lock.get('auto_unlock_time'),
            "lock_start_time": lock.get('lock_start_time'),
            "updated_at": lock.get('updated_at')
        })
    return results


# ============================================================
# ATTENDANCE SETTINGS FUNCTIONS
# ============================================================

def get_attendance_setting(user_id):
    doc = settings_col.find_one({"user_id": str(user_id)})
    return convert_id(doc)

def get_all_attendance_settings():
    settings = list(settings_col.find())
    results = []
    for s in settings:
        s = convert_id(s)
        user = get_user_by_id(s.get('user_id'))
        if user:
            s['username'] = user.get('username')
            s['full_name'] = user.get('full_name')
            results.append(s)
    return results

def save_attendance_setting(user_id, check_in_deadline, is_active):
    settings_col.update_one(
        {"user_id": str(user_id)},
        {"$set": {
            "check_in_deadline": check_in_deadline,
            "is_active": int(is_active),
            "updated_at": get_current_time()
        }},
        upsert=True
    )
    increment_data_version()
    return True

def check_attendance_deadline(user_id):
    setting = get_attendance_setting(user_id)
    if not setting or setting.get('is_active') != 1:
        return True, None

    deadline = setting.get('check_in_deadline')
    if not deadline:
        return True, None

    current_hhmm = get_current_time_only()[:5]
    if current_hhmm > deadline:
        return False, deadline
    return True, deadline


# ============================================================
# ATTENDANCE FUNCTIONS
# ============================================================

def get_company_location():
    doc = company_location_col.find_one({}, sort=[("_id", DESCENDING)])
    return convert_id(doc)

def save_company_location(lat, lng):
    company_location_col.insert_one({"lat": float(lat), "lng": float(lng)})
    increment_data_version()
    return True

def check_in(user_id, lat, lng, distance, shift):
    uid_str = str(user_id)
    existing = attendance_col.find_one({"user_id": uid_str, "check_out": None})
    if existing:
        return False, "អ្នកបានចូលធ្វើការរួចហើយ! សូមចុច 'ចេញពីធ្វើការ' មុនពេលចូលម្តងទៀត!"

    can_checkin, deadline = check_attendance_deadline(user_id)
    if not can_checkin:
        return False, f"⛔ អ្នកលើសម៉ោងដែល Admin បានកំណត់ (ម៉ោងកំណត់: {deadline})! សូមទាក់ទងទៅអ្នកគ្រប់គ្រង!"

    attendance_col.insert_one({
        "user_id": uid_str,
        "date": get_current_date(),
        "check_in": get_current_time(),
        "check_out": None,
        "shift": int(shift),
        "check_in_lat": float(lat),
        "check_in_lng": float(lng),
        "check_in_distance": float(distance),
        "total_hours": 0
    })
    increment_data_version()
    return True, "ចូលធ្វើការជោគជ័យ!"

def check_out(user_id, lat, lng, distance):
    uid_str = str(user_id)
    record = attendance_col.find_one({"user_id": uid_str, "check_out": None}, sort=[("_id", DESCENDING)])
    if not record:
        return False, "មិនមានការចូលធ្វើការដែលមិនទាន់ចេញ!"

    check_out_time = get_current_datetime()
    check_in_time = datetime.strptime(record['check_in'], '%Y-%m-%d %H:%M:%S')
    tz = pytz.timezone('Asia/Phnom_Penh')
    check_in_time = tz.localize(check_in_time)

    if check_out_time <= check_in_time:
        check_out_time = check_out_time + timedelta(days=1)

    diff = check_out_time - check_in_time
    total_hours = round(diff.total_seconds() / 3600, 2)

    attendance_col.update_one(
        {"_id": record["_id"]},
        {"$set": {
            "check_out": check_out_time.strftime('%Y-%m-%d %H:%M:%S'),
            "total_hours": total_hours,
            "check_out_lat": float(lat),
            "check_out_lng": float(lng),
            "check_out_distance": float(distance)
        }}
    )
    increment_data_version()

    shift_names = {1: 'វគ្គ 1 (ព្រឹក)', 2: 'វគ្គ 2 (រសៀល)', 3: 'វគ្គ 3 (យប់)'}
    hours = int(total_hours)
    minutes = int((total_hours - hours) * 60)
    return True, f"ចេញធ្វើការជោគជ័យ! ({shift_names.get(record.get('shift', 1), '')}) ម៉ោងសរុប: {hours:02d}:{minutes:02d}"

def get_attendance_stats():
    today = get_current_date()
    total_users = users_col.count_documents({"role": {"$ne": "admin"}})
    present_today = len(attendance_col.distinct("user_id", {"check_out": None}))
    
    leave_today = len(leaves_col.distinct("user_id", {
        "status": "approved",
        "start_date": {"$lte": today},
        "end_date": {"$gte": today}
    }))
    
    mission_today = len(missions_col.distinct("user_id", {
        "status": "approved",
        "start_date": {"$lte": today},
        "end_date": {"$gte": today}
    }))

    return {
        'total_users': total_users,
        'present_today': present_today,
        'leave_today': leave_today,
        'mission_today': mission_today
    }

def get_checkin_status(user_id):
    record = attendance_col.find_one({"user_id": str(user_id), "check_out": None}, sort=[("_id", DESCENDING)])
    if record:
        return {
            'has_checkin': True,
            'check_in_time': record.get('check_in'),
            'shift': record.get('shift', 1)
        }
    return {'has_checkin': False, 'check_in_time': None, 'shift': None}

def get_attendance_by_id(att_id):
    doc = attendance_col.find_one({"_id": ObjectId(att_id)})
    return convert_id(doc)

def update_attendance(att_id, check_in, check_out, shift):
    update_data = {"shift": int(shift)}
    if check_in: update_data["check_in"] = check_in
    if check_out: update_data["check_out"] = check_out
    
    attendance_col.update_one({"_id": ObjectId(att_id)}, {"$set": update_data})
    increment_data_version()
    return True

def delete_attendance(att_id):
    attendance_col.delete_one({"_id": ObjectId(att_id)})
    increment_data_version()
    return True


# ============================================================
# LEAVES & MISSIONS FUNCTIONS
# ============================================================

def create_leave(user_id, start_date, end_date, days, reason):
    leaves_col.insert_one({
        "user_id": str(user_id),
        "start_date": start_date,
        "end_date": end_date,
        "days": float(days),
        "reason": reason,
        "status": "pending",
        "created_at": get_current_time()
    })
    increment_data_version()
    return True

def get_pending_leaves():
    leaves = list(leaves_col.find({"status": "pending"}))
    results = []
    for l in leaves:
        l = convert_id(l)
        u = get_user_by_id(l['user_id'])
        if u: l['full_name'] = u.get('full_name')
        results.append(l)
    return results

def approve_leave(leave_id):
    leaves_col.update_one({"_id": ObjectId(leave_id)}, {"$set": {"status": "approved"}})
    increment_data_version()
    return True

def reject_leave(leave_id):
    leaves_col.update_one({"_id": ObjectId(leave_id)}, {"$set": {"status": "rejected"}})
    increment_data_version()
    return True

def create_mission(user_id, start_date, end_date, days, destination):
    missions_col.insert_one({
        "user_id": str(user_id),
        "start_date": start_date,
        "end_date": end_date,
        "days": float(days),
        "destination": destination,
        "status": "pending",
        "created_at": get_current_time()
    })
    increment_data_version()
    return True

def get_pending_missions():
    missions = list(missions_col.find({"status": "pending"}))
    results = []
    for m in missions:
        m = convert_id(m)
        u = get_user_by_id(m['user_id'])
        if u: m['full_name'] = u.get('full_name')
        results.append(m)
    return results

def approve_mission(mission_id):
    missions_col.update_one({"_id": ObjectId(mission_id)}, {"$set": {"status": "approved"}})
    increment_data_version()
    return True

def reject_mission(mission_id):
    missions_col.update_one({"_id": ObjectId(mission_id)}, {"$set": {"status": "rejected"}})
    increment_data_version()
    return True


# ============================================================
# CLEAN DATA FUNCTIONS
# ============================================================

def clean_attendance_only():
    attendance_col.delete_many({})
    increment_data_version()
    return True

def clean_leaves_only():
    leaves_col.delete_many({})
    increment_data_version()
    return True

def clean_missions_only():
    missions_col.delete_many({})
    increment_data_version()
    return True
# mongo_db.py - បន្ថែមនៅក្នុងផ្នែក ATTENDANCE FUNCTIONS

def get_all_attendance(limit=100):
    """Get all attendance records"""
    try:
        return list(attendance_collection.find().sort('date', -1).limit(limit))
    except Exception as e:
        print(f"Error in get_all_attendance: {e}")
        return []

def get_attendance_by_id(attendance_id):
    """Get attendance record by ID"""
    try:
        if isinstance(attendance_id, str):
            attendance_id = ObjectId(attendance_id)
        return attendance_collection.find_one({'_id': attendance_id})
    except Exception as e:
        print(f"Error in get_attendance_by_id: {e}")
        return None

def update_attendance(attendance_id, check_in=None, check_out=None, date=None, shift=None):
    """Update attendance record"""
    try:
        if isinstance(attendance_id, str):
            attendance_id = ObjectId(attendance_id)
        update_data = {}
        if check_in:
            update_data['check_in'] = check_in
        if check_out:
            update_data['check_out'] = check_out
        if date:
            update_data['date'] = date
        if shift:
            update_data['shift'] = shift
        if check_in and check_out:
            check_in_dt = datetime.strptime(check_in, '%Y-%m-%d %H:%M:%S')
            check_out_dt = datetime.strptime(check_out, '%Y-%m-%d %H:%M:%S')
            update_data['total_hours'] = (check_out_dt - check_in_dt).total_seconds() / 3600
        attendance_collection.update_one({'_id': attendance_id}, {'$set': update_data})
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in update_attendance: {e}")
        return False

def delete_attendance(attendance_id):
    """Delete attendance record"""
    try:
        if isinstance(attendance_id, str):
            attendance_id = ObjectId(attendance_id)
        attendance_collection.delete_one({'_id': attendance_id})
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in delete_attendance: {e}")
        return False

def get_attendance_report(start_date, end_date):
    """Get attendance report"""
    try:
        daily = list(attendance_collection.find({
            'date': {'$gte': start_date, '$lte': end_date}
        }).sort('date', -1))
        return {'daily': daily, 'summary': []}
    except Exception as e:
        print(f"Error in get_attendance_report: {e}")
        return {'daily': [], 'summary': []}
        
def clean_all_data():
    clean_attendance_only()
    clean_leaves_only()
    clean_missions_only()
    return True


# ============================================================
# REPORTS & DASHBOARD FUNCTIONS
# ============================================================

def get_attendance_report(start_date=None, end_date=None):
    query = {}
    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}
    
    docs = list(attendance_col.find(query).sort("date", DESCENDING))
    results = []
    for d in docs:
        d = convert_id(d)
        u = get_user_by_id(d['user_id'])
        if u: d['full_name'] = u.get('full_name')
        results.append(d)
    return results

def get_work_history_report(start_date=None, end_date=None, limit=200):
    if not start_date:
        start_date = datetime.now().replace(day=1).strftime('%Y-%m-%d')
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')

    result = []

    att_docs = list(attendance_col.find({
        "date": {"$gte": start_date, "$lte": end_date},
        "check_in": {"$ne": None}
    }))
    shift_map = {1: 'វគ្គ 1', 2: 'វគ្គ 2', 3: 'វគ្គ 3'}

    for d in att_docs:
        u = get_user_by_id(d['user_id'])
        full_name = u.get('full_name') if u else ''
        status = 'បានបិទ' if d.get('check_in') and d.get('check_out') else ('កំពុងធ្វើការ' if d.get('check_in') else 'មិនទាន់ចូល')

        result.append({
            "id": str(d['_id']),
            "user_id": d['user_id'],
            "full_name": full_name,
            "date": d.get('date'),
            "shift": shift_map.get(d.get('shift'), 'វគ្គ 1'),
            "check_in": d.get('check_in'),
            "check_out": d.get('check_out'),
            "total_hours": d.get('total_hours'),
            "type": "attendance",
            "status": status,
            "sort_date": d.get('date')
        })

    leave_docs = list(leaves_col.find({
        "status": "approved",
        "start_date": {"$gte": start_date, "$lte": end_date}
    }))
    for l in leave_docs:
        u = get_user_by_id(l['user_id'])
        result.append({
            "id": str(l['_id']),
            "user_id": l['user_id'],
            "full_name": u.get('full_name') if u else '',
            "date": l.get('start_date'),
            "shift": "ច្បាប់",
            "type": "leave",
            "days": l.get('days'),
            "reason": l.get('reason'),
            "status": "បានអនុម័ត",
            "sort_date": l.get('start_date')
        })

    mission_docs = list(missions_col.find({
        "status": "approved",
        "start_date": {"$gte": start_date, "$lte": end_date}
    }))
    for m in mission_docs:
        u = get_user_by_id(m['user_id'])
        result.append({
            "id": str(m['_id']),
            "user_id": m['user_id'],
            "full_name": u.get('full_name') if u else '',
            "date": m.get('start_date'),
            "shift": "បេសកម្ម",
            "type": "mission",
            "days": m.get('days'),
            "destination": m.get('destination'),
            "status": "បានអនុម័ត",
            "sort_date": m.get('start_date')
        })

    for item in result:
        if item.get('type') == 'attendance':
            if item.get('total_hours'):
                tot = item['total_hours']
                hours = abs(int(tot))
                minutes = abs(int((tot - int(tot)) * 60))
                prefix = "-" if tot < 0 else ""
                item['total_hours_formatted'] = f"{prefix}{hours:02d}:{minutes:02d}"
                item['display_value'] = item['total_hours_formatted']
            else:
                item['total_hours_formatted'] = ''
                item['display_value'] = ''

            cin = item.get('check_in')
            cout = item.get('check_out')
            item['check_in_time'] = cin[11:16] if cin and ' ' in cin else (cin[:5] if cin else '')
            item['check_out_time'] = cout[11:16] if cout and ' ' in cout else (cout[:5] if cout else '')
            item['display_info'] = ''
        elif item.get('type') == 'leave':
            item['check_in_time'] = ''
            item['check_out_time'] = ''
            item['total_hours_formatted'] = ''
            item['display_value'] = f"{item.get('days', 0)} ថ្ងៃ"
            item['display_info'] = f"មូលហេតុ: {item.get('reason', 'មិនបានបញ្ជាក់')}"
        elif item.get('type') == 'mission':
            item['check_in_time'] = ''
            item['check_out_time'] = ''
            item['total_hours_formatted'] = ''
            item['display_value'] = f"{item.get('days', 0)} ថ្ងៃ"
            item['display_info'] = f"ទីតាំង: {item.get('destination', 'មិនបានបញ្ជាក់')}"

    result.sort(key=lambda x: x.get('sort_date', ''), reverse=True)
    return result[:limit]

def get_monthly_summary_report(start_date, end_date):
    users = get_all_users()
    summary = []

    for user in users:
        uid_str = str(user['id'])
        
        worked_days = len(attendance_col.distinct("date", {
            "user_id": uid_str,
            "date": {"$gte": start_date, "$lte": end_date}
        }))
        
        att_pipeline = [
            {"$match": {"user_id": uid_str, "date": {"$gte": start_date, "$lte": end_date}}},
            {"$group": {"_id": None, "total": {"$sum": "$total_hours"}}}
        ]
        hours_res = list(attendance_col.aggregate(att_pipeline))
        total_hours = round(hours_res[0]['total'], 2) if hours_res else 0.0

        leave_pipeline = [
            {"$match": {"user_id": uid_str, "status": "approved", "start_date": {"$gte": start_date, "$lte": end_date}}},
            {"$group": {"_id": None, "total": {"$sum": "$days"}}}
        ]
        leave_res = list(leaves_col.aggregate(leave_pipeline))
        leave_days = leave_res[0]['total'] if leave_res else 0

        mission_pipeline = [
            {"$match": {"user_id": uid_str, "status": "approved", "start_date": {"$gte": start_date, "$lte": end_date}}},
            {"$group": {"_id": None, "total": {"$sum": "$days"}}}
        ]
        mission_res = list(missions_col.aggregate(mission_pipeline))
        mission_days = mission_res[0]['total'] if mission_res else 0

        summary.append({
            "user_id": uid_str,
            "full_name": user.get('full_name'),
            "username": user.get('username'),
            "days_worked": worked_days,
            "total_hours": total_hours,
            "leave_days": leave_days,
            "mission_days": mission_days
        })

    return summary
