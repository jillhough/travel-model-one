@echo off
setlocal enabledelayedexpansion

set COMBINED_DIR=AcrossScenarios
set RUN_NAME_SET=2010_04_ZZZ 2040_03_116 2040_03_127
set CODE_DIR=C:\Users\lzorn\Documents\Travel Model One Utilities\CoreSummaries
::  2040_03_129

:: save these
set OLD_PATH=%PATH%
set PATH=%CODE_DIR%;%PATH%

set R_HOME=C:\Program Files\R\R-3.1.1
set R_USER=lzorn
set R_LIBS_USER=C:\Users\lzorn\Documents\R\win-library\3.1

for %%H in (%RUN_NAME_SET%) DO (

  set RUN_NAME=%%H
  
  rem copy the inputs from the model run directory
  call summarizeScenario.bat
  if %ERRORLEVEL% GTR 0 goto done
)

:: Create the Tablea Data Extracts covering all scenarios
:: First, create the summary dirs list
set SUMMARY_DIRS=%RUN_NAME_SET: =\summary %
set SUMMARY_DIRS=%SUMMARY_DIRS%\summary
echo %SUMMARY_DIRS%

:: Run the conversion script
for %%H in (ActiveTransport.rdata ActivityPattern.rdata AutomobileOwnership.rdata CommuteByEmploymentLocation.rdata CommuteByIncomeHousehold.rdata CommuteByIncomeJob.rdata) DO (
  python "%CODE_DIR%\RdataToTableauExtract.py" %SUMMARY_DIRS% %COMBINED_DIR% %%H
  if %ERRORLEVEL% GTR 0 goto done
)

:done

set PATH=%OLD_PATH%
