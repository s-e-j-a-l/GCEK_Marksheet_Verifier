import re
import os
import sys

# Add the current directory to path to ensure imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from base_extractor import BaseExtractor

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

class NonNEPDoubleExtractor(BaseExtractor):
    def __init__(self):
        super().__init__()
        self.student_type = "Non-NEP Student (Double Semester)"
    
    def extract_all_courses_robust(self, text):
        """STRONG course extraction without duplicates"""
        courses = []
        lines = text.split('\n')
        
        current_semester = None
        in_course_section = False
        course_section_started = False
        seen_course_codes = set()
        
        for i, line in enumerate(lines):
            line_clean = self.clean_text(line)
            original_line = line.strip()
            
            if not line_clean:
                continue
            
            # Detect semester headers
            semester_match = re.search(r'Semester\s*:\s*([IVXivx]+)', line_clean, re.IGNORECASE)
            if semester_match:
                current_semester = semester_match.group(1).upper()
                course_section_started = True
                in_course_section = False
                continue
            
            # Look for course section start
            if course_section_started and not in_course_section:
                if re.search(r'[A-Z]{2,4}\d{3,4}[A-Z]?\*?', line_clean):
                    in_course_section = True
            
            # End of course section
            if in_course_section and any(marker in line_clean for marker in 
                ['Previous Semester Performance', 'Remarks', 'Grade Card No', 'Cummulative Performance', 'Semester :']):
                in_course_section = False
                course_section_started = False
                current_semester = None
            
            # Extract course data
            if in_course_section and current_semester:
                course = self.extract_course_bulletproof(original_line, line_clean)
                if course:
                    course_key = f"{course['course_code']}_{current_semester}"
                    if course_key not in seen_course_codes:
                        seen_course_codes.add(course_key)
                        course['semester'] = current_semester
                        courses.append(course)
        
        return courses

    def extract_course_bulletproof(self, original_line, clean_line):
        """BULLETPROOF course extraction with guaranteed correct grade detection"""
        
        # Extract course code
        code_match = re.search(r'([A-Z]{2,4}\d{3,4}[A-Z]?\*?)', clean_line)
        if not code_match:
            return None
            
        course_code = code_match.group(1).upper()
        
        # Extract ALL numbers for credits
        all_numbers = re.findall(r'\d+\.?\d*', clean_line)
        numbers = []
        
        for num in all_numbers:
            try:
                val = float(num)
                if 1 <= val <= 5:
                    numbers.append(val)
            except ValueError:
                continue
        
        # BULLETPROOF Grade Extraction
        grade = self.extract_grade_bulletproof(clean_line, course_code)
        
        if not grade:
            return None
        
        # Determine credits and earned credits
        credit = earned = 0
        
        if len(numbers) >= 2:
            credit, earned = numbers[0], numbers[1]
        elif len(numbers) == 1:
            credit = earned = numbers[0]
        else:
            return None
        
        # Final validation
        if not (self.is_valid_course_code(course_code) and 
                self.is_valid_grade(grade) and 
                1 <= credit <= 5 and 
                0 <= earned <= credit):
            return None
        
        return {
            'course_code': course_code,
            'credit': credit,
            'earned': earned,
            'grade': grade
        }

    def extract_grade_bulletproof(self, clean_line, course_code):
        """BULLETPROOF grade extraction"""
        
        # Remove the course code from the line to avoid confusion
        line_without_code = clean_line.replace(course_code, '').strip()
        
        # Split into components
        parts = line_without_code.split()
        
        # Strategy 1: Look for valid grades in the last few positions
        for i in range(min(3, len(parts))):
            position = -1 - i
            potential_grade = parts[position].upper() if abs(position) <= len(parts) else None
            
            if potential_grade and self.is_valid_grade(potential_grade):
                if self.is_grade_position_valid(parts, position):
                    return potential_grade
        
        # Strategy 2: Look for isolated grades that follow number patterns
        for i, part in enumerate(parts):
            if part.isdigit() and 1 <= int(part) <= 5:
                if i + 1 < len(parts):
                    next_part = parts[i + 1].upper()
                    if self.is_valid_grade(next_part):
                        return next_part
                if i + 2 < len(parts):
                    next_next_part = parts[i + 2].upper()
                    if self.is_valid_grade(next_next_part):
                        return next_next_part
        
        # Strategy 3: Look for common pattern
        number_count = sum(1 for part in parts if part.isdigit() and 1 <= int(part) <= 5)
        
        if number_count >= 2:
            last_part = parts[-1].upper()
            if self.is_valid_grade(last_part):
                return last_part
        
        return None

    def is_grade_position_valid(self, parts, grade_position):
        """Validate that the grade is in a logical position"""
        grade_index = grade_position if grade_position >= 0 else len(parts) + grade_position
        
        if grade_index < len(parts) - 3:
            return False
            
        has_numbers_before = False
        for i in range(max(0, grade_index - 3), grade_index):
            if i < len(parts) and parts[i].isdigit() and 1 <= int(parts[i]) <= 5:
                has_numbers_before = True
                break
                
        return has_numbers_before

    def extract_performance_data(self, text):
        """IMPROVED: Extract both previous and current semester performance"""
        lines = text.split('\n')
        
        prev_credits = prev_egp = prev_sgpa = 0
        curr_credits = curr_egp = curr_sgpa = 0
        
        in_performance_section = False
        performance_lines = []
        
        # Find the performance section
        for i, line in enumerate(lines):
            line_clean = line.strip()
            
            if 'Previous Semester Performance' in line_clean or 'Current Semester Performance' in line_clean:
                in_performance_section = True
                performance_lines.append(line_clean)
                continue
                
            if in_performance_section:
                performance_lines.append(line_clean)
                # Stop collecting if we reach certain markers
                if any(marker in line_clean for marker in ['Remarks', 'Grade Card No', 'Cummulative Performance']):
                    break
        
        # Join performance lines and extract numbers
        performance_text = ' '.join(performance_lines)
        
        # Improved number extraction with better patterns
        numbers = re.findall(r'\d+\.?\d*', performance_text)
        
        if len(numbers) >= 6:
            try:
                prev_credits, prev_egp, prev_sgpa = float(numbers[0]), float(numbers[1]), float(numbers[2])
                curr_credits, curr_egp, curr_sgpa = float(numbers[3]), float(numbers[4]), float(numbers[5])
            except (ValueError, IndexError):
                # Try alternative pattern matching
                self.extract_performance_alternative(lines, prev_credits, prev_egp, prev_sgpa, curr_credits, curr_egp, curr_sgpa)
        
        return {
            'previous': {'credits': prev_credits, 'egp': prev_egp, 'sgpa': prev_sgpa},
            'current': {'credits': curr_credits, 'egp': curr_egp, 'sgpa': curr_sgpa}
        }

    def extract_performance_alternative(self, lines, prev_credits, prev_egp, prev_sgpa, curr_credits, curr_egp, curr_sgpa):
        """Alternative method to extract performance data"""
        for i, line in enumerate(lines):
            line_clean = line.strip()
            
            # Look for specific patterns in performance data
            if 'Credits' in line_clean and 'EGP' in line_clean and 'SGPA' in line_clean:
                # This line contains headers, next line should contain numbers
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    numbers = re.findall(r'\d+\.?\d*', next_line)
                    if len(numbers) >= 6:
                        try:
                            prev_credits, prev_egp, prev_sgpa = float(numbers[0]), float(numbers[1]), float(numbers[2])
                            curr_credits, curr_egp, curr_sgpa = float(numbers[3]), float(numbers[4]), float(numbers[5])
                        except (ValueError, IndexError):
                            pass
    
    def process_pdf(self, pdf_path):
        """Main processing for double-semester format"""
        try:
            text = self.extract_text_from_pdf(pdf_path)
            if not text.strip():
                return {'all_courses': [], 'student_type': self.student_type, 'error': 'No text extracted'}
            
            # Extract courses
            courses = self.extract_all_courses_robust(text)
            
            # Extract performance data
            performance_data = self.extract_performance_data(text)
            
            # Separate courses by semester type
            odd_semester_courses = [c for c in courses if c.get('semester') in ['I', 'III', 'V', 'VII']]
            even_semester_courses = [c for c in courses if c.get('semester') in ['II', 'IV', 'VI', 'VIII']]
            
            # Calculate values for verification
            verifier = MarksheetVerifier()
            
            # Calculate for odd semester (Previous)
            calc_odd_egp = verifier.calculate_egp(odd_semester_courses)
            calc_odd_credits = verifier.calculate_total_credits(odd_semester_courses)
            calc_odd_sgpa = verifier.calculate_sgpa(odd_semester_courses)
            
            # Calculate for even semester (Current)  
            calc_even_egp = verifier.calculate_egp(even_semester_courses)
            calc_even_credits = verifier.calculate_total_credits(even_semester_courses)
            calc_even_sgpa = verifier.calculate_sgpa(even_semester_courses)
            
            # Create verification results
            verification_results = {
                'previous': {
                    'credits': {
                        'calculated': calc_odd_credits,
                        'reported': performance_data['previous']['credits'],
                        'match': abs(calc_odd_credits - performance_data['previous']['credits']) < 0.1
                    },
                    'egp': {
                        'calculated': calc_odd_egp,
                        'reported': performance_data['previous']['egp'],
                        'match': abs(calc_odd_egp - performance_data['previous']['egp']) < 0.1
                    },
                    'sgpa': {
                        'calculated': calc_odd_sgpa,
                        'reported': performance_data['previous']['sgpa'],
                        'match': abs(calc_odd_sgpa - performance_data['previous']['sgpa']) < 0.1
                    }
                },
                'current': {
                    'credits': {
                        'calculated': calc_even_credits,
                        'reported': performance_data['current']['credits'],
                        'match': abs(calc_even_credits - performance_data['current']['credits']) < 0.1
                    },
                    'egp': {
                        'calculated': calc_even_egp,
                        'reported': performance_data['current']['egp'],
                        'match': abs(calc_even_egp - performance_data['current']['egp']) < 0.1
                    },
                    'sgpa': {
                        'calculated': calc_even_sgpa,
                        'reported': performance_data['current']['sgpa'],
                        'match': abs(calc_even_sgpa - performance_data['current']['sgpa']) < 0.1
                    }
                }
            }
            
            # Check overall status
            all_previous_match = (
                verification_results['previous']['credits']['match'] and
                verification_results['previous']['egp']['match'] and
                verification_results['previous']['sgpa']['match']
            )
            
            all_current_match = (
                verification_results['current']['credits']['match'] and
                verification_results['current']['egp']['match'] and
                verification_results['current']['sgpa']['match']
            )
            
            overall_status = "✅ All Values Match" if (all_previous_match and all_current_match) else "❌ Verification Failed"
            
            return {
                'all_courses': courses,
                'odd_semester_courses': odd_semester_courses,
                'even_semester_courses': even_semester_courses,
                'performance_data': performance_data,
                'calculated_data': {
                    'previous': {
                        'egp': calc_odd_egp,
                        'credits': calc_odd_credits, 
                        'sgpa': calc_odd_sgpa
                    },
                    'current': {
                        'egp': calc_even_egp,
                        'credits': calc_even_credits,
                        'sgpa': calc_even_sgpa
                    }
                },
                'verification': verification_results,
                'status': overall_status,
                'student_type': self.student_type
            }
        except Exception as e:
            return {
                'all_courses': [],
                'student_type': self.student_type,
                'error': str(e)
            }

    def get_bulk_data(self, pdf_path):
        """CORRECTED: Fixed method for bulk processing with all required fields"""
        try:
            result = self.process_pdf(pdf_path)
            
            # Check if processing was successful and data exists
            if 'error' in result:
                return {
                    'reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'previous_reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'previous_calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'status': f"❌ {result['error']}",
                    'student_type': self.student_type,
                    'error': result['error']
                }
            
            # Safely extract the main values needed for bulk display
            if ('performance_data' in result and 'calculated_data' in result and 
                'current' in result['performance_data'] and 'current' in result['calculated_data'] and
                'previous' in result['performance_data'] and 'previous' in result['calculated_data']):
                
                curr_reported = result['performance_data']['current']
                curr_calculated = result['calculated_data']['current']
                prev_reported = result['performance_data']['previous']
                prev_calculated = result['calculated_data']['previous']
                
                return {
                    'reported': {
                        'egp': curr_reported.get('egp', 0),
                        'credits': curr_reported.get('credits', 0),
                        'sgpa': curr_reported.get('sgpa', 0)
                    },
                    'calculated': {
                        'egp': curr_calculated.get('egp', 0),
                        'credits': curr_calculated.get('credits', 0),
                        'sgpa': curr_calculated.get('sgpa', 0)
                    },
                    'previous_reported': {
                        'egp': prev_reported.get('egp', 0),
                        'credits': prev_reported.get('credits', 0),
                        'sgpa': prev_reported.get('sgpa', 0)
                    },
                    'previous_calculated': {
                        'egp': prev_calculated.get('egp', 0),
                        'credits': prev_calculated.get('credits', 0),
                        'sgpa': prev_calculated.get('sgpa', 0)
                    },
                    'status': "✅ Correct" if result.get('status') == "✅ All Values Match" else "❌ Wrong",
                    'student_type': self.student_type
                }
            else:
                return {
                    'reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'previous_reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'previous_calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'status': "❌ Data Extraction Failed",
                    'student_type': self.student_type
                }
                
        except Exception as e:
            return {
                'reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                'calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                'previous_reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                'previous_calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                'status': f"❌ Error: {str(e)}",
                'student_type': self.student_type,
                'error': str(e)
            }