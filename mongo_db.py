# mongo_db.py
import os
from pymongo import MongoClient
from datetime import datetime
import pytz
from bson import ObjectId

# ============================================================
# MONGODB CONNECTION
# ============================================================

MONGO_URI = os.environ.get('MONGO_URI')
if not MONGO_URI:
    MONGO_URI = 'mongodb://localhost:27017/'
    print("⚠️ Using local MongoDB (no MONGO_URI set)")

DB_NAME = os.environ.get('DB_NAME', 'hr_system')

try:
    client = MongoClient(MONGO_URI)
    client.admin.command('ping')
    print("✅ Connected to MongoDB successfully!")
except Exception as e:
    print(f"❌ MongoDB connection error: {e}")
    client = MongoClient('mongodb://localhost:27017/')

db = client[DB_NAME]

# Collections
users_collection = db['users']
attendance_collection = db['attendance']
leaves_collection = db['leaves']
missions_collection = db['missions']
company_location_collection = db['company_location']
settings_collection = db['settings']
data_version_collection = db['data_version']
attendance_settings_collection = db['attendance_settings']
user_attendance_lock_collection = db['user_attendance_lock']

CAMBODIA_TZ = pytz.timezone('Asia/Phnom_Penh')

def get_current_time():
    return datetime.now(CAMBODIA_TZ)

def get_current_date():
    return get_current_time().strftime('%Y-%m-%d')

def get_current_datetime_str():
    return get_current_time().strftime('%Y-%m-%d %H:%M:%S')

def get_current_time_only():
    return get_current_time().strftime('%H:%M:%S')

# ============================================================
# INIT DATABASE
# ============================================================

def init_db():
    try:
        admin = users_collection.find_one({'username': 'admin'})
        if not admin:
            users_collection.insert_one({
                'username': 'admin',
                'password': '1234',
                'full_name': 'អ្នកគ្រប់គ្រងប្រព័ន្ធ',
                'email': '',
                'phone': '',
                'role': 'admin',
                'created_at': get_current_datetime_str()
            })
            print("✅ Created admin user: admin / 1234")

        test_user = users_collection.find_one({'username': 'user1'})
        if not test_user:
            users_collection.insert_one({
                'username': 'user1',
                'password': '1234',
                'full_name': 'បុគ្គលិកសាកល្បង',
                'email': '',
                'phone': '',
                'role': 'user',
                'created_at': get_current_datetime_str()
            })
            print("✅ Created test user: user1 / 1234")

        version = data_version_collection.find_one({'_id': 'version'})
        if not version:
            data_version_collection.insert_one({
                '_id': 'version',
                'version': 1
            })
            print("✅ Data version initialized")

        lock = settings_collection.find_one({'_id': 'system_lock'})
        if not lock:
            settings_collection.insert_one({
                '_id': 'system_lock',
                'is_locked': 0,
                'auto_unlock_time': '06:00',
                'lock_start_time': None,
                'lock_end_time': None,
                'locked_by': None,
                'updated_at': get_current_datetime_str()
            })
            print("✅ System lock initialized")

        print("✅ MongoDB initialized successfully!")
        return True
    except Exception as e:
        print(f"❌ MongoDB initialization error: {e}")
        return False

# ============================================================
# DATA VERSION
# ============================================================

def get_data_version():
    try:
        version = data_version_collection.find_one({'_id': 'version'})
        return version['version'] if version else 1
    except Exception as e:
        print(f"Error getting data version: {e}")
        return 1

def increment_data_version():
    try:
        data_version_collection.update_one(
            {'_id': 'version'},
            {'$inc': {'version': 1}},
            upsert=True
        )
        return True
    except Exception as e:
        print(f"Error incrementing data version: {e}")
        return False

# ============================================================
# USER FUNCTIONS
# ============================================================

def get_user_by_id(user_id):
    try:
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        return users_collection.find_one({'_id': user_id})
    except Exception as e:
        print(f"Error in get_user_by_id: {e}")
        return None

def get_user_by_username(username):
    try:
        return users_collection.find_one({'username': username})
    except Exception as e:
        print(f"Error in get_user_by_username: {e}")
        return None

def create_user(username, password, full_name, email=None, phone=None, role='user'):
    try:
        existing = users_collection.find_one({'username': username})
        if existing:
            return False
        users_collection.insert_one({
            'username': username,
            'password': password,
            'full_name': full_name,
            'email': email or '',
            'phone': phone or '',
            'role': role,
            'created_at': get_current_datetime_str()
        })
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in create_user: {e}")
        return False

