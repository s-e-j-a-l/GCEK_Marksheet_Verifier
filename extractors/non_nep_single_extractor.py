from .base_extractor import BaseExtractor
import re

class MarksheetVerifier:
    def __init__(self):
        self.grade_points = {
            'A+': 10, 'A': 9, 'B+': 8, 'B': 7, 'C+': 6,
            'C': 5, 'D': 4, 'F': 0, 'FF': 0
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

class NonNEPSingleExtractor(BaseExtractor):
    def __init__(self):
        super().__init__()
        self.student_type = "Non-NEP Student (Single Semester)"
    
    def extract_all_courses_robust(self, text):
        """Robust course extraction for single semester Non-NEP"""
        courses = []
        lines = text.split('\n')
        
        in_course_section = False
        course_data_lines = []
        
        for i, line in enumerate(lines):
            line_clean = self.clean_text(line)
            
            # Start of course section
            if not in_course_section and any(marker in line_clean for marker in 
                ['Course Code', 'Sr.No.', 'Course Credits']):
                in_course_section = True
                continue
                
            # End of course section
            if in_course_section and any(marker in line_clean for marker in 
                ['Remarks', 'Current Semester Performance', 'Cumulative Performance', 'Grade Card No']):
                in_course_section = False
                break
                
            # Collect potential course lines
            if in_course_section:
                if not any(header in line_clean for header in ['Course Code', 'Sr.No.']):
                    course_data_lines.append((i, line_clean))
        
        # Extract courses from collected lines
        for line_num, line in course_data_lines:
            course = self.extract_course_smart(line)
            if course:
                courses.append(course)
        
        return courses

    def extract_performance_data(self, text):
        """Extract reported performance values from the marksheet"""
        lines = text.split('\n')
        
        credits = egp = sgpa = 0
        
        # Look for performance section
        for i, line in enumerate(lines):
            line_clean = line.strip()
            
            # Find performance section
            if 'Current Semester Performance' in line_clean:
                # Look for data in the next few lines
                for j in range(i+1, min(i+10, len(lines))):
                    data_line = lines[j].strip()
                    if not data_line:
                        continue
                    
                    # Extract numbers from the data line
                    numbers = re.findall(r'\d+\.?\d*', data_line)
                    if len(numbers) >= 3:
                        try:
                            # Format: Credits, EGP, SGPA
                            credits, egp, sgpa = float(numbers[0]), float(numbers[1]), float(numbers[2])
                            break
                        except (ValueError, IndexError):
                            continue
                break
        
        return credits, egp, sgpa

    def process_pdf(self, pdf_path):
        """Main processing function for single semester Non-NEP with verification"""
        text = self.extract_text_from_pdf(pdf_path)
        if not text.strip():
            return {'all_courses': [], 'student_type': self.student_type}
        
        # Extract courses
        courses = self.extract_all_courses_robust(text)
        
        # Extract reported performance data
        rep_credits, rep_egp, rep_sgpa = self.extract_performance_data(text)
        
        # Calculate values using our logic
        verifier = MarksheetVerifier()
        calc_egp = verifier.calculate_egp(courses)
        calc_credits = verifier.calculate_total_credits(courses)
        calc_sgpa = verifier.calculate_sgpa(courses)
        
        # Create verification results
        verification_results = {
            'egp': {
                'calculated': calc_egp,
                'reported': rep_egp,
                'match': abs(calc_egp - rep_egp) < 0.1
            },
            'credits': {
                'calculated': calc_credits,
                'reported': rep_credits,
                'match': abs(calc_credits - rep_credits) < 0.1
            },
            'sgpa': {
                'calculated': calc_sgpa,
                'reported': rep_sgpa,
                'match': abs(calc_sgpa - rep_sgpa) < 0.1
            }
        }
        
        # Check overall status
        all_match = (
            verification_results['egp']['match'] and 
            verification_results['credits']['match'] and 
            verification_results['sgpa']['match']
        )
        
        overall_status = "✅ All Values Verified" if all_match else "Verification Failed"
        
        return {
            'all_courses': courses,
            'performance_data': {
                'credits': rep_credits,
                'egp': rep_egp,
                'sgpa': rep_sgpa
            },
            'calculated_data': {
                'egp': calc_egp,
                'credits': calc_credits,
                'sgpa': calc_sgpa
            },
            'verification': verification_results,
            'status': overall_status,
            'student_type': self.student_type
        }