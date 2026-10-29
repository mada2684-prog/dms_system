from flask import Flask, request, redirect, session, render_template, url_for, abort
from datetime import datetime
import sqlite3
import os
import shutil
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "north_cairo_electricity_secret_2026"
DB = "correspondence.db"
UPLOAD_FOLDER = "static/uploads"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ==========================================================
# CUSTOM JINJA FILTER (محرك تعريب الأرقام التلقائي الشامل للمنظومة)
# ==========================================================
@app.template_filter('arabic_numbers')
def arabic_numbers_filter(value):
    if value is None:
        return ""
    
    # تحويل القيمة إلى نص للتمكن من استبدال الحروف الرقمية بدقة
    text_val = str(value)
    
    # خريطة الموازنة الرقمية الشرقية
    english_to_arabic = {
        '0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤',
        '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩'
    }
    
    # ترجمة الحروف الرقمية داخل النص
    converted_text = "".join(english_to_arabic.get(char, char) for char in text_val)
    return converted_text

def connect():
    # إضافة timeout=30 تمنع خطأ database is locked نهائياً في بيئات العمل المشتركة
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

# ======================
# DECORATORS (نظام الحماية والصلاحيات)
# ======================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session or session.get("role") != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated_function
# ==========================================================
# SECURITY DECORATORS (دالة الحماية المحدثة لرتبة مدير قطاع)
# ==========================================================
def sub_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        # السماح فقط للأدمن الرئيسي أو لمدير القطاع بالدخول
        if session.get("role") not in ["admin", "sub_admin"]:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# ==========================================================
# DATABASE INITIALIZATION (النسخة النهائية المحصنة لحقن حقل التبعية التلقائي)
# ==========================================================
def create_tables():
    conn = connect()
    cur = conn.cursor()
    
    # [تأكد من بقاء الجداول الأساسية الخمسة كما هي دون تعديل]
    cur.execute("""
    CREATE TABLE IF NOT EXISTS offices(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, code TEXT UNIQUE
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, office_id INTEGER, role TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS letters(
        id INTEGER PRIMARY KEY AUTOINCREMENT, external_incoming_number TEXT, subject TEXT, 
        description TEXT, incoming_from TEXT, incoming_date TEXT, reply_date TEXT, 
        created_at TEXT, created_by INTEGER, current_office TEXT, status TEXT DEFAULT 'new'
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS transfers(
        id INTEGER PRIMARY KEY AUTOINCREMENT, letter_id INTEGER, from_office INTEGER, to_office INTEGER, 
        status TEXT DEFAULT 'pending', sent_at TEXT, received_at TEXT, note TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS letter_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, letter_id INTEGER, action TEXT, from_office INTEGER, to_office INTEGER, created_at TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS attachments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, letter_id INTEGER, file_path TEXT, uploaded_by TEXT
    )""")
    
    # 🔒 حزمة التطوير والحماية الفورية: فحص وحقن الأعمدة تلو الآخر دون مسح قاعدة البيانات القديمة
        # 🔒 حزمة التطوير والحماية الفورية لحقن حقل حالة المعاملة اليدوي الجديد
    try: cur.execute("ALTER TABLE letters ADD COLUMN external_incoming_number TEXT")
    except sqlite3.OperationalError: pass
    
    try: cur.execute("ALTER TABLE letter_logs ADD COLUMN to_office TEXT")
    except sqlite3.OperationalError: pass
    
    try: cur.execute("ALTER TABLE attachments ADD COLUMN uploaded_by TEXT")
    except sqlite3.OperationalError: pass

    try: cur.execute("ALTER TABLE offices ADD COLUMN parent_id INTEGER DEFAULT NULL")
    except sqlite3.OperationalError: pass

    # 🔥 السطر المنقذ الجديد: زرع حقل "حالة المكاتبة اليدوي" في قاعدة البيانات دون تصفيرها
    try: 
        cur.execute("ALTER TABLE letters ADD COLUMN letter_action_type TEXT DEFAULT 'غير محدد'")
    except sqlite3.OperationalError: 
        pass # العمود مضاف مسبقاً، تخطى وحافظ على أمن البيانات الجارية

    # [باقي كود حساب الأدمن الافتراضي]
    cur.execute("SELECT * FROM users WHERE username='admin'")
    if not cur.fetchone():
        cur.execute("INSERT INTO users(username, password, role) VALUES('admin', ?, 'admin')", (generate_password_hash('1234'),))

        
    conn.commit()
    conn.close()

