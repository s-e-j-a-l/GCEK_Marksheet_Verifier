from flask import Flask, render_template, request, redirect, url_for, flash, send_file, send_from_directory
import os
import zipfile
import tempfile
import PyPDF2
from werkzeug.utils import secure_filename
from extractor_factory import ExtractorFactory
import re 
import math

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['pdf', 'zip']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/uploads/<filename>')
def serve_uploaded_file(filename):
    """Serve uploaded files directly"""
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except FileNotFoundError:
        flash('File not found', 'error')
        return redirect(url_for('index'))

@app.route('/pdf/<filename>')
def serve_pdf(filename):
    """Serve the uploaded PDF file with proper headers"""
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
        if os.path.exists(file_path):
            # Set proper headers for PDF display
            response = send_file(
                file_path, 
                as_attachment=False,
                mimetype='application/pdf'
            )
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
            return response
        else:
            flash('File not found', 'error')
            return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error serving PDF: {str(e)}', 'error')
        return redirect(url_for('index'))

def save_uploaded_file(file):
    """Save uploaded file and return the file path and secure filename"""
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)
    return file_path, filename

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
            # First, detect if it's a double semester marksheet
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                first_page_text = pdf_reader.pages[0].extract_text()
            
            # Check for double semester pattern
            if 'Previous Semester Performance' in first_page_text and 'Current Semester Performance' in first_page_text:
                from non_nep_double_extractor import NonNEPDoubleExtractor
                extractor = NonNEPDoubleExtractor()
                result = extractor.process_pdf(file_path)
                
                # Add PDF URL for viewing - use direct file serving
                result['pdf_url'] = url_for('serve_pdf', filename=filename)
                
                return render_template('double_semester_results.html', 
                                     result=result,
                                     filename=filename)
            else:
                # Use factory for single semester marksheets
                extractor = ExtractorFactory.get_extractor("")
                text = extractor.extract_text_from_pdf(file_path)
                extractor = ExtractorFactory.get_extractor(text)
                
                result = extractor.process_pdf(file_path)
                
                # Handle single semester formats
                if isinstance(result, dict) and 'verification' in result:
                    # New format with verification data
                    courses = result.get('all_courses', [])
                    student_type = result.get('student_type', 'Unknown')
                    verification = result.get('verification', {})
                    status = result.get('status', 'Unknown')
                    
                    # Add PDF URL for viewing - use direct file serving
                    pdf_url = url_for('serve_pdf', filename=filename)
                    
                    return render_template('results.html', 
                                         courses=courses, 
                                         verification=verification,
                                         status=status,
                                         filename=filename,
                                         student_type=student_type,
                                         total_courses=len(courses),
                                         pdf_url=pdf_url)
                else:
                    # Old format (backward compatibility)
                    courses = result if isinstance(result, list) else []
                    student_type = extractor.student_type
                    
                    if not courses:
                        flash('No courses data extracted from the PDF.', 'error')
                        return redirect(url_for('index'))

                    # Calculate verification for old format
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

                    # Add PDF URL for viewing - use direct file serving
                    pdf_url = url_for('serve_pdf', filename=filename)

                    return render_template('results.html', 
                                         courses=courses, 
                                         verification=verification,
                                         status=status,
                                         filename=filename,
                                         student_type=student_type,
                                         total_courses=len(courses),
                                         pdf_url=pdf_url)

        except Exception as e:
            flash(f'Error processing file: {str(e)}', 'error')
            return redirect(url_for('index'))

    flash('Invalid file type.', 'error')
    return redirect(url_for('index'))

def is_values_match(calculated, reported, value_type='general'):
    """Check if calculated and reported values match within tolerance"""
    if calculated == 0 and reported == 0:
        return False  # Both zero means no data
    
    # Handle floating point precision issues
    difference = abs(calculated - reported)
    
    # Set tolerance based on value type
    if value_type == 'sgpa':
        tolerance = 0.01  # Tighter tolerance for SGPA
    else:
        tolerance = 0.1   # Regular tolerance for credits and EGP
    
    return difference < tolerance

