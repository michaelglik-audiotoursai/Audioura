@echo off
echo Cleaning up files with long paths that cause Git issues...

REM Remove problematic long-path files
if exist "container_backup\tours\job_fefa438a-9a5c-42ed-959b-275a14dafb2a" (
    echo Removing long path directory...
    rmdir /s /q "container_backup\tours\job_fefa438a-9a5c-42ed-959b-275a14dafb2a"
)

if exist "tours\job_fefa438a-9a5c-42ed-959b-275a14dafb2a" (
    echo Removing long path directory...
    rmdir /s /q "tours\job_fefa438a-9a5c-42ed-959b-275a14dafb2a"
)

REM Clean up any other problematic paths
for /d %%i in ("container_backup\tours\job_*") do (
    for /d %%j in ("%%i\please_generate_auto_tour_on_my_way_from_boston_to_new_york_listing_five_the_most_famous_art_museums_on_my_way_and_describing_there_history*") do (
        echo Removing long path: %%j
        rmdir /s /q "%%j" 2>nul
    )
)

echo Cleanup completed.
echo.
echo Now you can commit changes without long filename issues.