def update_user(user_id, username, full_name, email, phone, role):
    try:
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        existing = users_collection.find_one({
            'username': username,
            '_id': {'$ne': user_id}
        })
        if existing:
            return False
        users_collection.update_one(
            {'_id': user_id},
            {'$set': {
                'username': username,
                'full_name': full_name,
                'email': email or '',
                'phone': phone or '',
                'role': role
            }}
        )
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in update_user: {e}")
        return False

def update_password(user_id, new_password):
    try:
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        users_collection.update_one(
            {'_id': user_id},
            {'$set': {'password': new_password}}
        )
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in update_password: {e}")
        return False

def verify_password(user_id, password):
    try:
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        user = users_collection.find_one({'_id': user_id})
        return user and user['password'] == password
    except Exception as e:
        print(f"Error in verify_password: {e}")
        return False

def delete_user(user_id):
    try:
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        users_collection.delete_one({'_id': user_id})
        attendance_collection.delete_many({'user_id': str(user_id)})
        leaves_collection.delete_many({'user_id': str(user_id)})
        missions_collection.delete_many({'user_id': str(user_id)})
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in delete_user: {e}")
        return False

def get_all_users():
    try:
        return list(users_collection.find().sort('created_at', -1))
    except Exception as e:
        print(f"Error in get_all_users: {e}")
        return []

def get_user_lock_status(user_id):
    try:
        lock = user_attendance_lock_collection.find_one({'user_id': str(user_id)})
        if lock:
            return lock
        return {'is_locked': 0, 'auto_unlock_time': None}
    except Exception as e:
        print(f"Error in get_user_lock_status: {e}")
        return {'is_locked': 0, 'auto_unlock_time': None}

def update_user_lock(user_id, is_locked, auto_unlock_time=None, locked_by=None):
    try:
        current_time = get_current_datetime_str()
        update_data = {
            'is_locked': is_locked,
            'updated_at': current_time
        }
        if is_locked == 1:
            update_data['lock_start_time'] = current_time
            if auto_unlock_time:
                update_data['auto_unlock_time'] = auto_unlock_time
            if locked_by:
                update_data['locked_by'] = str(locked_by)
        else:
            update_data['lock_end_time'] = current_time
        
        user_attendance_lock_collection.update_one(
            {'user_id': str(user_id)},
            {'$set': update_data},
            upsert=True
        )
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in update_user_lock: {e}")
        return False

def get_all_user_lock_status():
    try:
        users = list(users_collection.find({'role': {'$ne': 'admin'}}))
        locks = list(user_attendance_lock_collection.find({}))
        lock_dict = {lock['user_id']: lock for lock in locks}
        
        result = []
        for user in users:
            user_id = str(user['_id'])
            lock = lock_dict.get(user_id, {'is_locked': 0})
            result.append({
                'id': user_id,
                'username': user['username'],
                'full_name': user['full_name'],
                'is_locked': lock.get('is_locked', 0),
                'auto_unlock_time': lock.get('auto_unlock_time'),
                'lock_start_time': lock.get('lock_start_time'),
                'updated_at': lock.get('updated_at')
            })
        return result
    except Exception as e:
        print(f"Error in get_all_user_lock_status: {e}")
        return []

# ============================================================
# COMPANY LOCATION
# ============================================================

def save_company_location(lat, lng, address=None):
    try:
        company_location_collection.delete_many({})
        company_location_collection.insert_one({
            'lat': lat,
            'lng': lng,
            'address': address or '',
            'updated_at': get_current_datetime_str()
        })
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in save_company_location: {e}")
        return False

def get_company_location():
    try:
        return company_location_collection.find_one({})
    except Exception as e:
        print(f"Error in get_company_location: {e}")
        return None

# ============================================================
# ATTENDANCE FUNCTIONS
# ============================================================

def get_checkin_status(user_id):
    try:
        record = attendance_collection.find_one({
            'user_id': str(user_id),
            'check_out': None
        }, sort=[('_id', -1)])
        
        if record:
            return {
                'has_checkin': True,
                'check_in_time': record.get('check_in'),
                'shift': record.get('shift', 1)
            }
        return {'has_checkin': False, 'check_in_time': None, 'shift': None}
    except Exception as e:
        print(f"Error in get_checkin_status: {e}")
        return {'has_checkin': False, 'check_in_time': None, 'shift': None}