def process_bulk_upload(uploaded_files):
    """Process multiple PDF files for bulk verification"""
    results = []
    
    for uploaded_file in uploaded_files:
        try:
            filename = uploaded_file.filename
            
            # Save the file permanently first
            permanent_path, saved_filename = save_uploaded_file(uploaded_file)
            pdf_url = url_for('serve_pdf', filename=saved_filename)
            
            # Determine student type and use appropriate extractor
            result_data = None
            
            # Read first few lines to determine type
            try:
                with open(permanent_path, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    first_page_text = pdf_reader.pages[0].extract_text()
                    
                if 'Previous Semester Performance' in first_page_text and 'Current Semester Performance' in first_page_text:
                    # Non-NEP Double Semester
                    try:
                        from non_nep_double_extractor import NonNEPDoubleExtractor
                        extractor = NonNEPDoubleExtractor()
                        result_data = extractor.get_bulk_data(permanent_path)
                    except ImportError as e:
                        result_data = {
                            'reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                            'calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                            'previous_reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                            'previous_calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                            'status': f"❌ Import Error: {str(e)}",
                            'student_type': 'Non-NEP Student (Double Semester)',
                            'error': str(e)
                        }
                    except Exception as e:
                        result_data = {
                            'reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                            'calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                            'previous_reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                            'previous_calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                            'status': f"❌ Processing Error",
                            'student_type': 'Non-NEP Student (Double Semester)',
                            'error': str(e)
                        }
                else:
                    # For other types, use the factory
                    try:
                        extractor = ExtractorFactory.get_extractor("")
                        text = extractor.extract_text_from_pdf(permanent_path)
                        extractor = ExtractorFactory.get_extractor(text)
                        
                        # Process and create result data for bulk display
                        full_result = extractor.process_pdf(permanent_path)
                        
                        if isinstance(full_result, dict) and 'verification' in full_result:
                            # New format with verification
                            verification = full_result.get('verification', {})
                            result_data = {
                                'reported': {
                                    'egp': verification.get('egp', {}).get('reported', 0),
                                    'credits': verification.get('credits', {}).get('reported', 0),
                                    'sgpa': verification.get('sgpa', {}).get('reported', 0)
                                },
                                'calculated': {
                                    'egp': verification.get('egp', {}).get('calculated', 0),
                                    'credits': verification.get('credits', {}).get('calculated', 0),
                                    'sgpa': verification.get('sgpa', {}).get('calculated', 0)
                                },
                                'previous_reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                                'previous_calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                                'status': "✅ Correct" if full_result.get('status', '').startswith('✅') else "❌ Wrong",
                                'student_type': full_result.get('student_type', extractor.student_type)
                            }
                        else:
                            # Old format - calculate manually
                            courses = full_result if isinstance(full_result, list) else []
                            verifier = MarksheetVerifier()
                            calc_egp = verifier.calculate_egp(courses)
                            calc_cred = verifier.calculate_total_credits(courses)
                            calc_sgpa = verifier.calculate_sgpa(courses)
                            
                            result_data = {
                                'reported': {'egp': calc_egp, 'credits': calc_cred, 'sgpa': calc_sgpa},
                                'calculated': {'egp': calc_egp, 'credits': calc_cred, 'sgpa': calc_sgpa},
                                'previous_reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                                'previous_calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                                'status': "✅ Correct",
                                'student_type': extractor.student_type
                            }
                    except Exception as e:
                        result_data = {
                            'reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                            'calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                            'previous_reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                            'previous_calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                            'status': f"❌ Processing Error",
                            'student_type': 'Unknown',
                            'error': str(e)
                        }
            except Exception as e:
                result_data = {
                    'reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'previous_reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'previous_calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'status': f"❌ PDF Read Error",
                    'student_type': 'Unknown',
                    'error': str(e)
                }
            
            # Calculate match status for both semesters with better debugging
            if result_data: 
                # Previous semester match
                prev_credits_match = is_values_match(result_data['previous_calculated']['credits'], result_data['previous_reported']['credits'], 'credits')
                prev_egp_match = is_values_match(result_data['previous_calculated']['egp'], result_data['previous_reported']['egp'], 'egp')
                prev_sgpa_match = is_values_match(result_data['previous_calculated']['sgpa'], result_data['previous_reported']['sgpa'], 'sgpa')

                prev_match = prev_credits_match and prev_egp_match and prev_sgpa_match
                
                # Current semester match
                curr_credits_match = is_values_match(result_data['calculated']['credits'], result_data['reported']['credits'], 'credits')
                curr_egp_match = is_values_match(result_data['calculated']['egp'], result_data['reported']['egp'], 'egp')
                curr_sgpa_match = is_values_match(result_data['calculated']['sgpa'], result_data['reported']['sgpa'], 'sgpa')

                curr_match = curr_credits_match and curr_egp_match and curr_sgpa_match
                                
                # Determine overall status
                if result_data.get('status') in ['✅ Correct', '❌ Wrong']:
                    # Use the status from the extractor if available
                    status = result_data['status']
                else:
                    # Determine status based on matches
                    status = "✅ Correct" if (prev_match and curr_match) else "❌ Wrong"
                
                result_entry = {
                    'filename': filename,
                    'student_type': result_data.get('student_type', 'Unknown'),
                    'calculated': result_data.get('calculated', {'egp': 0, 'credits': 0, 'sgpa': 0}),
                    'reported': result_data.get('reported', {'egp': 0, 'credits': 0, 'sgpa': 0}),
                    'previous_calculated': result_data.get('previous_calculated', {'egp': 0, 'credits': 0, 'sgpa': 0}),
                    'previous_reported': result_data.get('previous_reported', {'egp': 0, 'credits': 0, 'sgpa': 0}),
                    'previous_match': prev_match,
                    'current_match': curr_match,
                    'status': status,
                    'error': result_data.get('error'),
                    'pdf_url': pdf_url  # Always include PDF URL
                }
                results.append(result_entry)
            else:
                results.append({
                    'filename': filename,
                    'student_type': 'Unknown',
                    'calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'previous_calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'previous_reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                    'previous_match': False,
                    'current_match': False,
                    'status': '❌ No result data',
                    'error': 'No data returned from processor',
                    'pdf_url': pdf_url  # Always include PDF URL even if processing failed
                })
            
        except Exception as e:
                
            results.append({
                'filename': uploaded_file.filename,
                'student_type': 'Unknown',
                'calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                'reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                'previous_calculated': {'egp': 0, 'credits': 0, 'sgpa': 0},
                'previous_reported': {'egp': 0, 'credits': 0, 'sgpa': 0},
                'previous_match': False,
                'current_match': False,
                'status': f'❌ Error',
                'error': str(e),
                'pdf_url': ''  # No PDF URL available due to error
            })
    
    return results

@app.route('/upload_bulk', methods=['POST'])
def upload_bulk():
    if 'bulk_files' not in request.files:
        flash('No files selected', 'error')
        return redirect(url_for('index'))

    files = request.files.getlist('bulk_files')
    if not files or all(file.filename == '' for file in files):
        flash('No files selected', 'error')
        return redirect(url_for('index'))

    
    # Use the new process_bulk_upload function
    results = process_bulk_upload(files)
        
    return render_template('bulk_results.html', results=results)

    
