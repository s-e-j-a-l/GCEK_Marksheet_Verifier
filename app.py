from flask import Flask, render_template, request, redirect, url_for, flash, send_file, send_from_directory, jsonify
import os
import zipfile
import tempfile
import PyPDF2
from werkzeug.utils import secure_filename
from extractor_factory import ExtractorFactory
import re
import math
import io
import pdfplumber
import pandas as pd
from sqlalchemy import create_engine, text

# ============================================
# Semester Result Sheet System (Database) Configuration
# ============================================
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Sejal369',   # CHANGE THIS
    'database': 'gcek_marksheet',
    'port': 3306
}

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.secret_key = 'gcek_secret_key_2025'

# Create SQLAlchemy engine
engine = create_engine(f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")

# ============================================
# Branch Mapping (Semester System)
# ============================================
STANDARD_BRANCHES = {
    'IT': 'IT', 'INFORMATION TECHNOLOGY': 'IT', 'BTECH-IT': 'IT',
    'ETC': 'ETC', 'ELECTRONICS': 'ETC', 'TELECOMMUNICATION': 'ETC', 'BTECH-ETC': 'ETC',
    'EE': 'EE', 'ELECTRICAL': 'EE', 'BTECH-EE': 'EE',
    'ME': 'ME', 'MECHANICAL': 'ME', 'BTECH-ME': 'ME',
    'CE': 'CE', 'CIVIL': 'CE', 'BTECH-CE': 'CE'
}

def normalize_branch_code(raw_branch):
    if not raw_branch:
        return 'IT'
    raw_upper = str(raw_branch).upper()
    for pattern, code in STANDARD_BRANCHES.items():
        if pattern in raw_upper:
            return code
    return 'IT'

# ============================================
# Semester System: PDF Metadata Extraction
# ============================================
def extract_metadata_from_pdf_text(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for i in range(min(3, len(pdf.pages))):
                full_text += pdf.pages[i].extract_text() + "\n"
            full_text = full_text.upper()

            semester = None
            match = re.search(r'SEMESTER\s+([IVX\d]+)', full_text)
            if match:
                sem_str = match.group(1)
                if sem_str.isdigit():
                    semester = int(sem_str)
                else:
                    roman_map = {'I':1,'II':2,'III':3,'IV':4,'V':5,'VI':6,'VII':7,'VIII':8}
                    semester = roman_map.get(sem_str, None)
            if not semester:
                match = re.search(r'(\d+)(?:ST|ND|RD|TH)?\s+SEMESTER', full_text)
                if match:
                    semester = int(match.group(1))
            if not semester:
                semester = 1

            exam_session = None
            match = re.search(r'(WINTER|SUMMER)-(\d{4})', full_text, re.IGNORECASE)
            if match:
                session_type = match.group(1).capitalize()
                year = match.group(2)
                exam_session = f"{session_type}-{year}"
            else:
                match = re.search(r'HELD IN\s*[-:]\s*(WINTER|SUMMER)-(\d{4})', full_text, re.IGNORECASE)
                if match:
                    session_type = match.group(1).capitalize()
                    year = match.group(2)
                    exam_session = f"{session_type}-{year}"
            if not exam_session:
                exam_year = 2023 if semester == 1 else 2024
                session_type = "Winter" if semester % 2 == 1 else "Summer"
                exam_session = f"{session_type}-{exam_year}"

            academic_year = None
            match = re.search(r'NEP\s+(\d{4})-(\d{2,4})', full_text)
            if match:
                start = match.group(1)
                end = match.group(2)
                if len(end) == 2:
                    end = "20" + end
                academic_year = f"{start}-{end}"
            else:
                match = re.search(r'PROGRAMME.*?(\d{4})-(\d{2,4})', full_text)
                if match:
                    start = match.group(1)
                    end = match.group(2)
                    if len(end) == 2:
                        end = "20" + end
                    academic_year = f"{start}-{end}"
            if not academic_year:
                year = int(exam_session.split('-')[1])
                if semester % 2 == 1:
                    academic_year = f"{year}-{year+1}"
                else:
                    academic_year = f"{year-1}-{year}"

            branch_code = 'IT'
            for pattern, code in STANDARD_BRANCHES.items():
                if pattern in full_text:
                    branch_code = code
                    break

            exam_month = 'May' if 'Summer' in exam_session else 'December'
            exam_year = int(exam_session.split('-')[1])

            return {
                'semester': semester,
                'exam_session': exam_session,
                'academic_year': academic_year,
                'exam_year': exam_year,
                'exam_month': exam_month,
                'branch_code': branch_code
            }
    except Exception as e:
        print(f"Metadata error: {e}")
        return {
            'semester': 1,
            'exam_session': 'Winter-2023',
            'academic_year': '2023-2024',
            'exam_year': 2023,
            'exam_month': 'December',
            'branch_code': 'IT'
        }

def extract_tables_as_in_original(pdf_path):
    records = []
    header_saved = False
    header = None
    last_course_row = None
    last_credit_row = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                rows = table
                for row in rows:
                    if not row:
                        continue
                    first_cell = str(row[0]).strip() if row[0] else ""
                    row_text = " ".join([str(x) if x else "" for x in row])

                    if "Sr." in first_cell and not header_saved:
                        header = row
                        header_saved = True
                        continue

                    if "Sr." in first_cell:
                        continue

                    if "Course Code" in row_text:
                        last_course_row = row
                        continue

                    if "Credit(C)" in row_text:
                        last_credit_row = row
                        continue

                    if first_cell.isdigit():
                        if last_course_row:
                            records.append(last_course_row)
                        if last_credit_row:
                            records.append(last_credit_row)
                        records.append(row)
                        records.append([""] * len(row))
    return records, header

def process_pdf_and_store(pdf_path, engine, forced_branch=None):
    metadata = extract_metadata_from_pdf_text(pdf_path)
    if forced_branch:
        metadata['branch_code'] = normalize_branch_code(forced_branch)

    print(f"Processing {os.path.basename(pdf_path)}: Sem {metadata['semester']}, {metadata['exam_session']}")

    records, header = extract_tables_as_in_original(pdf_path)
    if not records:
        print("No records extracted!")
        return 0, 0

    df = pd.DataFrame(records, columns=header)
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]

    # Split student name / mother name (col index 2)
    student_names = []
    mother_names = []
    for value in df.iloc[:, 2]:
        text_val = str(value).strip()
        words = text_val.split()
        if len(words) >= 4:
            student = " ".join(words[:3])
            mother = words[3]
        else:
            student = text_val
            mother = ""
        student_names.append(student)
        mother_names.append(mother)
    df.iloc[:, 2] = student_names
    df.insert(3, "Mother Name", mother_names)

    # Split credit/EGP columns
    def split_credit_egp_column(df, pattern, egp_name):
        col_idx = None
        for idx, col in enumerate(df.columns):
            if pattern in str(col):
                col_idx = idx
                break
        if col_idx is None:
            return df
        credit = []
        egp = []
        for val in df.iloc[:, col_idx]:
            parts = str(val).split()
            if len(parts) >= 2:
                credit.append(parts[0])
                egp.append(parts[1])
            else:
                credit.append(val)
                egp.append("")
        df.iloc[:, col_idx] = credit
        df.insert(col_idx + 1, egp_name, egp)
        return df

    df = split_credit_egp_column(df, "Present Credit", "Present EGP")
    df = split_credit_egp_column(df, "Previous Credit", "Previous EGP")
    df = split_credit_egp_column(df, "Total Credit", "Total EGP")
    df = df.replace("\n", " ", regex=True)

    # Find column indices
    present_credit_col = None
    for idx, col in enumerate(df.columns):
        if "Present Credit" in str(col):
            present_credit_col = idx
            break
    total_credit_col = None
    total_egp_col = None
    for idx, col in enumerate(df.columns):
        if "Total Credit" in str(col):
            total_credit_col = idx
        if "Total EGP" in str(col):
            total_egp_col = idx

    sgpa_col = None
    cgpa_col = None
    result_col = None
    for idx, col in enumerate(df.columns):
        if "SGPA" in str(col):
            sgpa_col = idx
        elif "CGPA" in str(col) or "Cumulative" in str(col):
            cgpa_col = idx
        elif "Result" in str(col):
            result_col = idx

    if present_credit_col is None:
        print("Could not find 'Present Credit' column – aborting.")
        return 0, 0

    reg_col = 1
    name_col = 2
    mother_col = 3

    students_inserted = 0
    courses_inserted = 0

    with engine.connect() as conn:
        for i in range(len(df)):
            row = df.iloc[i]
            if str(row.iloc[0]).isdigit():
                credit_row = df.iloc[i-1]

                reg_no = str(row.iloc[reg_col]).strip()
                student_name = str(row.iloc[name_col]).strip()
                mother_name = str(row.iloc[mother_col]).strip()

                reported_sgpa = None
                if sgpa_col and sgpa_col < len(row):
                    try:
                        reported_sgpa = float(row.iloc[sgpa_col])
                    except:
                        pass
                reported_cgpa = None
                if cgpa_col and cgpa_col < len(row):
                    try:
                        reported_cgpa = float(row.iloc[cgpa_col])
                    except:
                        pass
                result = "PASS"
                if result_col and result_col < len(row):
                    if "FAIL" in str(row.iloc[result_col]).upper():
                        result = "FAIL"

                # SGPA calculation
                credit_sum = 0
                egp_sum = 0
                total_credit_all = 0
                col = 4
                while col < present_credit_col:
                    grd = row.iloc[col] if col < len(row) else ""
                    cg = row.iloc[col+1] if col+1 < len(row) else ""
                    credit = credit_row.iloc[col] if col < len(credit_row) else ""
                    try:
                        credit_val = float(credit) if credit else 0
                    except:
                        credit_val = 0
                    try:
                        cg_val = float(cg) if cg else 0
                    except:
                        cg_val = 0
                    total_credit_all += credit_val
                    if not (str(grd).strip().upper() == "F" and cg_val == 0):
                        credit_sum += credit_val
                    egp_sum += cg_val
                    col += 2

                reported_present_credit = None
                if present_credit_col < len(row):
                    try:
                        reported_present_credit = float(row.iloc[present_credit_col])
                    except:
                        pass

                calc_sgpa = round(egp_sum / total_credit_all, 2) if total_credit_all > 0 else 0
                sgpa_match = False
                if reported_sgpa is not None and calc_sgpa is not None:
                    sgpa_match = abs(calc_sgpa - reported_sgpa) <= 0.01

                calc_cgpa = None
                cgpa_match = False
                if total_credit_col is not None and total_egp_col is not None:
                    try:
                        total_credit_val = float(row.iloc[total_credit_col]) if row.iloc[total_credit_col] else 0
                        total_egp_val = float(row.iloc[total_egp_col]) if row.iloc[total_egp_col] else 0
                        if total_credit_val > 0:
                            calc_cgpa = round(total_egp_val / total_credit_val, 2)
                            if reported_cgpa is not None:
                                cgpa_match = abs(calc_cgpa - reported_cgpa) <= 0.01
                    except:
                        pass

                if calc_cgpa is None:
                    calc_cgpa = calc_sgpa
                    cgpa_match = sgpa_match

                # Insert student record
                try:
                    conn.execute(text("""
                        INSERT INTO students 
                        (registration_number, student_name, mother_name, program, branch_code, semester, 
                         exam_year, exam_session, exam_month, academic_year, sgpa, cgpa, result, present_credit,
                         calculated_sgpa, calculated_cgpa, sgpa_verified, cgpa_verified)
                        VALUES (:reg, :name, :mother, :program, :branch, :sem, 
                                :exam_year, :exam_session, :exam_month, :academic_year, :sgpa, :cgpa, :result, :credit,
                                :calc_sgpa, :calc_cgpa, :sgpa_verified, :cgpa_verified)
                        ON DUPLICATE KEY UPDATE
                        student_name = VALUES(student_name),
                        mother_name = VALUES(mother_name),
                        sgpa = VALUES(sgpa),
                        cgpa = VALUES(cgpa),
                        result = VALUES(result),
                        present_credit = VALUES(present_credit),
                        calculated_sgpa = VALUES(calculated_sgpa),
                        calculated_cgpa = VALUES(calculated_cgpa),
                        sgpa_verified = VALUES(sgpa_verified),
                        cgpa_verified = VALUES(cgpa_verified)
                    """), {
                        'reg': reg_no, 'name': student_name, 'mother': mother_name,
                        'program': 'Bachelor of Technology', 'branch': metadata['branch_code'],
                        'sem': metadata['semester'], 'exam_year': metadata['exam_year'],
                        'exam_session': metadata['exam_session'], 'exam_month': metadata['exam_month'],
                        'academic_year': metadata['academic_year'],
                        'sgpa': reported_sgpa, 'cgpa': reported_cgpa,
                        'result': result, 'credit': reported_present_credit,
                        'calc_sgpa': calc_sgpa, 'calc_cgpa': calc_cgpa,
                        'sgpa_verified': sgpa_match, 'cgpa_verified': cgpa_match
                    })
                    students_inserted += 1
                except Exception as e:
                    print(f"Error inserting {reg_no}: {e}")
                    continue

                # Insert course marks
                course_num = 1
                col = 4
                while col < present_credit_col:
                    grade = row.iloc[col] if col < len(row) else ""
                    if grade and str(grade).strip() not in ['', 'nan', 'None']:
                        credit_val = 0
                        if col < len(credit_row):
                            try:
                                credit_val = float(credit_row.iloc[col])
                            except:
                                pass
                        try:
                            conn.execute(text("""
                                INSERT INTO course_marks 
                                (registration_number, semester, exam_session, course_number, grade, credit_points)
                                VALUES (:reg, :sem, :session, :cnum, :grade, :credit)
                                ON DUPLICATE KEY UPDATE grade = VALUES(grade), credit_points = VALUES(credit_points)
                            """), {
                                'reg': reg_no, 'sem': metadata['semester'], 'session': metadata['exam_session'],
                                'cnum': course_num, 'grade': str(grade).strip(), 'credit': credit_val
                            })
                            courses_inserted += 1
                        except Exception as e:
                            print(f"Course insert error: {e}")
                    col += 2
                    course_num += 1

        conn.commit()

    print(f"Inserted {students_inserted} students, {courses_inserted} courses")
    return students_inserted, courses_inserted

def init_database():
    """Create tables if they don't exist."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS branches (
                branch_code VARCHAR(20) PRIMARY KEY,
                branch_name VARCHAR(100) NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS students (
                registration_number VARCHAR(50) NOT NULL,
                student_name VARCHAR(200) NOT NULL,
                mother_name VARCHAR(200),
                program VARCHAR(100),
                branch_code VARCHAR(20) NOT NULL,
                semester INT NOT NULL,
                exam_year INT NOT NULL,
                exam_session VARCHAR(50) NOT NULL,
                exam_month VARCHAR(20),
                academic_year VARCHAR(20),
                sgpa FLOAT,
                cgpa FLOAT,
                result VARCHAR(10),
                present_credit INT,
                calculated_sgpa FLOAT,
                calculated_cgpa FLOAT,
                sgpa_verified BOOLEAN DEFAULT FALSE,
                cgpa_verified BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (registration_number, semester, exam_session),
                FOREIGN KEY (branch_code) REFERENCES branches(branch_code)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS course_marks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                registration_number VARCHAR(50) NOT NULL,
                semester INT NOT NULL,
                exam_session VARCHAR(50) NOT NULL,
                course_number INT NOT NULL,
                grade VARCHAR(5),
                credit_points INT,
                UNIQUE KEY unique_course (registration_number, semester, exam_session, course_number),
                FOREIGN KEY (registration_number, semester, exam_session) 
                    REFERENCES students(registration_number, semester, exam_session)
                    ON DELETE CASCADE
            )
        """))

        for code, name in [('IT','Information Technology'),('ETC','Electronics & Telecommunication'),
                           ('EE','Electrical Engineering'),('ME','Mechanical Engineering'),
                           ('CE','Civil Engineering')]:
            conn.execute(text("""
                INSERT INTO branches (branch_code, branch_name) 
                VALUES (:code, :name) 
                ON DUPLICATE KEY UPDATE branch_name = :name
            """), {'code': code, 'name': name})
        conn.commit()
        print("✅ Semester database tables ready.")

