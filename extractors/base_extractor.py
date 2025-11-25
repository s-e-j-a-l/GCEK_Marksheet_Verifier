import pdfplumber
import re

class BaseExtractor:
    def __init__(self):
        self.courses = []
        self.student_type = "Unknown"

    def extract_text_from_pdf(self, pdf_path):
        """Extract text with better table handling"""
        full_text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    # Extract tables
                    tables = page.extract_tables({
                        "vertical_strategy": "lines", 
                        "horizontal_strategy": "lines",
                        "snap_tolerance": 3
                    })
                    
                    for table in tables:
                        for row in table:
                            clean_row = []
                            for cell in row:
                                cell_text = str(cell or '').strip()
                                cell_text = re.sub(r'\s+', ' ', cell_text)
                                clean_row.append(cell_text)
                            table_line = ' | '.join(clean_row)
                            full_text += table_line + "\n"
                    
                    # Extract text
                    text = page.extract_text()
                    if text:
                        full_text += text + "\n"
                        
        except Exception as e:
            print(f"Error extracting PDF: {e}")
        return full_text

    def clean_text(self, text):
        """Clean text while preserving structure"""
        if not text:
            return ""
        text = re.sub(r'[^\S\n]+', ' ', text)
        return text.strip()

    def is_valid_grade(self, grade):
        if not grade:
            return False
        grade = re.sub(r'[^A-Z\+\-]', '', grade.upper().strip())
        valid_grades = ['A','A+','B','B+','C','C+','D','D+','F','FF','U','UU','P','PP','PASS','COMP']
        return grade in valid_grades

    def is_valid_course_code(self, code):
        if not code:
            return False
        code = code.upper().strip()
        patterns = [
            r'^[A-Z]{2,4}\d{3,4}[A-Z]?\*?$',
            r'^[A-Z]{2,4}-\d{3,4}[A-Z]?\*?$',
            r'^CC\d+$'
        ]
        return any(re.match(p, code) for p in patterns)

    def extract_course_smart(self, line):
        """Smart course extraction using multiple strategies"""
        # Strategy 1: Look for course code first
        code_match = re.search(r'([A-Z]{2,4}\d{3,4}[A-Z]?\*?|CC\d+)', line)
        if not code_match:
            return None
            
        course_code = code_match.group(1).upper()
        
        # Strategy 2: Find grade using multiple approaches
        grade = self.find_grade_in_line(line)
        if not grade:
            return None
        
        # Strategy 3: Extract credit numbers using robust approach
        credit_data = self.extract_credit_data(line)
        if not credit_data:
            return None
            
        credit, earned = credit_data
        
        # Validate the course data
        if self.is_valid_course_data(course_code, credit, earned, grade):
            return {
                'course_code': course_code,
                'credit': credit,
                'earned': earned,
                'grade': grade
            }
        
        return None

    def find_grade_in_line(self, line):
        """Find grade using multiple strategies"""
        # Strategy 1: Look at the end of line (most common)
        words = line.split()
        for word in reversed(words):
            if self.is_valid_grade(word):
                return word.upper()
        
        # Strategy 2: Look for single capital letter grades
        grade_match = re.search(r'\b([A-Z][\+]?)\b', line)
        if grade_match and self.is_valid_grade(grade_match.group(1)):
            return grade_match.group(1).upper()
        
        # Strategy 3: Look for grade in any position
        for word in words:
            if self.is_valid_grade(word):
                return word.upper()
                
        return None

    def extract_credit_data(self, line):
        """Extract credit and earned credit using robust approach"""
        # Extract ALL numbers from the line
        all_numbers = re.findall(r'\b\d+\.?\d*\b', line)
        numbers = []
        
        for num in all_numbers:
            try:
                val = float(num)
                # Filter for credit-like values (0-5)
                if 0 <= val <= 5:
                    numbers.append(val)
            except ValueError:
                continue
        
        # Strategy 1: Look for consecutive credit-earned pairs
        for i in range(len(numbers) - 1):
            credit = numbers[i]
            earned = numbers[i + 1]
            # Basic validation: earned should be <= credit
            if earned <= credit:
                return credit, earned
        
        # Strategy 2: If only one number, assume earned equals credit
        if len(numbers) == 1:
            return numbers[0], numbers[0]
        
        # Strategy 3: Try last two numbers
        if len(numbers) >= 2:
            return numbers[-2], numbers[-1]
        
        return None

    def is_valid_course_data(self, code, credit, earned, grade):
        """Validate course data"""
        if not self.is_valid_course_code(code):
            return False
        if not (0 <= credit <= 5):
            return False
        if not (0 <= earned <= credit):
            return False
        if not self.is_valid_grade(grade):
            return False
        return True

    # Compatibility methods
    def extract_course_bulletproof(self, original_line, clean_line):
        return self.extract_course_smart(clean_line)

    def extract_grade_bulletproof(self, clean_line, course_code):
        return self.find_grade_in_line(clean_line)

    def is_grade_position_valid(self, parts, grade_position):
        return True