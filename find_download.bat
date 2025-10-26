@echo off
echo Looking for recently downloaded files...

echo Checking for files modified in last 10 minutes:
forfiles /m *.* /c "cmd /c echo @path @fdate @ftime" 2>nul | findstr /i "%date:~-4%"

echo.
echo Checking current directory for all files:
dir /od

echo.
echo Looking for the specific job ID file:
dir *4e93b901*

pause