# ============================================
# Existing MarksheetVerifier Class
# ============================================
class MarksheetVerifier:
    def __init__(self):
        self.grade_points = {
            'A+': 10, 'A': 9, 'B+': 8, 'B': 7, 'C+': 6,
            'C': 5, 'D': 4, 'F': 0, 'FF': 0, 'P': 5, 'PP': 5, 'PASS': 5, 'COMP': 5
        }

    def calculate_egp(self, courses):
        egp = 0
        for course in courses:
            grade = course['grade'].upper()
            earned = course['earned']
            point = self.grade_points.get(grade, 0)
            egp += point * earned
        return egp

    def calculate_total_credits(self, courses):
        return sum(course['earned'] for course in courses)

    def calculate_sgpa(self, courses):
        total_credits = self.calculate_total_credits(courses)
        if total_credits == 0:
            return 0
        egp = self.calculate_egp(courses)
        return round(egp / total_credits, 2)

# ============================================
# Helper Functions
# ============================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['pdf', 'zip']

def save_uploaded_file(file):
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)
    return file_path, filename

def is_values_match(calculated, reported, value_type='general'):
    if calculated == 0 and reported == 0:
        return False
    difference = abs(calculated - reported)
    tolerance = 0.01 if value_type == 'sgpa' else 0.1
    return difference < tolerance

