-- SQLite schema for Biometric Attendance.
-- Timestamps are ISO-8601 TEXT values. Foreign keys are enabled per connection.

CREATE TABLE IF NOT EXISTS people (
    person_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL CHECK (length(trim(full_name)) > 0),
    date_of_birth TEXT,
    gender TEXT CHECK (gender IS NULL OR gender IN ('male', 'female', 'other', 'unspecified')),
    phone TEXT,
    email TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS departments (
    department_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK (length(trim(name)) > 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS employees (
    employee_id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL UNIQUE REFERENCES people(person_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    employee_code TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(employee_code)) > 0),
    department_id INTEGER REFERENCES departments(department_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    job_title TEXT,
    hire_date TEXT,
    address TEXT,
    employment_status TEXT NOT NULL DEFAULT 'active'
        CHECK (employment_status IN ('active', 'on_leave', 'terminated', 'inactive'))
);

CREATE TABLE IF NOT EXISTS students (
    student_id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL UNIQUE REFERENCES people(person_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    student_code TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(student_code)) > 0),
    guardian_name TEXT,
    guardian_phone TEXT,
    student_status TEXT NOT NULL DEFAULT 'active'
        CHECK (student_status IN ('active', 'reserved', 'graduated', 'inactive'))
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id INTEGER PRIMARY KEY,
    person_id INTEGER UNIQUE REFERENCES people(person_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(username)) > 0),
    password_hash TEXT NOT NULL CHECK (length(password_hash) >= 32),
    password_scheme TEXT NOT NULL
        CHECK (password_scheme IN ('argon2id', 'bcrypt', 'scrypt', 'pbkdf2_sha256')),
    account_status TEXT NOT NULL DEFAULT 'active'
        CHECK (account_status IN ('active', 'locked', 'disabled')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS roles (
    role_id INTEGER PRIMARY KEY,
    role_code TEXT NOT NULL UNIQUE,
    role_name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS permissions (
    permission_id INTEGER PRIMARY KEY,
    permission_code TEXT NOT NULL UNIQUE,
    permission_name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS account_roles (
    account_id INTEGER NOT NULL REFERENCES accounts(account_id) ON UPDATE CASCADE ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(role_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    PRIMARY KEY (account_id, role_id)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER NOT NULL REFERENCES roles(role_id) ON UPDATE CASCADE ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions(permission_id) ON UPDATE CASCADE ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS classes (
    class_id INTEGER PRIMARY KEY,
    class_name TEXT NOT NULL CHECK (length(trim(class_name)) > 0),
    academic_year TEXT NOT NULL,
    teacher_name TEXT,
    room TEXT,
    schedule_text TEXT,
    time_text TEXT,
    capacity INTEGER CHECK (capacity IS NULL OR capacity > 0),
    start_date TEXT,
    notes TEXT,
    class_status TEXT NOT NULL DEFAULT 'active'
        CHECK (class_status IN ('active', 'completed', 'cancelled', 'inactive')),
    UNIQUE (class_name, academic_year)
);

CREATE TABLE IF NOT EXISTS enrollments (
    enrollment_id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(student_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    class_id INTEGER NOT NULL REFERENCES classes(class_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    start_date TEXT NOT NULL,
    end_date TEXT,
    enrollment_status TEXT NOT NULL DEFAULT 'active'
        CHECK (enrollment_status IN ('active', 'completed', 'withdrawn')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (end_date IS NULL OR end_date >= start_date),
    UNIQUE (enrollment_id, student_id, class_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_enrollments_active_student_class
    ON enrollments(student_id, class_id) WHERE enrollment_status = 'active';

CREATE TABLE IF NOT EXISTS face_images (
    image_id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES people(person_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    image_path TEXT NOT NULL UNIQUE CHECK (length(trim(image_path)) > 0),
    capture_label TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    UNIQUE (image_id, person_id),
    CHECK (instr(image_path, '://') = 0),
    CHECK (substr(image_path, 1, 1) <> '/' AND instr(image_path, ':') = 0)
);

CREATE TABLE IF NOT EXISTS face_embeddings (
    embedding_id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES people(person_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    image_id INTEGER,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dimension INTEGER NOT NULL CHECK (dimension > 0),
    dtype TEXT NOT NULL CHECK (dtype IN ('float32', 'float64')),
    vector_data BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    CHECK (length(vector_data) = dimension * CASE dtype WHEN 'float32' THEN 4 WHEN 'float64' THEN 8 END),
    FOREIGN KEY (image_id, person_id) REFERENCES face_images(image_id, person_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS employee_attendance (
    attendance_id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(employee_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    work_date TEXT NOT NULL,
    check_in_at TEXT,
    check_out_at TEXT,
    check_in_method TEXT CHECK (check_in_method IS NULL OR check_in_method IN ('face', 'manual', 'other')),
    check_out_method TEXT CHECK (check_out_method IS NULL OR check_out_method IN ('face', 'manual', 'other')),
    status TEXT NOT NULL DEFAULT 'present'
        CHECK (status IN ('present', 'late', 'incomplete', 'excused', 'absent')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (check_out_at IS NULL OR check_in_at IS NULL OR check_out_at >= check_in_at)
);

CREATE TABLE IF NOT EXISTS student_attendance (
    student_attendance_id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(student_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    class_id INTEGER NOT NULL REFERENCES classes(class_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    enrollment_id INTEGER,
    attendance_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('present', 'late', 'absent', 'excused')),
    check_in_at TEXT,
    method TEXT CHECK (method IS NULL OR method IN ('face', 'manual', 'other')),
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (student_id, class_id, attendance_date),
    FOREIGN KEY (enrollment_id, student_id, class_id)
        REFERENCES enrollments(enrollment_id, student_id, class_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS employee_leave_requests (
    leave_request_id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(employee_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    leave_type TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    handover_person TEXT,
    attachment_path TEXT,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_by_account_id INTEGER REFERENCES accounts(account_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    reviewed_at TEXT,
    review_note TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (end_date >= start_date),
    CHECK ((status = 'pending' AND reviewed_at IS NULL AND reviewed_by_account_id IS NULL)
        OR (status <> 'pending' AND reviewed_at IS NOT NULL AND reviewed_by_account_id IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS student_leave_requests (
    student_leave_request_id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(student_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    class_id INTEGER REFERENCES classes(class_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    leave_date TEXT NOT NULL,
    session_count REAL CHECK (session_count IS NULL OR session_count > 0),
    submitted_by_type TEXT NOT NULL CHECK (submitted_by_type IN ('guardian', 'student')),
    contact_phone TEXT,
    reason TEXT NOT NULL,
    attachment_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_by_account_id INTEGER REFERENCES accounts(account_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    reviewed_at TEXT,
    review_note TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((status = 'pending' AND reviewed_at IS NULL AND reviewed_by_account_id IS NULL)
        OR (status <> 'pending' AND reviewed_at IS NOT NULL AND reviewed_by_account_id IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS system_settings (
    setting_id INTEGER PRIMARY KEY,
    scope TEXT NOT NULL CHECK (scope IN ('global', 'staff', 'student')),
    setting_key TEXT NOT NULL,
    setting_value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_by_account_id INTEGER REFERENCES accounts(account_id) ON UPDATE CASCADE ON DELETE SET NULL,
    UNIQUE (scope, setting_key)
);

CREATE INDEX IF NOT EXISTS ix_people_full_name ON people(full_name);
CREATE INDEX IF NOT EXISTS ix_employees_department_status ON employees(department_id, employment_status);
CREATE INDEX IF NOT EXISTS ix_enrollments_class_status ON enrollments(class_id, enrollment_status);
CREATE INDEX IF NOT EXISTS ix_face_embeddings_person_active ON face_embeddings(person_id, is_active);
CREATE INDEX IF NOT EXISTS ix_employee_attendance_employee_date ON employee_attendance(employee_id, work_date);
CREATE INDEX IF NOT EXISTS ix_student_attendance_class_date ON student_attendance(class_id, attendance_date);
CREATE INDEX IF NOT EXISTS ix_employee_leave_status_date ON employee_leave_requests(status, start_date);
CREATE INDEX IF NOT EXISTS ix_student_leave_status_date ON student_leave_requests(status, leave_date);

PRAGMA user_version = 1;
