import os
import pandas as pd
from datetime import datetime
import re
import numpy as np

# dataset file path
DATASET_FILE = 'marksheet_dataset.xlsx'

# Define column names and their expected dtypes
COLUMN_DTYPES = {
    'filename': 'str',
    'student_name': 'str',
    'mother_name': 'str',
    'registration_no': 'str',  # Store as string to preserve leading zeros
    'program': 'str',
    'department': 'str',
    'semester': 'str',
    'examination': 'str',
    'student_type': 'str',
    'verification_status': 'str',
    'reported_credits': 'float64',
    'reported_egp': 'float64',
    'reported_sgpa': 'float64',
    'calculated_credits': 'float64',
    'calculated_egp': 'float64',
    'calculated_sgpa': 'float64',
    'credits_match': 'str',
    'egp_match': 'str',
    'sgpa_match': 'str',
    'total_courses': 'int64',
    'grade_A+_count': 'int64',
    'grade_A_count': 'int64',
    'grade_B+_count': 'int64',
    'grade_B_count': 'int64',
    'grade_C+_count': 'int64',
    'grade_C_count': 'int64',
    'grade_D_count': 'int64',
    'grade_F_count': 'int64',
    'extraction_date': 'str'
}

def get_dataset_path():
    """Get the path to the dataset file"""
    return DATASET_FILE

def calculate_grade_distribution(courses):
    """Calculate grade distribution from courses"""
    grade_counts = {
        'A+': 0, 'A': 0, 'B+': 0, 'B': 0, 
        'C+': 0, 'C': 0, 'D': 0, 'F': 0
    }
    
    for course in courses:
        grade = course.get('grade', '').upper()
        if grade in grade_counts:
            grade_counts[grade] += 1
        elif grade in ['FF', 'F']:
            grade_counts['F'] += 1
    
    return grade_counts

def extract_row_data(result, filename):
    """Extract a single row of data from the result"""
    
    student_info = result.get('student_info', {})
    courses = result.get('all_courses', [])
    grade_counts = calculate_grade_distribution(courses)
    
    # Handle different result formats
    if 'verification' in result:
        # Single semester format
        verification = result.get('verification', {})
        credits_match = verification.get('credits', {}).get('match', False)
        egp_match = verification.get('egp', {}).get('match', False)
        sgpa_match = verification.get('sgpa', {}).get('match', False)
        
        reported_credits = result.get('performance_data', {}).get('credits', 0)
        reported_egp = result.get('performance_data', {}).get('egp', 0)
        reported_sgpa = result.get('performance_data', {}).get('sgpa', 0)
        calculated_credits = result.get('calculated_data', {}).get('credits', 0)
        calculated_egp = result.get('calculated_data', {}).get('egp', 0)
        calculated_sgpa = result.get('calculated_data', {}).get('sgpa', 0)
        
    elif 'previous' in result.get('performance_data', {}):
        # Double semester format - use current semester data
        verification = result.get('verification', {}).get('current', {})
        credits_match = verification.get('credits', {}).get('match', False)
        egp_match = verification.get('egp', {}).get('match', False)
        sgpa_match = verification.get('sgpa', {}).get('match', False)
        
        reported_credits = result.get('performance_data', {}).get('current', {}).get('credits', 0)
        reported_egp = result.get('performance_data', {}).get('current', {}).get('egp', 0)
        reported_sgpa = result.get('performance_data', {}).get('current', {}).get('sgpa', 0)
        calculated_credits = result.get('calculated_data', {}).get('current', {}).get('credits', 0)
        calculated_egp = result.get('calculated_data', {}).get('current', {}).get('egp', 0)
        calculated_sgpa = result.get('calculated_data', {}).get('current', {}).get('sgpa', 0)
    else:
        # Fallback
        credits_match = egp_match = sgpa_match = False
        reported_credits = reported_egp = reported_sgpa = 0
        calculated_credits = calculated_egp = calculated_sgpa = 0
    
    # Ensure proper data types
    row_data = {
        'filename': str(filename),
        'student_name': str(student_info.get('name', '')),
        'mother_name': str(student_info.get('mother_name', '')),
        'registration_no': str(student_info.get('registration_no', '')),  # Force string
        'program': str(student_info.get('program', '')),
        'department': str(student_info.get('department', '')),
        'semester': str(student_info.get('semester', '')),
        'examination': str(student_info.get('examination', '')),
        'student_type': str(result.get('student_type', '')),
        'verification_status': str(result.get('status', '')),
        'reported_credits': float(reported_credits),
        'reported_egp': float(reported_egp),
        'reported_sgpa': float(reported_sgpa),
        'calculated_credits': float(calculated_credits),
        'calculated_egp': float(calculated_egp),
        'calculated_sgpa': float(calculated_sgpa),
        'credits_match': 'Yes' if credits_match else 'No',
        'egp_match': 'Yes' if egp_match else 'No',
        'sgpa_match': 'Yes' if sgpa_match else 'No',
        'total_courses': int(len(courses)),
        'grade_A+_count': int(grade_counts.get('A+', 0)),
        'grade_A_count': int(grade_counts.get('A', 0)),
        'grade_B+_count': int(grade_counts.get('B+', 0)),
        'grade_B_count': int(grade_counts.get('B', 0)),
        'grade_C+_count': int(grade_counts.get('C+', 0)),
        'grade_C_count': int(grade_counts.get('C', 0)),
        'grade_D_count': int(grade_counts.get('D', 0)),
        'grade_F_count': int(grade_counts.get('F', 0)),
        'extraction_date': str(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    }
    
    return row_data

def ensure_dtypes(df):
    """Ensure DataFrame has correct dtypes"""
    for col, dtype in COLUMN_DTYPES.items():
        if col in df.columns:
            if dtype == 'str':
                df[col] = df[col].astype(str)
            elif dtype == 'int64':
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            elif dtype == 'float64':
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).astype(float)
    return df

