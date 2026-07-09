"""
Logger configuration for the job scraping system.
"""
import sys
from pathlib import Path
from loguru import logger


def setup_logger(settings):
    """Setup logger with configuration from settings"""
    # Remove default logger
    logger.remove()
    
    # Custom format function to handle missing company
    def format_with_company(record):
        company = record["extra"].get("company", "System")
        record["extra"]["company"] = company
        return "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{extra[company]}</cyan> | <level>{message}</level>\n"
    
    # Add console logger
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format=format_with_company,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )
    
    # Add file logger if configured
    if settings.LOG_FILE_PATH:
        # Create log directory if it doesn't exist
        log_path = Path(settings.LOG_FILE_PATH)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        def format_file_with_company(record):
            company = record["extra"].get("company", "System")
            record["extra"]["company"] = company
            return "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[company]} | {message}\n"
        
        logger.add(
            settings.LOG_FILE_PATH,
            level=settings.LOG_LEVEL,
            format=format_file_with_company,
            rotation=settings.LOG_ROTATION,
            retention=settings.LOG_RETENTION,
            compression="zip",
            backtrace=True,
            diagnose=True,
        )
    
    return logger 