# ======================
# AUTHENTICATION & DASHBOARD
# ======================
@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = connect()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        # ابحث عن دالة login في ملف app.py وتأكد من إضافة السطر الموضح بالأسفل
        if user and check_password_hash(user['password'], password):
            session["user_id"] = user['id']
            session["role"] = user['role']
            session["office_id"] = user['office_id']
            session["username"] = user['username'] # 🔥 اضف هذا السطر تحديداً لحفظ اسم المستخدم بداخل الجلسة
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="بيانات الدخول غير صحيحة")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ==========================================================
# DASHBOARD (النسخة النهائية المحصنة للعدادات الإحصائية لعام 2026)
# ==========================================================
@app.route("/dashboard")
@login_required
def dashboard():
    conn = connect()
    user_office = session.get("office_id")
    user_id = session.get("user_id")
    user_role = session.get("role")
    
    if user_role == "admin":
        t_row = conn.execute("SELECT COUNT(*) FROM letters").fetchone()
        n_row = conn.execute("SELECT COUNT(*) FROM letters WHERE status='new'").fetchone()
        tr_row = conn.execute("SELECT COUNT(*) FROM letters WHERE status='in_transfer'").fetchone()
        r_row = conn.execute("SELECT COUNT(*) FROM letters WHERE status='received' OR status='replied_closed'").fetchone()
        u_row = conn.execute("""
            SELECT COUNT(*) FROM letters WHERE reply_date IS NOT NULL AND reply_date != ''
            AND date(reply_date) <= date('now', '+3 day') AND status != 'received' AND status != 'replied_closed'
        """).fetchone()
        
        total_num = t_row[0] if t_row else 0
        new_num = n_row[0] if n_row else 0
        transferring_num = tr_row[0] if tr_row else 0
        received_num = r_row[0] if r_row else 0
        urgent_num = u_row[0] if u_row else 0
    else:
        t_row = conn.execute("""
            SELECT COUNT(DISTINCT l.id) FROM letters l
            WHERE l.created_by = ? OR l.id IN (SELECT letter_id FROM transfers WHERE to_office = ? OR from_office = ?)
        """, (user_id, user_office, user_office)).fetchone()
        
        n_row = conn.execute("""
            SELECT COUNT(DISTINCT id) FROM letters WHERE status='new' AND created_by = ?
        """, (user_id,)).fetchone()
        
        tr_row = conn.execute("""
            SELECT COUNT(DISTINCT l.id) FROM letters l
            WHERE l.status='in_transfer' AND (l.created_by = ? OR l.id IN (SELECT letter_id FROM transfers WHERE to_office = ? OR from_office = ?))
        """, (user_id, user_office, user_office)).fetchone()
        
        r_row = conn.execute("""
            SELECT COUNT(DISTINCT l.id) FROM letters l
            WHERE (l.status='received' OR l.status='replied_closed') 
            AND (l.created_by = ? OR l.id IN (SELECT letter_id FROM transfers WHERE to_office = ? OR from_office = ?))
        """, (user_id, user_office, user_office)).fetchone()
        
        u_row = conn.execute("""
            SELECT COUNT(DISTINCT l.id) FROM letters l
            WHERE l.reply_date IS NOT NULL AND l.reply_date != ''
            AND date(l.reply_date) <= date('now', '+3 day') AND l.status != 'received' AND l.status != 'replied_closed'
            AND (l.created_by = ? OR l.id IN (SELECT letter_id FROM transfers WHERE to_office = ? OR from_office = ?))
        """, (user_id, user_office, user_office)).fetchone()
        
        total_num = t_row[0] if t_row else 0
        new_num = n_row[0] if n_row else 0
        transferring_num = tr_row[0] if tr_row else 0
        received_num = r_row[0] if r_row else 0
        urgent_num = u_row[0] if u_row else 0


    conn.close()

    eng_to_arb = {'0':'٠', '1':'١', '2':'٢', '3':'٣', '4':'٤', '5':'٥', '6':'٦', '7':'٧', '8':'٨', '9':'٩'}
    total_clean = "".join(eng_to_arb.get(c, c) for c in str(total_num))
    new_clean = "".join(eng_to_arb.get(c, c) for c in str(new_num))
    transferring_clean = "".join(eng_to_arb.get(c, c) for c in str(transferring_num))
    received_clean = "".join(eng_to_arb.get(c, c) for c in str(received_num))
    urgent_clean = "".join(eng_to_arb.get(c, c) for c in str(urgent_num))

    return render_template("dashboard.html", total=total_clean, new=new_clean, transferring=transferring_clean, received=received_clean, urgent=urgent_clean)