def check_in(user_id, lat, lng, distance, shift):
    try:
        date = get_current_date()
        check_in_time = get_current_datetime_str()
        
        existing = attendance_collection.find_one({
            'user_id': str(user_id),
            'date': date,
            'shift': shift,
            'check_out': None
        })
        if existing:
            return False, "អ្នកបានចូលធ្វើការរួចហើយ!"

        attendance_collection.insert_one({
            'user_id': str(user_id),
            'date': date,
            'check_in': check_in_time,
            'check_out': None,
            'shift': shift,
            'check_in_lat': lat,
            'check_in_lng': lng,
            'check_in_distance': distance,
            'check_out_lat': None,
            'check_out_lng': None,
            'check_out_distance': None,
            'total_hours': 0,
            'created_at': get_current_datetime_str()
        })
        increment_data_version()
        return True, "ចូលធ្វើការជោគជ័យ!"
    except Exception as e:
        print(f"Error in check_in: {e}")
        return False, f"កំហុស: {e}"

def check_out(user_id, lat, lng, distance):
    try:
        check_out_time = get_current_datetime_str()
        
        record = attendance_collection.find_one({
            'user_id': str(user_id),
            'check_out': None
        }, sort=[('_id', -1)])
        
        if not record:
            return False, "មិនមានការចូលធ្វើការដែលមិនទាន់ចេញ!"
        
        from datetime import datetime
        check_in_dt = datetime.strptime(record['check_in'], '%Y-%m-%d %H:%M:%S')
        check_out_dt = datetime.strptime(check_out_time, '%Y-%m-%d %H:%M:%S')
        
        total_seconds = (check_out_dt - check_in_dt).total_seconds()
        total_hours = total_seconds / 3600
        
        if total_hours < 0:
            total_hours += 24
        
        attendance_collection.update_one(
            {'_id': record['_id']},
            {'$set': {
                'check_out': check_out_time,
                'check_out_lat': lat,
                'check_out_lng': lng,
                'check_out_distance': distance,
                'total_hours': total_hours
            }}
        )
        increment_data_version()
        
        shift_names = {1: 'វគ្គ 1 (ព្រឹក)', 2: 'វគ្គ 2 (រសៀល)', 3: 'វគ្គ 3 (យប់)'}
        shift = record.get('shift', 1)
        
        hours = int(total_hours)
        minutes = int((total_hours - hours) * 60)
        return True, f"ចេញធ្វើការជោគជ័យ! ({shift_names.get(shift, '')}) ម៉ោងសរុប: {hours:02d}:{minutes:02d}"
    except Exception as e:
        print(f"Error in check_out: {e}")
        return False, f"កំហុស: {e}"

def get_attendance_stats():
    try:
        today = get_current_date()
        total_users = users_collection.count_documents({'role': {'$ne': 'admin'}})
        present_today = attendance_collection.count_documents({
            'date': today,
            'check_out': None
        })
        leave_today = leaves_collection.count_documents({
            'status': 'approved',
            'start_date': {'$lte': today},
            'end_date': {'$gte': today}
        })
        mission_today = missions_collection.count_documents({
            'status': 'approved',
            'start_date': {'$lte': today},
            'end_date': {'$gte': today}
        })
        
        return {
            'total_users': total_users,
            'present_today': present_today,
            'leave_today': leave_today,
            'mission_today': mission_today
        }
    except Exception as e:
        print(f"Error in get_attendance_stats: {e}")
        return {'total_users': 0, 'present_today': 0, 'leave_today': 0, 'mission_today': 0}

def get_all_attendance(limit=100):
    try:
        return list(attendance_collection.find().sort('date', -1).limit(limit))
    except Exception as e:
        print(f"Error in get_all_attendance: {e}")
        return []

def get_work_history_report(start_date=None, end_date=None, limit=200):
    try:
        if not start_date:
            today = datetime.now()
            start_date = today.replace(day=1).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        attendance_records = list(attendance_collection.find({
            'date': {'$gte': start_date, '$lte': end_date}
        }).sort('date', -1))
        
        leave_records = list(leaves_collection.find({
            'status': 'approved',
            'start_date': {'$gte': start_date, '$lte': end_date}
        }).sort('start_date', -1))
        
        mission_records = list(missions_collection.find({
            'status': 'approved',
            'start_date': {'$gte': start_date, '$lte': end_date}
        }).sort('start_date', -1))
        
        return attendance_records + leave_records + mission_records
    except Exception as e:
        print(f"Error in get_work_history_report: {e}")
        return []