def save_to_dataset(result, filename):
    """
    Save a single marksheet result to the dataset Excel file
    Each marksheet becomes one row in the dataset
    """
    
    # Extract row data
    row_data = extract_row_data(result, filename)
    
    # Create DataFrame with proper dtypes
    df_new = pd.DataFrame([row_data])
    df_new = ensure_dtypes(df_new)
    
    # Check if dataset exists
    if os.path.exists(DATASET_FILE):
        try:
            # Load existing dataset with proper dtypes
            df_existing = pd.read_excel(DATASET_FILE)
            df_existing = ensure_dtypes(df_existing)
            
            # Check if this filename already exists
            if filename in df_existing['filename'].values:
                # Update existing row - remove old row and append new one
                df_existing = df_existing[df_existing['filename'] != filename]
                df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            else:
                # Append new row
                df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            
            # Ensure dtypes again after concatenation
            df_combined = ensure_dtypes(df_combined)
            
        except Exception as e:
            print(f"Error reading existing file, creating new one: {e}")
            df_combined = df_new
    else:
        # Create new dataset
        df_combined = df_new
    
    # Save to Excel
    df_combined.to_excel(DATASET_FILE, index=False)
    
    return DATASET_FILE

def save_bulk_to_dataset(results_list):
    """
    Save multiple marksheet results to the dataset
    """
    saved_count = 0
    errors = []
    
    # Collect all rows first
    all_rows = []
    
    for result_data in results_list:
        try:
            result = result_data.get('full_result')
            filename = result_data.get('filename')
            if result and filename:
                row_data = extract_row_data(result, filename)
                all_rows.append(row_data)
                saved_count += 1
        except Exception as e:
            errors.append(f"{filename}: {str(e)}")
    
    if all_rows:
        # Create DataFrame from all rows
        df_new = pd.DataFrame(all_rows)
        df_new = ensure_dtypes(df_new)
        
        # Check if dataset exists
        if os.path.exists(DATASET_FILE):
            try:
                df_existing = pd.read_excel(DATASET_FILE)
                df_existing = ensure_dtypes(df_existing)
                
                # Remove existing rows that are being updated
                existing_filenames = set(df_new['filename'].values)
                df_existing = df_existing[~df_existing['filename'].isin(existing_filenames)]
                
                # Combine
                df_combined = pd.concat([df_existing, df_new], ignore_index=True)
                df_combined = ensure_dtypes(df_combined)
            except Exception as e:
                print(f"Error reading existing file, creating new one: {e}")
                df_combined = df_new
        else:
            df_combined = df_new
        
        # Save to Excel
        df_combined.to_excel(DATASET_FILE, index=False)
    
    return saved_count, errors

def view_dataset():
    """Utility function to view the current dataset"""
    if os.path.exists(DATASET_FILE):
        df = pd.read_excel(DATASET_FILE)
        print(f"Dataset contains {len(df)} records")
        print("\nColumns:", list(df.columns))
        print("\nFirst few rows:")
        print(df.head())
        return df
    else:
        print("No dataset found")
        return None

def clear_dataset():
    """Utility function to clear the dataset"""
    if os.path.exists(DATASET_FILE):
        os.remove(DATASET_FILE)
        print("Dataset cleared")
    else:
        print("No dataset to clear")