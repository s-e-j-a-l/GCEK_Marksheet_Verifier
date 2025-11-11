from flask import Flask, render_template, request, redirect, url_for, flash
import pdfplumber
import pandas as pd
import re
from pathlib import Path
import os
import io
import zipfile
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# -------------------- Core Classes --------------------

class MarksheetVerifier:
    def __init__(self):
        self.grade_points = {
            'A+': 10, 'A': 9, 'B+': 8, 'B': 7, 'C+': 6,
            'C': 5, 'D': 4, 'F': 0, 'FF': 0, 'U': 0, 'UU': 0,
            'P': 5, 'PP': 5, 'PASS': 5, 'COMP': 5
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


class UniversalMarksheetExtractor:
    def __init__(self):
        self.courses = []
        self.student_type = "Unknown"

    def extract_text_from_pdf(self, pdf_path):
        text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    if page.extract_text():
                        text += page.extract_text() + "\n"
                    for table in page.extract_tables():
                        for row in table:
                            clean_row = [str(cell or '').strip() for cell in row]
                            text += ' | '.join(clean_row) + "\n"
        except Exception as e:
            print(f"Error reading PDF: {e}")
        return text

    def clean_text(self, text):
        return re.sub(r'\s+', ' ', text).strip()

    def is_valid_grade(self, grade):
        if not grade:
            return False
        grade = re.sub(r'[^A-Z\+\-]', '', grade.upper().strip())
        valid = ['A','A+','B','B+','C','C+','D','D+','F','FF','U','UU','P','PP','PASS','COMP']
        return grade in valid

    def is_valid_course_code(self, code):
        if not code:
            return False
        code = code.upper().strip()
        patterns = [
            r'^[A-Z]{2,4}\d{3,4}[A-Z]?\*?$',
            r'^[A-Z]{2,4}-\d{3,4}[A-Z]?\*?$'
        ]
        return any(re.match(p, code) for p in patterns)

    def is_valid_course_data(self, code, credit, earned, grade):
        if not self.is_valid_course_code(code): return False
        if not (0.5 <= credit <= 5.0): return False
        if not (0 <= earned <= credit): return False
        if not self.is_valid_grade(grade): return False
        return True

    def detect_student_type(self, text):
        """Detect if the student is NEP or Non-NEP based on performance table structure"""
        
        # NEP Pattern: Has "Current Semester Performance" and "Cummulative/Cumulative Performance"
        has_current_sem_performance = "Current Semester Performance" in text
        has_cumulative_performance = "Cummulative Performance" in text or "Cumulative Performance" in text
        
        # Non-NEP Pattern: Has "Previous Semester Performance", "Current Semester Performance", "Cummulative Performance"
        has_previous_sem_performance = "Previous Semester Performance" in text
        
        if has_current_sem_performance and has_cumulative_performance and not has_previous_sem_performance:
            return "NEP Student"
        elif has_previous_sem_performance and has_current_sem_performance and has_cumulative_performance:
            return "Non-NEP Student"
        else:
            # Default to NEP if we can't determine clearly
            return "NEP Student"

    def extract_courses_nep(self, text):
        """Extract courses from NEP format marksheets"""
        courses = []
        lines = text.split('\n')
        
        in_course_section = False
        
        for line in lines:
            line_clean = self.clean_text(line)
            if not line_clean:
                continue
                
            # Start of course table - various patterns for NEP
            if any(header in line for header in ['Course Code', 'Sr.No.', 'MSE']):
                in_course_section = True
                continue
                
            # End of course section
            if "Current Semester Performance" in line or "Remarks" in line:
                in_course_section = False
                continue
                
            if in_course_section:
                # Look for course codes
                code_match = re.search(r'([A-Z]{2,4}\d{3,4}[A-Z]?\*?)', line_clean)
                if code_match:
                    code = code_match.group(1).upper()
                    
                    # Find grade - usually at the end of the line
                    grade = None
                    words = line_clean.split()
                    for word in reversed(words):
                        if self.is_valid_grade(word):
                            grade = word.upper()
                            break
                    
                    if not grade:
                        continue
                        
                    # Extract credits and earned credits
                    numbers = re.findall(r'\b\d+\.?\d*\b', line_clean)
                    credit_values = []
                    
                    for num in numbers:
                        try:
                            val = float(num)
                            if 0.5 <= val <= 5.0:  # Credit values are typically in this range
                                credit_values.append(val)
                        except ValueError:
                            continue
                    
                    if len(credit_values) >= 2:
                        # Try different combinations to find valid course data
                        for i in range(len(credit_values) - 1):
                            credit = credit_values[i]
                            earned = credit_values[i + 1]
                            
                            if self.is_valid_course_data(code, credit, earned, grade):
                                courses.append({
                                    'course_code': code,
                                    'credit': credit,
                                    'earned': earned,
                                    'grade': grade
                                })
                                break
        
        return courses

    def extract_courses_non_nep(self, text):
        """Extract courses from Non-NEP format marksheets"""
        courses = []
        lines = text.split('\n')
        
        current_semester = None
        in_course_section = False
        
        for line in lines:
            line_clean = self.clean_text(line)
            if not line_clean:
                continue
                
            # Detect semester changes
            sem_match = re.search(r'Semester\s*:\s*([IVX]+)', line_clean, re.IGNORECASE)
            if sem_match:
                current_semester = sem_match.group(1)
                in_course_section = True
                continue
                
            # Course table headers
            if any(header in line for header in ['Course Code', 'Course Name']):
                in_course_section = True
                continue
                
            # End of course section
            if 'Performance' in line and ('Previous' in line or 'Current' in line):
                in_course_section = False
                continue
                
            if in_course_section and current_semester:
                # Extract course data
                code_match = re.search(r'([A-Z]{2,4}\d{3,4}[A-Z]?\*?)', line_clean)
                if code_match:
                    code = code_match.group(1).upper()
                    
                    # Find grade
                    grade = None
                    words = line_clean.split()
                    for word in reversed(words):
                        if self.is_valid_grade(word):
                            grade = word.upper()
                            break
                    
                    if not grade:
                        continue
                        
                    # Extract credits and earned credits
                    numbers = re.findall(r'\b\d+\.?\d*\b', line_clean)
                    if len(numbers) >= 2:
                        try:
                            # In Non-NEP format, credits usually come before earned credits
                            credit = float(numbers[-2])
                            earned = float(numbers[-1])
                            
                            if self.is_valid_course_data(code, credit, earned, grade):
                                courses.append({
                                    'course_code': code,
                                    'credit': credit,
                                    'earned': earned,
                                    'grade': grade,
                                    'semester': current_semester
                                })
                        except ValueError:
                            continue
        
        return courses

    def remove_duplicates(self, courses):
        seen, unique = set(), []
        for c in courses:
            key = (c['course_code'], c.get('semester', ''))
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique

    def process_pdf(self, pdf_path):
        text = self.extract_text_from_pdf(pdf_path)
        if not text.strip(): 
            return []
        
        # Detect student type
        self.student_type = self.detect_student_type(text)
        
        # Extract courses based on student type
        if self.student_type == "NEP Student":
            courses = self.extract_courses_nep(text)
        else:
            courses = self.extract_courses_non_nep(text)
        
        all_courses = self.remove_duplicates(courses)
        return all_courses


# -------------------- Helper Functions --------------------

def extract_reported_values(text, student_type):
    """Extract reported EGP, Credits, and SGPA"""
    egp = credits = sgpa = 0
    
    # Pattern for performance tables
    patterns = [
        r'Current Semester Performance.*?(\d+)\s+(\d+)\s+(\d+\.\d+)',
        r'Credits\s*(\d+)\s*EGP\s*(\d+)\s*SGPA\s*(\d+\.\d+)',
        r'Credits\s*(\d+)\s+(\d+)\s+(\d+\.\d+)'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
        for match in matches:
            try:
                c, e, s = float(match[0]), float(match[1]), float(match[2])
                if 10 <= c <= 40 and 50 <= e <= 400 and 5.0 <= s <= 10.0:
                    credits, egp, sgpa = c, e, s
                    break
            except (ValueError, IndexError):
                continue
    
    # Fallback method
    if egp == 0 or credits == 0 or sgpa == 0:
        nums = re.findall(r'\d+\.?\d*', text)
        possible = [float(x) for x in nums if float(x) > 0]
        for i in range(len(possible)-2):
            if (10 <= possible[i] <= 40 and 
                50 <= possible[i+1] <= 400 and 
                5.0 <= possible[i+2] <= 10.0):
                credits, egp, sgpa = possible[i], possible[i+1], possible[i+2]
                break
    
    return egp, credits, sgpa


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['pdf', 'zip']


# -------------------- Routes --------------------

@app.route('/')
def index():
    return render_template('index.html')


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
        filename = secure_filename(file.filename)
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(path)

        extractor = UniversalMarksheetExtractor()
        courses = extractor.process_pdf(path)
        student_type = extractor.student_type
        
        if not courses:
            flash('No data extracted.', 'error')
            return redirect(url_for('index'))

        text = extractor.extract_text_from_pdf(path)
        rep_egp, rep_cred, rep_sgpa = extract_reported_values(text, student_type)

        verifier = MarksheetVerifier()
        calc_egp = verifier.calculate_egp(courses)
        calc_cred = verifier.calculate_total_credits(courses)
        calc_sgpa = verifier.calculate_sgpa(courses)

        verification = {
            'egp': {'calculated': calc_egp, 'reported': rep_egp, 'match': abs(calc_egp - rep_egp) < 0.1},
            'credits': {'calculated': calc_cred, 'reported': rep_cred, 'match': abs(calc_cred - rep_cred) < 0.1},
            'sgpa': {'calculated': calc_sgpa, 'reported': rep_sgpa, 'match': abs(calc_sgpa - rep_sgpa) < 0.1}
        }

        return render_template('results.html', 
                             courses=courses, 
                             verification=verification, 
                             filename=filename,
                             student_type=student_type,
                             total_courses=len(courses))

    flash('Invalid file type.', 'error')
    return redirect(url_for('index'))


@app.route('/upload_bulk', methods=['POST'])
def upload_bulk():
    if 'bulk_files' not in request.files:
        flash('No files selected', 'error')
        return redirect(url_for('index'))

    files = request.files.getlist('bulk_files')
    results = []

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)

            if filename.lower().endswith('.zip'):
                with zipfile.ZipFile(save_path, 'r') as zip_ref:
                    zip_ref.extractall(app.config['UPLOAD_FOLDER'])
                for f in os.listdir(app.config['UPLOAD_FOLDER']):
                    if f.lower().endswith('.pdf'):
                        process_path = os.path.join(app.config['UPLOAD_FOLDER'], f)
                        results.append(process_single_pdf(process_path, f))
            else:
                results.append(process_single_pdf(save_path, filename))

    return render_template('bulk_results.html', results=results)


def process_single_pdf(filepath, filename):
    try:
        extractor = UniversalMarksheetExtractor()
        courses = extractor.process_pdf(filepath)
        student_type = extractor.student_type
        
        if not courses:
            return {'filename': filename, 'error': 'No data extracted'}

        text = extractor.extract_text_from_pdf(filepath)
        rep_egp, rep_cred, rep_sgpa = extract_reported_values(text, student_type)

        verifier = MarksheetVerifier()
        calc_egp = verifier.calculate_egp(courses)
        calc_cred = verifier.calculate_total_credits(courses)
        calc_sgpa = verifier.calculate_sgpa(courses)

        all_match = (
            abs(calc_egp - rep_egp) < 0.1 and
            abs(calc_cred - rep_cred) < 0.1 and
            abs(calc_sgpa - rep_sgpa) < 0.1
        )

        return {
            'filename': filename,
            'student_type': student_type,
            'calculated': {'egp': calc_egp, 'credits': calc_cred, 'sgpa': calc_sgpa},
            'reported': {'egp': rep_egp, 'credits': rep_cred, 'sgpa': rep_sgpa},
            'status': '✅ Correct' if all_match else '❌ Wrong'
        }
    except Exception as e:
        return {'filename': filename, 'error': str(e)}


# -------------------- Main --------------------

if __name__ == '__main__':
    app.run(debug=True)