def get_monthly_summary_report(start_date, end_date):
    try:
        users = list(users_collection.find({'role': {'$ne': 'admin'}}))
        
        result = []
        for user in users:
            user_id = str(user['_id'])
            
            attendance = list(attendance_collection.aggregate([
                {
                    '$match': {
                        'user_id': user_id,
                        'date': {'$gte': start_date, '$lte': end_date}
                    }
                },
                {
                    '$group': {
                        '_id': '$user_id',
                        'days_worked': {'$sum': 1},
                        'total_hours': {'$sum': '$total_hours'},
                        'night_shifts': {'$sum': {'$cond': [{'$eq': ['$shift', 3]}, 1, 0]}},
                        'night_hours': {'$sum': {'$cond': [{'$eq': ['$shift', 3]}, '$total_hours', 0]}}
                    }
                }
            ]))
            
            leaves = list(leaves_collection.aggregate([
                {
                    '$match': {
                        'user_id': user_id,
                        'status': 'approved',
                        'start_date': {'$gte': start_date, '$lte': end_date}
                    }
                },
                {
                    '$group': {
                        '_id': '$user_id',
                        'total_leave_days': {'$sum': '$days'}
                    }
                }
            ]))
            
            missions = list(missions_collection.aggregate([
                {
                    '$match': {
                        'user_id': user_id,
                        'status': 'approved',
                        'start_date': {'$gte': start_date, '$lte': end_date}
                    }
                },
                {
                    '$group': {
                        '_id': '$user_id',
                        'total_mission_days': {'$sum': '$days'}
                    }
                }
            ]))
            
            att = attendance[0] if attendance else {}
            lev = leaves[0] if leaves else {}
            mis = missions[0] if missions else {}
            
            result.append({
                'id': user_id,
                'full_name': user['full_name'],
                'days_worked': att.get('days_worked', 0),
                'total_hours': att.get('total_hours', 0),
                'night_shifts': att.get('night_shifts', 0),
                'night_hours': att.get('night_hours', 0),
                'total_leave_days': lev.get('total_leave_days', 0),
                'total_mission_days': mis.get('total_mission_days', 0)
            })
        
        return result
    except Exception as e:
        print(f"Error in get_monthly_summary_report: {e}")
        return []

# ============================================================
# SYSTEM LOCK
# ============================================================

def get_system_lock_status():
    try:
        lock = settings_collection.find_one({'_id': 'system_lock'})
        if lock:
            return lock
        return {
            '_id': 'system_lock',
            'is_locked': 0,
            'auto_unlock_time': '06:00',
            'lock_start_time': None,
            'lock_end_time': None,
            'locked_by': None
        }
    except Exception as e:
        print(f"Error in get_system_lock_status: {e}")
        return {'is_locked': 0, 'auto_unlock_time': '06:00'}

def update_system_lock(is_locked, lock_start_time=None, lock_end_time=None, auto_unlock_time=None, locked_by=None):
    try:
        update_data = {
            'is_locked': is_locked,
            'updated_at': get_current_datetime_str()
        }
        if lock_start_time:
            update_data['lock_start_time'] = lock_start_time
        if lock_end_time:
            update_data['lock_end_time'] = lock_end_time
        if auto_unlock_time:
            update_data['auto_unlock_time'] = auto_unlock_time
        if locked_by:
            update_data['locked_by'] = str(locked_by)
        
        settings_collection.update_one(
            {'_id': 'system_lock'},
            {'$set': update_data},
            upsert=True
        )
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in update_system_lock: {e}")
        return False

def toggle_system_lock(lock_state, auto_unlock_time=None, locked_by=None):
    current_time = get_current_datetime_str()
    if lock_state == 1:
        return update_system_lock(
            is_locked=1,
            lock_start_time=current_time,
            auto_unlock_time=auto_unlock_time or '06:00',
            locked_by=locked_by
        )
    else:
        return update_system_lock(
            is_locked=0,
            lock_end_time=current_time,
            locked_by=locked_by
        )

# ============================================================
# LEAVE FUNCTIONS
# ============================================================

def create_leave(user_id, start_date, end_date, days, reason='', attachment=None):
    try:
        leaves_collection.insert_one({
            'user_id': str(user_id),
            'start_date': start_date,
            'end_date': end_date,
            'days': days,
            'reason': reason,
            'attachment': attachment,
            'status': 'pending',
            'admin_id': None,
            'created_at': get_current_datetime_str()
        })
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in create_leave: {e}")
        return False

def get_pending_leaves():
    try:
        return list(leaves_collection.find({'status': 'pending'}).sort('created_at', -1))
    except Exception as e:
        print(f"Error in get_pending_leaves: {e}")
        return []

def approve_leave(leave_id, admin_id):
    try:
        if isinstance(leave_id, str):
            leave_id = ObjectId(leave_id)
        leaves_collection.update_one(
            {'_id': leave_id},
            {'$set': {
                'status': 'approved',
                'admin_id': str(admin_id)
            }}
        )
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in approve_leave: {e}")
        return False