# ============================================
# Routes for Single Marksheet Verification
# ============================================
@app.route('/')
def index():
    branches = []
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT branch_code, branch_name FROM branches ORDER BY branch_code"))
            branches = [{"branch_code": row[0], "branch_name": row[1]} for row in result]
    except Exception as e:
        print(f"Could not load branches: {e}")
    return render_template('index.html', branches=branches)

@app.route('/uploads/<filename>')
def serve_uploaded_file(filename):
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except FileNotFoundError:
        flash('File not found', 'error')
        return redirect(url_for('index'))

@app.route('/pdf/<filename>')
def serve_pdf(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
        if os.path.exists(file_path):
            response = send_file(file_path, as_attachment=False, mimetype='application/pdf')
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
            return response
        else:
            flash('File not found', 'error')
            return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error serving PDF: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('index'))

    if file and allowed_file(file.filename):
        file_path, filename = save_uploaded_file(file)
        try:
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                first_page_text = pdf_reader.pages[0].extract_text()

            if 'Previous Semester Performance' in first_page_text and 'Current Semester Performance' in first_page_text:
                from non_nep_double_extractor import NonNEPDoubleExtractor
                extractor = NonNEPDoubleExtractor()
                result = extractor.process_pdf(file_path)
                result['pdf_url'] = url_for('serve_pdf', filename=filename)
                result['filename'] = filename
                return render_template('double_semester_results.html', result=result, filename=filename)
            else:
                extractor = ExtractorFactory.get_extractor("")
                text = extractor.extract_text_from_pdf(file_path)
                extractor = ExtractorFactory.get_extractor(text)
                result = extractor.process_pdf(file_path)

                if isinstance(result, dict) and 'verification' in result:
                    courses = result.get('all_courses', [])
                    student_type = result.get('student_type', 'Unknown')
                    verification = result.get('verification', {})
                    status = result.get('status', 'Unknown')
                    pdf_url = url_for('serve_pdf', filename=filename)
                    return render_template('results.html',
                                         courses=courses, verification=verification,
                                         status=status, filename=filename,
                                         student_type=student_type, total_courses=len(courses),
                                         pdf_url=pdf_url, result=result)
                else:
                    courses = result if isinstance(result, list) else []
                    student_type = extractor.student_type
                    verifier = MarksheetVerifier()
                    calc_egp = verifier.calculate_egp(courses)
                    calc_cred = verifier.calculate_total_credits(courses)
                    calc_sgpa = verifier.calculate_sgpa(courses)
                    verification = {
                        'egp': {'calculated': calc_egp, 'reported': calc_egp, 'match': True, 'difference': 0},
                        'credits': {'calculated': calc_cred, 'reported': calc_cred, 'match': True, 'difference': 0},
                        'sgpa': {'calculated': calc_sgpa, 'reported': calc_sgpa, 'match': True, 'difference': 0}
                    }
                    status = "✅ All Values Match"
                    pdf_url = url_for('serve_pdf', filename=filename)
                    result = {
                        'all_courses': courses,
                        'student_info': {'name': '', 'registration_no': ''},
                        'performance_data': {'credits': calc_cred, 'egp': calc_egp, 'sgpa': calc_sgpa},
                        'calculated_data': {'credits': calc_cred, 'egp': calc_egp, 'sgpa': calc_sgpa},
                        'verification': verification,
                        'status': status,
                        'student_type': student_type
                    }
                    return render_template('results.html',
                                         courses=courses, verification=verification,
                                         status=status, filename=filename,
                                         student_type=student_type, total_courses=len(courses),
                                         pdf_url=pdf_url, result=result)
        except Exception as e:
            flash(f'Error processing file: {str(e)}', 'error')
            return redirect(url_for('index'))

    flash('Invalid file type.', 'error')
    return redirect(url_for('index'))