# ==========================================================
# ADD LETTER (نسخة التوسعة المؤسسية المحدثة بحقل حالة المكاتبة اليدوي)
# ==========================================================
@app.route("/add_letter", methods=["GET", "POST"])
@login_required
def add_letter():
    conn = connect()
    if request.method == "POST":
        cur = conn.cursor()
        external_incoming_number = request.form.get("external_incoming_number", "").strip()
        subject = request.form.get("subject", "").strip()
        description = request.form.get("description", "").strip()
        incoming_from = request.form.get("incoming_from", "").strip()
        incoming_date = request.form.get("incoming_date", "").strip()
        reply_date = request.form.get("reply_date", "").strip()
        to_offices = request.form.getlist("to_offices")
        
        # 🔥 التقاط حقل "حالة المكاتبة اليدوي الجديد" (مثل: إفادة - تنبيه باللازم)
        letter_action_type = request.form.get("letter_action_type", "غير محدد").strip()
        if not letter_action_type:
            letter_action_type = "غير محدد"
            
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        if not external_incoming_number:
            external_incoming_number = "بدون رقم"
            
        office_names = []
        if to_offices:
            for office_id in to_offices:
                office_data = conn.execute("SELECT name FROM offices WHERE id=?", (office_id,)).fetchone()
                if office_data:
                    office_names.append(office_data["name"])
        offices_string = " + ".join(office_names) if office_names else "غير محدد"
        
        # حقن الحقل الجديد letter_action_type داخل استعلام الـ INSERT
        cur.execute("""
            INSERT INTO letters(external_incoming_number, subject, description, incoming_from, incoming_date, reply_date, created_at, created_by, current_office, status, letter_action_type)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, (external_incoming_number, subject, description, incoming_from, incoming_date, reply_date, datetime.now().strftime("%Y-%m-%d"), session["user_id"], offices_string, "in_transfer", letter_action_type))
        
        letter_id = cur.lastrowid
        for office_id in to_offices:
            cur.execute("INSERT INTO transfers(letter_id, from_office, to_office, status, sent_at) VALUES(?, NULL, ?, 'pending', ?)", (letter_id, office_id, current_time))
            cur.execute("INSERT INTO letter_logs(letter_id, action, from_office, to_office, created_at) VALUES(?, 'transfer', NULL, ?, ?)", (letter_id, office_id, current_time))
        
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        files = request.files.getlist("attachments")
        for file in files:
            if file and file.filename != "":
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                web_friendly_path = f"static/uploads/{filename}"
                cur.execute("""
                    INSERT INTO attachments(letter_id, file_path, uploaded_by) 
                    VALUES(?,?,?)
                """, (letter_id, web_friendly_path, session.get("username", "admin")))
                
        conn.commit()
        conn.close()
        return redirect(url_for("letters"))
        
    offices = conn.execute("SELECT id, name FROM offices").fetchall()
    conn.close()
    return render_template("add_letter.html", offices=offices)

# ======================
# USERS MANAGEMENT (إدارة الموظفين)
# ======================
@app.route("/users")
@admin_required
def users_list():
    conn = connect()
    data = conn.execute("""
        SELECT u.id, u.username, u.role, o.name as office_name 
        FROM users u 
        LEFT JOIN offices o ON u.office_id = o.id
    """).fetchall()
    conn.close()
    return render_template("users.html", users=data)

@app.route("/add_user", methods=["GET", "POST"])
@admin_required
def add_user():
    conn = connect()
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        office_id = request.form["office_id"]
        role = request.form["role"]
        
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users(username, password, office_id, role) VALUES(?,?,?,?)", (username, password, office_id, role))
            conn.commit()
        except sqlite3.IntegrityError:
            offices = conn.execute("SELECT id, name FROM offices").fetchall()
            conn.close()
            return render_template("add_user.html", offices=offices, error="اسم المستخدم مسجل مسبقاً بالنظام!")
            
        conn.close()
        return redirect(url_for("users_list"))
        
    offices = conn.execute("SELECT id, name FROM offices").fetchall()
    conn.close()
    return render_template("add_user.html", offices=offices)

# ==========================================================
# RESET PASSWORD BY ADMIN (إعادة تعيين كلمة المرور بواسطة الأدمن)
# ==========================================================
@app.route("/reset_password/<int:user_id>", methods=["GET", "POST"])
@admin_required
def reset_password(user_id):
    conn = connect()
    user = conn.execute("SELECT id, username FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return "الموظف غير موجود", 404
        
    if request.method == "POST":
        new_password = generate_password_hash(request.form["new_password"])
        cur = conn.cursor()
        cur.execute("UPDATE users SET password=? WHERE id=?", (new_password, user_id))
        conn.commit()
        conn.close()
        return redirect(url_for("users_list"))
        
    conn.close()
    return render_template("reset_password.html", user=user)

# ==========================================================
# CHANGE PASSWORD BY EMPLOYEE (تغيير كلمة المرور الشخصية للموظف)
# ==========================================================
@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    error = None
    success = None
    if request.method == "POST":
        old_password = request.form["old_password"]
        new_password = request.form["new_password"]
        
        conn = connect()
        user = conn.execute("SELECT password FROM users WHERE id=?", (session["user_id"],)).fetchone()
        
        if user and check_password_hash(user["password"], old_password):
            hashed_password = generate_password_hash(new_password)
            cur = conn.cursor()
            cur.execute("UPDATE users SET password=? WHERE id=?", (hashed_password, session["user_id"]))
            conn.commit()
            success = "تم تغيير كلمة المرور الشخصية بنجاح!"
        else:
            error = "كلمة المرور الحالية غير صحيحة، يرجى المحاولة مرة أخرى."
        conn.close()
        
    return render_template("change_password.html", error=error, success=success)

# ==========================================================
# TIMELINE (النسخة النهائية لربط هوية رافع كل مستند مستقل)
# ==========================================================
@app.route("/timeline/<int:letter_id>")
@login_required
def timeline(letter_id):
    conn = connect()
    
    # 1. جلب المعاملة مع منشئها الأول
    letter = conn.execute("""
        SELECT l.*, u.username as creator_name 
        FROM letters l 
        LEFT JOIN users u ON l.created_by = u.id 
        WHERE l.id = ?
    """, (letter_id,)).fetchone()
    
    if not letter:
        conn.close()
        return "المكاتبة غير موجودة", 404

    # 2. جلب المرفقات مع قراءة الحقل الجديد uploaded_by لتحديد هوية رافع الورقة
    attachments = conn.execute("""
        SELECT id, file_path, uploaded_by 
        FROM attachments 
        WHERE letter_id = ?
    """, (letter_id,)).fetchall()

    # 3. جلب سجل التحركات التاريخية
    logs = conn.execute("""
        SELECT 
            tl.action, 
            tl.created_at, 
            tl.to_office as reply_content, 
            o1.name as from_office_name, 
            o2.name as to_office_name,
            (SELECT username FROM users WHERE id = l.created_by) as log_user_name
        FROM letter_logs tl 
        LEFT JOIN letters l ON tl.letter_id = l.id
        LEFT JOIN offices o1 ON tl.from_office = o1.id 
        LEFT JOIN offices o2 ON tl.to_office = o2.id
        WHERE tl.letter_id = ? 
        ORDER BY tl.created_at DESC
    """, (letter_id,)).fetchall()
    
    conn.close()
    return render_template("timeline.html", letter=letter, logs=logs, attachments=attachments)

# ==========================================================
# LETTERS (النسخة النهائية المحصنة: عزل المكاتبات غير المحولة كلياً)
# ==========================================================
@app.route("/letters")
@login_required
def letters():
    conn = connect()
    user_office = session.get("office_id")
    user_id = session.get("user_id")
    user_role = session.get("role")
    
    if user_role == "admin":
        letters_data = conn.execute("""
            SELECT l.*,
                (SELECT t.id FROM transfers t WHERE t.letter_id = l.id AND t.status = 'pending' LIMIT 1) as my_pending_transfer_id,
                (SELECT t.status FROM transfers t WHERE t.letter_id = l.id ORDER BY t.id DESC LIMIT 1) as last_transfer_status
            FROM letters l ORDER BY l.id DESC
        """).fetchall()
    else:
        # القيد الصارم والمطلق: حظر تام للمواضيع الجديدة التي لم يتم تحويلها لقطاع الموظف بعد
        letters_data = conn.execute("""
            SELECT l.*,
                (SELECT t.id FROM transfers t WHERE t.letter_id = l.id AND t.to_office = ? AND t.status = 'pending' LIMIT 1) as my_pending_transfer_id,
                (SELECT t.status FROM transfers t WHERE t.letter_id = l.id ORDER BY t.id DESC LIMIT 1) as last_transfer_status
            FROM letters l
            WHERE l.created_by = ? 
               OR l.id IN (SELECT letter_id FROM transfers WHERE to_office = ? OR from_office = ?)
            ORDER BY l.id DESC
        """, (user_office, user_id, user_office, user_office)).fetchall()
    
    conn.close()
    return render_template("letters.html", letters=letters_data)

# ==========================================================
# REPORTS & PRINTING (النسخة المؤسسية المعزولة جغرافياً بالكامل)
# ==========================================================
@app.route("/reports", methods=["GET"])
@login_required
def reports():
    conn = connect()
    user_office = session.get("office_id")
    user_id = session.get("user_id")
    user_role = session.get("role")
    
    status_filter = request.args.get("status", "").strip()
    office_filter = request.args.get("office", "").strip()
    from_date = request.args.get("from_date", "").strip()
    to_date = request.args.get("to_date", "").strip()
    action_filter = request.args.get("action_type", "").strip()
    incoming_from_filter = request.args.get("incoming_from", "").strip()
    
    # الأساس البرمجي للاستعلام: جلب آخر مكتب محول إليه وتاريخ التحويل الرسمي
    query = """
        SELECT 
            l.id, l.external_incoming_number, l.subject, l.incoming_from, l.status, l.letter_action_type, l.created_by,
            COALESCE(
                (SELECT o.name FROM transfers t JOIN offices o ON t.to_office = o.id WHERE t.letter_id = l.id ORDER BY t.id DESC LIMIT 1),
                l.current_office
            ) as clean_current_office,
            COALESCE(
                (SELECT date(t.sent_at) FROM transfers t WHERE t.letter_id = l.id ORDER BY t.id ASC LIMIT 1),
                l.created_at
            ) as transfer_date
        FROM letters l WHERE 1=1
    """
    
    # 🔒 حزمة العزل الأمني: تطبيق الحظر الجغرافي الصارم فوراً على حسابات الموظفين ومديري القطاعات
    if user_role != "admin":
        query += """ AND (l.created_by = ? OR l.id IN (
            SELECT letter_id FROM transfers WHERE to_office = ? OR from_office = ?
        ))"""
        
    params = []
    if user_role != "admin":
        params.extend([user_id, user_office, user_office])
        
    # تطبيق الفلاتر التصفيفية للدليل العلوي في نفس وقت العزل
    if status_filter:
        query += " AND l.status = ?"
        params.append(status_filter)
    if office_filter:
        query += " AND clean_current_office LIKE ?"
        params.append(f"%{office_filter}%")
    if action_filter:
        query += " AND l.letter_action_type LIKE ?"
        params.append(f"%{action_filter}%")
    if incoming_from_filter:
        query += " AND l.incoming_from LIKE ?"
        params.append(f"%{incoming_from_filter}%")
    if from_date:
        query += " AND date(transfer_date) >= date(?)"
        params.append(from_date)
    if to_date:
        query += " AND date(transfer_date) <= date(?)"
        params.append(to_date)
        
    query += " ORDER BY l.id DESC"
    letters_data = conn.execute(query, params).fetchall()
    
    formatted_letters = []
    for row in letters_data:
        letter_dict = dict(row)
        raw_date = letter_dict["transfer_date"]
        try:
            date_obj = datetime.strptime(raw_date, "%Y-%m-%d")
            letter_dict["formatted_transfer_date"] = date_obj.strftime("%d/%m/%Y")
        except:
            letter_dict["formatted_transfer_date"] = raw_date
        formatted_letters.append(letter_dict)

    offices = conn.execute("SELECT name FROM offices").fetchall()
    conn.close()
    return render_template("reports.html", letters=formatted_letters, status_filter=status_filter, office_filter=office_filter, from_date=from_date, to_date=to_date, offices=offices, action_filter=action_filter)

# ======================
# RE-TRANSFER LETTER (نسخة مؤمنة بالكامل ضد قفل قاعدة البيانات)
# ======================
@app.route("/re_transfer/<int:letter_id>", methods=["GET", "POST"])
@login_required
def re_transfer(letter_id):
    conn = connect()
    
    # 1. جلب البيانات وإغلاق الاتصال فوراً لفك قفل الملف
    letter_row = conn.execute("SELECT id, subject, current_office FROM letters WHERE id=?", (letter_id,)).fetchone()
    conn.close()
    
    if not letter_row:
        return "المكاتبة غير موجودة", 404
        
    # تحويل البيانات إلى قاموس عادي لتجنب بقاء الـ Row Object معلقاً في الذاكرة
    letter = {"id": letter_row["id"], "subject": letter_row["subject"], "current_office": letter_row["current_office"]}
        
    if request.method == "POST":
        to_offices = request.form.getlist("to_offices")
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        if to_offices:
            # فتح اتصال جديد مستقل ومعزول كلياً مخصص فقط للكتابة
            write_conn = connect()
            cur = write_conn.cursor()
            new_office_names = []
            
            for office_id in to_offices:
                office_data = write_conn.execute("SELECT name FROM offices WHERE id=?", (office_id,)).fetchone()
                if office_data:
                    new_office_names.append(office_data["name"])
                    
                cur.execute("INSERT INTO transfers(letter_id, from_office, to_office, status, sent_at) VALUES(?, NULL, ?, 'pending', ?)", (letter_id, office_id, current_time))
                cur.execute("INSERT INTO letter_logs(letter_id, action, from_office, to_office, created_at) VALUES(?, 'transfer', NULL, ?, ?)", (letter_id, office_id, current_time))
            
            # دمج القطاعات القديمة والجديدة
            updated_offices = letter["current_office"] + " + " + " + ".join(new_office_names) if letter["current_office"] else " + ".join(new_office_names)
            cur.execute("UPDATE letters SET current_office=?, status='in_transfer' WHERE id=?", (updated_offices, letter_id))
            
            write_conn.commit()
            write_conn.close() # إغلاق الاتصال فوراً بعد انتهاء الحفظ
            
        return redirect(url_for("letters"))
        
    # فتح اتصال نظيف مخصص فقط لعرض القائمة المنسدلة للجهات
    read_conn = connect()
    offices = read_conn.execute("SELECT id, name FROM offices").fetchall()
    read_conn.close()
    
    return render_template("re_transfer.html", letter=letter, offices=offices)

# ======================
# RECEIVE (تأكيد الاستلام الإداري المصلح والمؤمن 100%)
# ======================
@app.route("/receive/<int:transfer_id>")
@login_required
def receive_transfer(transfer_id):
    conn = connect()
    cur = conn.cursor()
    
    # 1. جلب بيانات التحويل الحالي لمعرفة رقم المكاتبة والجهات المعنية
    row = cur.execute("SELECT letter_id, from_office, to_office FROM transfers WHERE id=?", (transfer_id,)).fetchone()
    
    if row:
        letter_id = row['letter_id']
        from_office = row['from_office']
        to_office = row['to_office']
        
        # حساب الوقت الحالي بدقة عبر البايثون وتمريره كنص جاهز
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        # 2. تحديث حالة أمر التحويل إلى "تم الاستلام" وتوثيق توقيته
        cur.execute("UPDATE transfers SET status='received', received_at=? WHERE id=?", (current_time, transfer_id))
        
        # 3. تحديث حالة المكاتبة الرئيسية في السجل الموحد لتصبح "تم الاستلام"
        cur.execute("UPDATE letters SET status='received' WHERE id=?", (letter_id,))
        
        # 4. إصلاح السطر 362: تسجيل الحركة التاريخية بنجاح داخل سجل التحركات للخط الزمني
        cur.execute("""
            INSERT INTO letter_logs(letter_id, action, from_office, to_office, created_at) 
            VALUES(?, 'receive', ?, ?, ?)
        """, (letter_id, from_office, to_office, current_time))
        
        conn.commit()
        
    conn.close()
    return redirect(url_for('letters'))

# ==========================================================
# ADD ATTACHMENT FROM TIMELINE (النسخة المحدثة لحقن هوية مسجل الملف)
# ==========================================================
@app.route("/add_attachment/<int:letter_id>", methods=["POST"])
@login_required
def add_attachment(letter_id):
    conn = connect()
    cur = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    files = request.files.getlist("new_attachments")
    file_uploaded = False
    
    for file in files:
        if file and file.filename != "":
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            web_friendly_path = f"static/uploads/{filename}"
            # 🔥 التحديث: حقن اسم الموظف uploaded_by بشكل مستقل مع المرفق التكميلي
            cur.execute("""
                INSERT INTO attachments(letter_id, file_path, uploaded_by) 
                VALUES(?,?,?)
            """, (letter_id, web_friendly_path, session.get("username", "admin")))
            file_uploaded = True
            
    if file_uploaded:
        cur.execute("INSERT INTO letter_logs(letter_id, action, from_office, to_office, created_at) VALUES(?, 'add_attachment', NULL, NULL, ?)", (letter_id, current_time))
        conn.commit()
        
    conn.close()
    return redirect(url_for('timeline', letter_id=letter_id))


# ==========================================================
# REPLY & CLOSE LETTER (النسخة المحدثة لحقن هوية مسجل ملف الرد)
# ==========================================================
@app.route("/reply_letter/<int:letter_id>", methods=["GET", "POST"])
@login_required
def reply_letter(letter_id):
    conn = connect()
    letter = conn.execute("SELECT id, subject FROM letters WHERE id=?", (letter_id,)).fetchone()
    if not letter:
        conn.close()
        return "المكاتبة غير موجودة", 404
        
    if request.method == "POST":
        cur = conn.cursor()
        reply_note = request.form.get("reply_note", "").strip()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        files = request.files.getlist("reply_attachments")
        reply_files_links = []
        
        for file in files:
            if file and file.filename != "":
                filename = secure_filename(file.filename)
                unique_filename = f"reply_{letter_id}_{datetime.now().strftime('%M%S')}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                
                web_friendly_path = f"static/uploads/{unique_filename}"
                # 🔥 التحديث: حقن اسم الموظف uploaded_by بشكل مستقل مع مرفق الرد الرسمي
                cur.execute("""
                    INSERT INTO attachments(letter_id, file_path, uploaded_by) 
                    VALUES(?,?,?)
                """, (letter_id, web_friendly_path, session.get("username", "admin")))
                reply_files_links.append(web_friendly_path)
        
        attachments_text = ""
        if reply_files_links:
            attachments_text = "\n📎 المرفقات الرسمية للرد: " + " | ".join([f"<button type='button' onclick='openPreviewModal(\"/{p}\", \"مستند الرد\")' style='background:none; border:none; color:#38bdf8; font-weight:600; text-decoration:underline; cursor:pointer;'>استعراض المستند</button>" for p in reply_files_links])

        cur.execute("""
            UPDATE letters 
            SET status='replied_closed', description = description || ?
            WHERE id=?
        """, (f"\n[تم إغلاق المعاملة - {current_time}]: {reply_note}", letter_id))

        cur.execute("UPDATE transfers SET status='replied', received_at=? WHERE letter_id=? AND status='received'", (current_time, letter_id))
        
        final_reply_content = reply_note + attachments_text
        cur.execute("""
            INSERT INTO letter_logs(letter_id, action, from_office, to_office, created_at)
            VALUES(?, 'reply_close', ?, ?, ?)
        """, (letter_id, session.get("office_id"), final_reply_content, current_time))
        
        conn.commit()
        conn.close()
        return redirect(url_for("letters"))
        
    conn.close()
    return render_template("reply_letter.html", letter=letter)
    
def backup_database():
    backup_dir = "database_backups"
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"backup_{timestamp}_correspondence.db"
    backup_path = os.path.join(backup_dir, backup_filename)
    
    if os.path.exists(DB):
        shutil.copy(DB, backup_path)  # تم التصحيح هنا لتعمل فوراً دون أخطاء
        print(f"[✓] تم أخذ نسخة احتياطية آمنة من قاعدة البيانات بنجاح في: {backup_path}")


# ==========================================================
# OFFICES MANAGEMENT (نسخة الفرز الجغرافي الصارم حسب صلاحية القطاع)
# ==========================================================
@app.route("/offices")
@login_required
def offices():
    conn = connect()
    user_office = session.get("office_id") # القطاع الحالي للموظف
    user_role = session.get("role")        # صلاحية الموظف
    
    # 1. الأدمن الرئيسي يرى كافة القطاعات والمكاتب التابعة دون قيود
    if user_role == "admin":
        data = conn.execute("""
            SELECT o1.*, o2.name as parent_name 
            FROM offices o1 
            LEFT JOIN offices o2 ON o1.parent_id = o2.id
        """).fetchall()
        
    # 2. مدير القطاع (sub_admin) يرى فقط قطاعه الرئيسي والمكاتب الفرعية التابعة له حصرياً
    else:
        data = conn.execute("""
            SELECT o1.*, o2.name as parent_name 
            FROM offices o1 
            LEFT JOIN offices o2 ON o1.parent_id = o2.id
            WHERE o1.id = ? OR o1.parent_id = ?
        """, (user_office, user_office)).fetchall()
        
    conn.close()
    return render_template("offices.html", offices=data)

# ==========================================================
# ADD OFFICE (النسخة النهائية المصححة لتمرير شجرة التبعية)
# ==========================================================
@app.route("/add_office", methods=["GET", "POST"])
@login_required
@sub_admin_required
def add_office():
    error_msg = None
    conn = connect()
    
    if request.method == "POST":
        office_name = request.form.get("name", "").strip()
        office_code = request.form.get("code", "").strip().upper()
        parent_id = request.form.get("parent_id", "").strip()
        
        # حوكمة صارمة: إذا كان الحساب مدير قطاع (sub_admin)
        # يتم إجباره وتثبيت قطاعه الحالي كـ parent_id حسي ومحمي من التلاعب
        if session.get("role") == "sub_admin":
            parent_val = session.get("office_id")
        else:
            # الأدمن الرئيسي يمتلك حرية اختيار الأب من القائمة المنسدلة
            parent_val = int(parent_id) if parent_id else None
            
        if not office_name or not office_code:
            error_msg = "خطأ: يرجى كتابة اسم المكتب والكود المختصر معاً!"
            offices_list = conn.execute("SELECT id, name FROM offices").fetchall()
            conn.close()
            return render_template("add_office.html", error=error_msg, offices=offices_list)
            
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO offices(name, code, parent_id) 
                VALUES(?,?,?)
            """, (office_name, office_code, parent_val))
            conn.commit()
            conn.close()
            return redirect(url_for("offices"))
        except sqlite3.IntegrityError:
            error_msg = "خطأ: كود الويب المختصر هذا مستخدم مسبقاً بالنظام!"
            offices_list = conn.execute("SELECT id, name FROM offices").fetchall()
            conn.close()
            return render_template("add_office.html", error=error_msg, offices=offices_list)
            
    # 🔥 التصحيح الحاسم هنا: تغيير اسم المتغير من offices_list إلى offices ليطابق الـ HTML تماماً
    offices_list = conn.execute("SELECT id, name FROM offices").fetchall()
    conn.close()
    return render_template("add_office.html", error=error_msg, offices=offices_list)