def reject_leave(leave_id):
    try:
        if isinstance(leave_id, str):
            leave_id = ObjectId(leave_id)
        leaves_collection.update_one(
            {'_id': leave_id},
            {'$set': {'status': 'rejected'}}
        )
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in reject_leave: {e}")
        return False

# ============================================================
# MISSION FUNCTIONS
# ============================================================

def create_mission(user_id, start_date, end_date, days, destination='', purpose='', attachment=None):
    try:
        missions_collection.insert_one({
            'user_id': str(user_id),
            'start_date': start_date,
            'end_date': end_date,
            'days': days,
            'destination': destination,
            'purpose': purpose,
            'attachment': attachment,
            'status': 'pending',
            'admin_id': None,
            'created_at': get_current_datetime_str()
        })
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in create_mission: {e}")
        return False

def get_pending_missions():
    try:
        return list(missions_collection.find({'status': 'pending'}).sort('created_at', -1))
    except Exception as e:
        print(f"Error in get_pending_missions: {e}")
        return []

def approve_mission(mission_id, admin_id):
    try:
        if isinstance(mission_id, str):
            mission_id = ObjectId(mission_id)
        missions_collection.update_one(
            {'_id': mission_id},
            {'$set': {
                'status': 'approved',
                'admin_id': str(admin_id)
            }}
        )
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in approve_mission: {e}")
        return False

def reject_mission(mission_id):
    try:
        if isinstance(mission_id, str):
            mission_id = ObjectId(mission_id)
        missions_collection.update_one(
            {'_id': mission_id},
            {'$set': {'status': 'rejected'}}
        )
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in reject_mission: {e}")
        return False

# ============================================================
# ATTENDANCE SETTINGS
# ============================================================

def get_attendance_setting(user_id):
    try:
        return attendance_settings_collection.find_one({'user_id': str(user_id)})
    except Exception as e:
        print(f"Error in get_attendance_setting: {e}")
        return None

def save_attendance_setting(user_id, check_in_deadline, is_active):
    try:
        attendance_settings_collection.update_one(
            {'user_id': str(user_id)},
            {'$set': {
                'check_in_deadline': check_in_deadline,
                'is_active': is_active,
                'updated_at': get_current_datetime_str()
            }},
            upsert=True
        )
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in save_attendance_setting: {e}")
        return False

def get_all_attendance_settings():
    try:
        return list(attendance_settings_collection.find({}))
    except Exception as e:
        print(f"Error in get_all_attendance_settings: {e}")
        return []

# ============================================================
# CLEAN DATA
# ============================================================

def clean_all_data():
    try:
        attendance_collection.delete_many({})
        leaves_collection.delete_many({})
        missions_collection.delete_many({})
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in clean_all_data: {e}")
        return False

def clean_attendance_only():
    try:
        attendance_collection.delete_many({})
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in clean_attendance_only: {e}")
        return False

def clean_leaves_only():
    try:
        leaves_collection.delete_many({})
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in clean_leaves_only: {e}")
        return False

def clean_missions_only():
    try:
        missions_collection.delete_many({})
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in clean_missions_only: {e}")
        return False

def get_attendance_report(start_date, end_date):
    try:
        daily = list(attendance_collection.find({
            'date': {'$gte': start_date, '$lte': end_date}
        }).sort('date', -1))
        return {'daily': daily, 'summary': []}
    except Exception as e:
        print(f"Error in get_attendance_report: {e}")
        return {'daily': [], 'summary': []}

def get_attendance_by_id(attendance_id):
    try:
        if isinstance(attendance_id, str):
            attendance_id = ObjectId(attendance_id)
        return attendance_collection.find_one({'_id': attendance_id})
    except Exception as e:
        print(f"Error in get_attendance_by_id: {e}")
        return None

def update_attendance(attendance_id, check_in=None, check_out=None, date=None, shift=None):
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
            from datetime import datetime
            check_in_dt = datetime.strptime(check_in, '%Y-%m-%d %H:%M:%S')
            check_out_dt = datetime.strptime(check_out, '%Y-%m-%d %H:%M:%S')
            total_hours = (check_out_dt - check_in_dt).total_seconds() / 3600
            update_data['total_hours'] = total_hours
        
        attendance_collection.update_one(
            {'_id': attendance_id},
            {'$set': update_data}
        )
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in update_attendance: {e}")
        return False

def delete_attendance(attendance_id):
    try:
        if isinstance(attendance_id, str):
            attendance_id = ObjectId(attendance_id)
        attendance_collection.delete_one({'_id': attendance_id})
        increment_data_version()
        return True
    except Exception as e:
        print(f"Error in delete_attendance: {e}")
        return False
