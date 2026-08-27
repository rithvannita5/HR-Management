# app.py
from flask_app import app, init_db

# Initialize database when app starts
with app.app_context():
    init_db()
    print("✅ Database initialized successfully!")

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
