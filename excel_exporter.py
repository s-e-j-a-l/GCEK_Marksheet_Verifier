import os
import pandas as pd
from datetime import datetime
import re

class SingleMarksheetExporter:
    def __init__(self):
        pass
    
    def export_to_excel(self, result, filename, output_path=None):
        """
        Export a single marksheet result to Excel
        
        Args:
            result: The result dictionary from the extractor
            filename: Original PDF filename
            output_path: Optional output path
        """
        # Create exports directory if it doesn't exist
        export_dir = 'exports'
        os.makedirs(export_dir, exist_ok=True)
        
        # Generate filename
        if not output_path:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            base_name = os.path.splitext(filename)[0]
            # Clean filename to remove special characters
            base_name = re.sub(r'[^\w\-_]', '', base_name)
            output_path = os.path.join(export_dir, f'{base_name}_data_{timestamp}.xlsx')
        
        # Extract student info
        student_info = result.get('student_info', {})
        
        # Prepare summary data - using simple column names
        summary_data = []
        summary_data.append(['Field', 'Value'])
        summary_data.append(['Filename', filename])
        summary_data.append(['Student Name', student_info.get('name', '')])
        summary_data.append(['Mother\'s Name', student_info.get('mother_name', '')])
        summary_data.append(['Registration No', student_info.get('registration_no', '')])
        summary_data.append(['Program', student_info.get('program', '')])
        summary_data.append(['Department', student_info.get('department', '')])
        summary_data.append(['Semester', student_info.get('semester', '')])
        summary_data.append(['Examination', student_info.get('examination', '')])
        summary_data.append(['Student Type', result.get('student_type', '')])
        summary_data.append(['Verification Status', result.get('status', '')])
        summary_data.append(['Reported Credits', result.get('performance_data', {}).get('credits', 0)])
        summary_data.append(['Reported EGP', result.get('performance_data', {}).get('egp', 0)])
        summary_data.append(['Reported SGPA', result.get('performance_data', {}).get('sgpa', 0)])
        summary_data.append(['Calculated Credits', result.get('calculated_data', {}).get('credits', 0)])
        summary_data.append(['Calculated EGP', result.get('calculated_data', {}).get('egp', 0)])
        summary_data.append(['Calculated SGPA', result.get('calculated_data', {}).get('sgpa', 0)])
        summary_data.append(['Credits Match', 'Yes' if result.get('verification', {}).get('credits', {}).get('match', False) else 'No'])
        summary_data.append(['EGP Match', 'Yes' if result.get('verification', {}).get('egp', {}).get('match', False) else 'No'])
        summary_data.append(['SGPA Match', 'Yes' if result.get('verification', {}).get('sgpa', {}).get('match', False) else 'No'])
        summary_data.append(['Total Courses', len(result.get('all_courses', []))])
        summary_data.append(['Extraction Date', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        
        # Prepare courses data with simple column names
        courses_data = []
        courses_data.append(['Course Code', 'Credit', 'Earned', 'Grade'])
        for course in result.get('all_courses', []):
            courses_data.append([
                course.get('course_code', ''),
                course.get('credit', 0),
                course.get('earned', 0),
                course.get('grade', '')
            ])
        
        # Prepare grade distribution data
        grade_counts = {}
        for course in result.get('all_courses', []):
            grade = course.get('grade', '')
            if grade:
                grade_counts[grade] = grade_counts.get(grade, 0) + 1
        
        grade_data = []
        grade_data.append(['Grade', 'Count'])
        for grade, count in grade_counts.items():
            grade_data.append([grade, count])
        
        # Create Excel file using xlsxwriter engine (more compatible)
        try:
            with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                # Sheet 1: Summary
                df_summary = pd.DataFrame(summary_data[1:], columns=summary_data[0])
                df_summary.to_excel(writer, sheet_name='Summary', index=False, header=False)
                
                # Auto-adjust column widths for Summary
                worksheet = writer.sheets['Summary']
                worksheet.set_column('A:A', 25)
                worksheet.set_column('B:B', 40)
                
                # Sheet 2: Courses
                if len(courses_data) > 1:
                    df_courses = pd.DataFrame(courses_data[1:], columns=courses_data[0])
                    df_courses.to_excel(writer, sheet_name='Courses', index=False)
                    
                    worksheet = writer.sheets['Courses']
                    worksheet.set_column('A:A', 20)  # Course Code
                    worksheet.set_column('B:B', 10)  # Credit
                    worksheet.set_column('C:C', 10)  # Earned
                    worksheet.set_column('D:D', 10)  # Grade
                
                # Sheet 3: Grade Distribution
                if len(grade_data) > 1:
                    df_grade = pd.DataFrame(grade_data[1:], columns=grade_data[0])
                    df_grade.to_excel(writer, sheet_name='Grade_Distribution', index=False)
                    
                    worksheet = writer.sheets['Grade_Distribution']
                    worksheet.set_column('A:A', 15)
                    worksheet.set_column('B:B', 10)
            
            print(f"✅ Excel file created successfully: {output_path}")
            return output_path
            
        except ImportError:
            # Fallback to openpyxl if xlsxwriter is not available
            print("xlsxwriter not found, using openpyxl as fallback")
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                # Sheet 1: Summary
                df_summary = pd.DataFrame(summary_data[1:], columns=summary_data[0])
                df_summary.to_excel(writer, sheet_name='Summary', index=False, header=False)
                
                # Sheet 2: Courses
                if len(courses_data) > 1:
                    df_courses = pd.DataFrame(courses_data[1:], columns=courses_data[0])
                    df_courses.to_excel(writer, sheet_name='Courses', index=False)
                
                # Sheet 3: Grade Distribution
                if len(grade_data) > 1:
                    df_grade = pd.DataFrame(grade_data[1:], columns=grade_data[0])
                    df_grade.to_excel(writer, sheet_name='Grade_Distribution', index=False)
            
            return output_path


# Simple function for easy import
def export_single_marksheet(result, filename, output_path=None):
    """Easy-to-use function to export a single marksheet"""
    exporter = SingleMarksheetExporter()
    return exporter.export_to_excel(result, filename, output_path)


# Test function
if __name__ == "__main__":
    # Test the exporter with sample data
    test_result = {
        'student_info': {
            'name': 'Test Student',
            'registration_no': '12345',
            'program': 'B.Tech',
            'department': 'Computer Science',
            'semester': 'III'
        },
        'student_type': 'NEP Student',
        'status': '✅ All Values Match',
        'performance_data': {'credits': 20, 'egp': 180, 'sgpa': 9.0},
        'calculated_data': {'credits': 20, 'egp': 180, 'sgpa': 9.0},
        'verification': {
            'credits': {'match': True},
            'egp': {'match': True},
            'sgpa': {'match': True}
        },
        'all_courses': [
            {'course_code': 'CS101', 'credit': 3, 'earned': 3, 'grade': 'A'},
            {'course_code': 'CS102', 'credit': 4, 'earned': 4, 'grade': 'B+'}
        ]
    }
    
    export_single_marksheet(test_result, 'test.pdf')