@app.route("/edit_office/<int:office_id>", methods=["GET", "POST"])
@admin_required # حصرية للأدمن العام فقط لحماية سلامة الجداول الأساسية
def edit_office(office_id):
    conn = connect()
    office = conn.execute("SELECT * FROM offices WHERE id=?", (office_id,)).fetchone()
    error_msg = None
    
    if request.method == "POST":
        cur = conn.cursor()
        office_name = request.form.get("name", "").strip()
        office_code = request.form.get("code", "").strip().upper()
        try:
            cur.execute("UPDATE offices SET name=?, code=? WHERE id=?", (office_name, office_code, office_id))
            conn.commit()
            conn.close()
            return redirect(url_for("offices"))
        except sqlite3.IntegrityError:
            conn.close()
            error_msg = "خطأ: كود القطاع الجديد مستخدم في جهة أخرى!"
            return render_template("edit_office.html", office=office, error=error_msg)
        
    conn.close()
    return render_template("edit_office.html", office=office, error=error_msg)

@app.route("/delete_office/<int:office_id>")
@admin_required # حصرية للأدمن العام فقط لمنع العبث بهيكل الفروع
def delete_office(office_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET office_id = NULL WHERE office_id = ?", (office_id,))
    cur.execute("DELETE FROM offices WHERE id = ?", (office_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("offices"))

# ==========================================================
# DELETE ATTACHMENT (النسخة المحصنة: السماح بحذف المرفقات الشخصية فقط)
# ==========================================================
@app.route("/delete_attachment/<int:attach_id>")
@login_required
def delete_attachment(attach_id):
    conn = connect()
    cur = conn.cursor()
    
    # 1. جلب مسار الملف، رقم المكاتبة، وهوية الموظف الذي قام برفع هذا المستند بالتحديد
    attach = conn.execute("""
        SELECT file_path, letter_id, uploaded_by 
        FROM attachments 
        WHERE id = ?
    """, (attach_id,)).fetchone()
    
    if not attach:
        conn.close()
        return "المستند غير موجود", 404
        
    letter_id = attach["letter_id"]
    file_path = attach["file_path"]
    current_username = session.get("username")
    
    # 2. 🔒 قيد الأمان الحاسم: الحظر والمنع التام إلا للأدمن أو لرافع الملف بنفسه
    if session.get("role") != "admin" and attach["uploaded_by"] != current_username:
        conn.close()
        return "غير مسموح لك بحذف مستند رسمي محول من قطاع آخر!", 403
        
    # 3. حذف الملف الفعلي من الهارد ديسك الخاص بالسيرفر
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"[!] فشل حذف الملف: {file_path}")
            
    # 4. مسح السجل وتوثيق الحركة التاريخية في الجدول
    cur.execute("DELETE FROM attachments WHERE id = ?", (attach_id,))
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    cur.execute("""
        INSERT INTO letter_logs(letter_id, action, from_office, to_office, created_at)
        VALUES(?, 'delete_attachment', NULL, NULL, ?)
    """, (letter_id, current_time))
    
    conn.commit()
    conn.close()
    return redirect(url_for('timeline', letter_id=letter_id))

# ==========================================================
# DELETE LETTER & ATTACHMENTS (الحذف النظيف للمكاتبة ومرفقاتها الفعلية من السيرفر - أدمن فقط)
# ==========================================================
@app.route("/delete_letter/<int:letter_id>")
@admin_required # حماية حصرية لمدير النظام فقط
def delete_letter(letter_id):
    conn = connect()
    cur = conn.cursor()
    
    # 1. جلب مسارات كافة الملفات المرفوعة المرتبطة بهذه المعاملة من جدول المرفقات
    attachments = conn.execute("SELECT file_path FROM attachments WHERE letter_id = ?", (letter_id,)).fetchall()
    
    # 2. حذف الملفات الفعلية من الهارد ديسك الخاص بالسيرفر (static/uploads)
    for attach in attachments:
        file_path = attach["file_path"]
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"[!] فشل حذف الملف الفعلي: {file_path} - الخطأ: {str(e)}")
                
    # 3. مسح كافة السجلات التاريخية والتحويلات المرتبطة بالمكاتبة من جداول قاعدة البيانات بالتتابع
    cur.execute("DELETE FROM attachments WHERE letter_id = ?", (letter_id,))
    cur.execute("DELETE FROM transfers WHERE letter_id = ?", (letter_id,))
    cur.execute("DELETE FROM letter_logs WHERE letter_id = ?", (letter_id,))
    
    # 4. مسح المكاتبة نفسها نهائياً من جدول المعاملات
    cur.execute("DELETE FROM letters WHERE id = ?", (letter_id,))
    
    conn.commit()
    conn.close()
    return redirect(url_for("letters"))

