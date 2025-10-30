@echo off
REM Newsletter Cleanup Utility - Windows Batch Script

if "%1"=="--list" (
    echo Listing recent newsletters...
    python newsletter_cleanup_utility.py --list
    goto :end
)

if "%1"=="" (
    echo Usage:
    echo   cleanup_newsletter.bat --list
    echo   cleanup_newsletter.bat "https://newsletter-url-here"
    echo.
    echo Examples:
    echo   cleanup_newsletter.bat --list
    echo   cleanup_newsletter.bat "https://guyraz.substack.com/p/10-lessons-from-chip-and-joanna-gaines"
    goto :end
)

echo Cleaning up newsletter: %1
python newsletter_cleanup_utility.py --url %1

:end
pause