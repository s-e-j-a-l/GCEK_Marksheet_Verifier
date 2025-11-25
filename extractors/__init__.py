from .base_extractor import BaseExtractor
from .nep_extractor import NEPExtractor
from .non_nep_single_extractor import NonNEPSingleExtractor
from .non_nep_double_extractor import NonNEPDoubleExtractor

class ExtractorFactory:
    @staticmethod
    def get_extractor(text):
        """Determine the appropriate extractor based on PDF content"""
        
        # Check for NEP format
        if "MSE" in text and "ISE" in text and "ESE" in text:
            return NEPExtractor()
        
        # Check for Non-NEP double semester format
        elif "Previous Semester Performance" in text and "Current Semester Performance" in text:
            # Count how many semester sections exist
            semester_count = text.count("Semester :")
            if semester_count >= 2:
                return NonNEPDoubleExtractor()
        
        # Default to single semester Non-NEP
        return NonNEPSingleExtractor()

# For backward compatibility
class UniversalMarksheetExtractor:
    def __init__(self):
        self.courses = []
        self.student_type = "Unknown"
    
    def extract_text_from_pdf(self, pdf_path):
        return BaseExtractor().extract_text_from_pdf(pdf_path)
    
    def process_pdf(self, pdf_path):
        text = self.extract_text_from_pdf(pdf_path)
        extractor = ExtractorFactory.get_extractor(text)
        result = extractor.process_pdf(pdf_path)
        self.student_type = extractor.student_type
        
        # Handle different return formats
        if isinstance(result, dict) and 'all_courses' in result:
            return result['all_courses']
        else:
            return result