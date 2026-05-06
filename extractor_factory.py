from extractors.nep_extractor import NEPExtractor
from extractors.non_nep_single_extractor import NonNEPSingleExtractor
from extractors.non_nep_double_extractor import NonNEPDoubleExtractor

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