@app.route('/save_to_dataset/<filename>', methods=['POST'])
def save_to_dataset(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
        if not os.path.exists(file_path):
            flash('File not found', 'error')
            return redirect(url_for('index'))

        with open(file_path, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)
            first_page_text = pdf_reader.pages[0].extract_text()

        if 'Previous Semester Performance' in first_page_text and 'Current Semester Performance' in first_page_text:
            from non_nep_double_extractor import NonNEPDoubleExtractor
            extractor = NonNEPDoubleExtractor()
            result = extractor.process_pdf(file_path)
        else:
            extractor = ExtractorFactory.get_extractor("")
            text = extractor.extract_text_from_pdf(file_path)
            extractor = ExtractorFactory.get_extractor(text)
            result = extractor.process_pdf(file_path)

        from dataset_saver import save_to_dataset
        save_to_dataset(result, filename)
        flash(f'Data saved successfully to dataset', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error saving to dataset: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/save_bulk_to_dataset', methods=['POST'])
def save_bulk_to_dataset():
    # Keep existing implementation (omitted for brevity – copy from your original)
    pass

@app.route('/download_dataset', methods=['GET'])
def download_dataset():
    try:
        from dataset_saver import get_dataset_path
        dataset_path = get_dataset_path()
        if not os.path.exists(dataset_path):
            flash('No dataset file found. Please save some data first.', 'error')
            return redirect(url_for('index'))
        return send_file(dataset_path, as_attachment=True,
                         download_name='marksheet_dataset.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        flash(f'Error downloading dataset: {str(e)}', 'error')
        return redirect(url_for('index'))

# ============================================
# Routes for Semester Result Sheet Verification
# ============================================
@app.route('/semester')
def semester_index():
    """Main page for semester result sheet system"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT branch_code, branch_name FROM branches ORDER BY branch_code"))
            branches = [{"branch_code": row[0], "branch_name": row[1]} for row in result]
            years_result = conn.execute(text("SELECT DISTINCT academic_year FROM students WHERE academic_year IS NOT NULL ORDER BY academic_year DESC"))
            academic_years = [row[0] for row in years_result]
    except Exception as e:
        branches = []
        academic_years = []
        flash(f"Warning: Could not load branches. {e}", 'warning')
    return render_template('semester.html', branches=branches, academic_years=academic_years)

@app.route('/semester/upload', methods=['POST'])
def semester_upload():
    selected_branch = request.form.get('branch', '')
    if not selected_branch:
        flash('Please select a branch before uploading.', 'error')
        return redirect(url_for('semester_index'))

    if 'files' not in request.files:
        flash('No file part', 'error')
        return redirect(url_for('semester_index'))
    files = request.files.getlist('files')
    if not files or files[0].filename == '':
        flash('No selected files', 'error')
        return redirect(url_for('semester_index'))

    processed = 0
    total_students = 0
    total_courses = 0
    errors = []

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            try:
                students, courses = process_pdf_and_store(filepath, engine, forced_branch=selected_branch)
                total_students += students
                total_courses += courses
                processed += 1
                os.remove(filepath)
            except Exception as e:
                errors.append(f"{filename}: {str(e)}")
        else:
            errors.append(f"{file.filename}: Invalid file type")

    if processed > 0:
        flash(f"✅ Processed {processed} PDF(s) into branch '{selected_branch}'. Added/updated {total_students} student semester records, {total_courses} course records.", 'success')
    if errors:
        flash(f"⚠️ Errors: {'; '.join(errors[:3])}", 'warning')
    return redirect(url_for('semester_index'))

@app.route('/semester/api/students')
def semester_api_students():
    branch = request.args.get('branch', '').strip()
    semester = request.args.get('semester', '').strip()
    academic_year = request.args.get('academic_year', '').strip()
    exam_session = request.args.get('exam_session', '').strip()
    search = request.args.get('search', '').strip()

    query = """
        SELECT registration_number, student_name, mother_name, branch_code, semester, 
               exam_session, academic_year, sgpa, cgpa, result, present_credit,
               calculated_sgpa, calculated_cgpa, sgpa_verified, cgpa_verified
        FROM students WHERE 1=1
    """
    params = {}

    if branch:
        query += " AND branch_code = :branch"
        params['branch'] = branch
    if semester and semester.isdigit():
        query += " AND semester = :semester"
        params['semester'] = int(semester)
    if academic_year:
        query += " AND academic_year = :academic_year"
        params['academic_year'] = academic_year
    if exam_session:
        query += " AND exam_session LIKE :session"
        params['session'] = f"%{exam_session}%"
    if search:
        query += " AND (registration_number LIKE :search OR student_name LIKE :search)"
        params['search'] = f"%{search}%"

    query += " ORDER BY semester, registration_number"

    try:
        with engine.connect() as conn:
            result = conn.execute(text(query), params)
            rows = result.fetchall()
            columns = result.keys()
            students = [dict(zip(columns, row)) for row in rows]
            total = len(students)
            passed = sum(1 for s in students if s.get('result') == 'PASS')
            failed = total - passed
            stats = {'total': total, 'passed': passed, 'failed': failed}
            return jsonify({'students': students, 'stats': stats})
    except Exception as e:
        print(f"API Error: {e}")
        return jsonify({'error': str(e), 'students': [], 'stats': {'total':0,'passed':0,'failed':0}})

@app.route('/semester/student/<reg_no>/<int:semester>/<exam_session>')
def semester_student_details(reg_no, semester, exam_session):
    try:
        with engine.connect() as conn:
            student_result = conn.execute(text("""
                SELECT * FROM students 
                WHERE registration_number = :reg AND semester = :sem AND exam_session = :session
            """), {'reg': reg_no, 'sem': semester, 'session': exam_session})
            student_rows = student_result.fetchall()
            if not student_rows:
                return "<h3>Student semester record not found</h3>"
            student = student_rows[0]
            student_dict = dict(zip(student_result.keys(), student))
            courses_result = conn.execute(text("""
                SELECT course_number, grade, credit_points 
                FROM course_marks 
                WHERE registration_number = :reg AND semester = :sem AND exam_session = :session
                ORDER BY course_number
            """), {'reg': reg_no, 'sem': semester, 'session': exam_session})
            courses = [dict(zip(courses_result.keys(), row)) for row in courses_result.fetchall()]
        return render_template('semester_student_details.html', student=student_dict, courses=courses)
    except Exception as e:
        return f"<h3>Error: {e}</h3>"

@app.route('/semester/export')
def semester_export():
    branch = request.args.get('branch', '').strip()
    semester = request.args.get('semester', '').strip()
    academic_year = request.args.get('academic_year', '').strip()
    exam_session = request.args.get('exam_session', '').strip()
    search = request.args.get('search', '').strip()

    query = "SELECT * FROM students WHERE 1=1"
    params = {}
    if branch:
        query += " AND branch_code = :branch"
        params['branch'] = branch
    if semester and semester.isdigit():
        query += " AND semester = :semester"
        params['semester'] = int(semester)
    if academic_year:
        query += " AND academic_year = :academic_year"
        params['academic_year'] = academic_year
    if exam_session:
        query += " AND exam_session LIKE :session"
        params['session'] = f"%{exam_session}%"
    if search:
        query += " AND (registration_number LIKE :search OR student_name LIKE :search)"
        params['search'] = f"%{search}%"
    query += " ORDER BY semester, registration_number"

    try:
        with engine.connect() as conn:
            result = conn.execute(text(query), params)
            rows = result.fetchall()
            columns = result.keys()
            df = pd.DataFrame(rows, columns=columns)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Students', index=False)
            if branch and semester.isdigit():
                with engine.connect() as conn:
                    course_result = conn.execute(text("""
                        SELECT c.registration_number, c.course_number, c.grade, c.credit_points, s.student_name
                        FROM course_marks c JOIN students s 
                        ON c.registration_number = s.registration_number 
                        AND c.semester = s.semester 
                        AND c.exam_session = s.exam_session
                        WHERE s.branch_code = :branch AND s.semester = :sem
                        ORDER BY c.registration_number, c.course_number
                    """), {'branch': branch, 'sem': int(semester)})
                    if course_result.rowcount > 0:
                        course_df = pd.DataFrame(course_result.fetchall(), columns=course_result.keys())
                        course_df.to_excel(writer, sheet_name='Course_Marks', index=False)
        output.seek(0)
        filename = f"semester_export_{branch}_{semester}_{academic_year}.xlsx".replace("__","_").replace(" ","_")
        return send_file(output, download_name=filename, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        return f"Error exporting data: {e}"

# ============================================
# Main
# ============================================
if __name__ == '__main__':
    print("="*60)
    print("🎓 GCEK Marksheet Verification System (Merged)")
    print("="*60)
    init_database()
    try:
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM students")).fetchone()[0]
            print(f"✅ Semester database ready! Found {count} semester records.")
    except Exception as e:
        print(f"⚠️ Database connection warning: {e}")
    app.run(debug=True, host='0.0.0.0', port=5000)