# ==========================================================
# EDIT USER (تعديل بيانات وصلاحيات الموظف - أدمن فقط)
# ==========================================================
@app.route("/edit_user/<int:user_id>", methods=["GET", "POST"])
@admin_required
def edit_user(user_id):
    conn = connect()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    error_msg = None
    
    if not user:
        conn.close()
        return "الموظف غير موجود", 404
        
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        office_id = request.form.get("office_id")
        role = request.form.get("role")
        
        if not username:
            offices = conn.execute("SELECT id, name FROM offices").fetchall()
            conn.close()
            return render_template("edit_user.html", user=user, offices=offices, error="خطأ: اسم المستخدم مطلوب!")
            
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE users 
                SET username=?, office_id=?, role=? 
                WHERE id=?
            """, (username, office_id if office_id else None, role, user_id))
            conn.commit()
            conn.close()
            return redirect(url_for("users_list"))
        except sqlite3.IntegrityError:
            offices = conn.execute("SELECT id, name FROM offices").fetchall()
            conn.close()
            return render_template("edit_user.html", user=user, offices=offices, error="خطأ: اسم المستخدم الجديد مكرر ومسجل لموظف آخر!")
            
    offices = conn.execute("SELECT id, name FROM offices").fetchall()
    conn.close()
    return render_template("edit_user.html", user=user, offices=offices, error=error_msg)

# ==========================================================
# DELETE USER (الحذف الآمن لحساب الموظف - أدمن فقط)
# ==========================================================
@app.route("/delete_user/<int:user_id>")
@admin_required
def delete_user(user_id):
    # حماية وقائية: منع الأدمن من حذف حسابه الشخصي بالخطأ لمنع قفل النظام
    if session.get("user_id") == user_id:
        return "خطأ أمني: لا يمكنك حذف حساب الأدمن الرئيسي النشط حالياً!", 400
        
    conn = connect()
    cur = conn.cursor()
    # مسح الحساب نهائياً من جدول المستخدمين
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("users_list"))

if __name__ == "__main__":
    backup_database() # <--- تضمن لك وجود نسخة احتياطية عند كل تشغيل للسيرفر
    create_tables()
    app.run(host='0.0.0.0', port=5001, debug=False)