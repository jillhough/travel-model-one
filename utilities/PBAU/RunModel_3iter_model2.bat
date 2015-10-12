::~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
:: RunModel.bat
::
:: MS-DOS batch file to execute the MTC travel model.  Each of the model steps are sequentially
:: called here.  
::
:: For complete details, please see http://mtcgis.mtc.ca.gov/foswiki/Main/RunModelBatch.
::
:: dto (2012 02 15) gde (2009 04 22)
::
::~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:: copy CTRAMP
set CTRAMP_SRC=C:\Users\mtcpb\Documents\GitHub\travel-model-one-v05
robocopy /MIR %CTRAMP_SRC%\model-files\model            CTRAMP\model
robocopy /MIR %CTRAMP_SRC%\model-files\runtime          CTRAMP\runtime
robocopy /MIR %CTRAMP_SRC%\model-files\scripts          CTRAMP\scripts
copy /Y %CTRAMP_SRC%\model-files\RunIteration.bat       CTRAMP
copy /Y %CTRAMP_SRC%\model-files\RunAccessibility.bat   .
copy /Y %CTRAMP_SRC%\model-files\RunMetrics.bat         .
copy /Y %CTRAMP_SRC%\utilities\PBAU\ExtractKeyFiles.bat .

:: ------------------------------------------------------------------------------------------------------
::
:: Step 1:  Set the necessary path variables
::
:: ------------------------------------------------------------------------------------------------------

:: The location of the 64-bit java development kit
set JAVA_PATH=C:\Program Files\Java\jdk1.7.0_71

:: The location of the GAWK binary executable files
set GAWK_PATH=M:\UTIL\Gawk

:: The location of R
set R_HOME=C:\Program Files\R\R-3.2.0

:: The location of the RUNTPP executable from Citilabs - 64bit first
set TPP_PATH=C:\Program Files\Citilabs\CubeVoyager;C:\Program Files (x86)\Citilabs\CubeVoyager

:: The location of python
set PYTHON_PATH=C:\Python27

:: The location of the MTC.JAR file
set RUNTIME=CTRAMP/runtime

:: Add these variables to the PATH environment variable, moving the current path to the back
set OLD_PATH=%PATH%
set PATH=%RUNTIME%;%JAVA_PATH%/bin;%TPP_PATH%;%GAWK_PATH%/bin;%PYTHON_PATH%;%OLD_PATH%

::  Set the Java classpath (locations where Java needs to find configuration and JAR files)
set CLASSPATH=%RUNTIME%/config;%RUNTIME%;%RUNTIME%/config/jppf-2.4/jppf-2.4-admin-ui/lib/*;%RUNTIME%/mtc.jar

::  Set the IP address of the host machine which sends tasks to the client machines 
set HOST_IP_ADDRESS=192.168.1.207


:: ------------------------------------------------------------------------------------------------------
::
:: Step 2:  Create the directory structure
::
:: ------------------------------------------------------------------------------------------------------

:: Create the working directories
mkdir hwy
mkdir trn
mkdir skims
mkdir landuse
mkdir popsyn
mkdir nonres
mkdir main
mkdir logs
mkdir database

:: Stamp the feedback report with the date and time of the model start
echo STARTED MODEL RUN  %DATE% %TIME% >> logs\feedback.rpt 

:: Move the input files, which are not accessed by the model, to the working directories
copy INPUT\hwy\                 hwy\
copy INPUT\trn\transit_lines\   trn\
copy INPUT\trn\transit_fares\   trn\ 
copy INPUT\trn\transit_support\ trn\
copy INPUT\landuse\             landuse\
copy INPUT\popsyn\              popsyn\
copy INPUT\nonres\              nonres\
copy INPUT\warmstart\main\      main\
copy INPUT\warmstart\nonres\    nonres\


:: ------------------------------------------------------------------------------------------------------
::
:: Step 3:  Pre-process steps
::
:: ------------------------------------------------------------------------------------------------------

: Pre-Process

:: Runtime configuration: set project directory, auto operating cost, 
:: and synthesized household/population files in the appropriate places
python CTRAMP\scripts\preprocess\RuntimeConfiguration.py
if ERRORLEVEL 1 goto done

:: Make sure java isn't running already
copy /Y CTRAMP\runtime\pslist_exe.txt                   CTRAMP\runtime\pslist.exe
CTRAMP\runtime\pslist.exe java
if %ERRORLEVEL% EQU 0 goto done

cd CTRAMP\runtime
set RUNTIMEDIR=%CD%

:: Run the java processes locally and verify
copy /Y PsExec_exe.txt PsExec.exe
.\PsExec.exe JavaOnly_runMain.cmd
.\PsExec.exe JavaOnly_runNode0.cmd
.\pslist.exe java
if %ERRORLEVEL% NEQ 0 goto done


M:
cd %RUNTIMEDIR%
cd ..
cd ..

:: Set the prices in the roadway network
runtpp CTRAMP\scripts\preprocess\SetTolls.job
if ERRORLEVEL 2 goto done

:: Set a penalty to dummy links connecting HOV/HOT lanes and general purpose lanes
runtpp CTRAMP\scripts\preprocess\SetHovXferPenalties.job
if ERRORLEVEL 2 goto done

:: Create time-of-day-specific 
runtpp CTRAMP\scripts\preprocess\CreateFiveHighwayNetworks.job
if ERRORLEVEL 2 goto done

:: Add pavement cost adjustment for state of good repair work
runtpp CTRAMP\scripts\preprocess\AddPavementCost.job
if ERRORLEVEL 2 goto done



:: ------------------------------------------------------------------------------------------------------
::
:: Step 4:  Build non-motorized level-of-service matrices
::
:: ------------------------------------------------------------------------------------------------------

: Non-Motorized Skims

:: Translate the roadway network into a non-motorized network
runtpp CTRAMP\scripts\skims\CreateNonMotorizedNetwork.job
if ERRORLEVEL 2 goto done

:: Build the skim tables
runtpp CTRAMP\scripts\skims\NonMotorizedSkims.job
if ERRORLEVEL 2 goto done


:: ------------------------------------------------------------------------------------------------------
::
:: Step 5:  Prepare for Iteration 0
::
:: ------------------------------------------------------------------------------------------------------

: iter0

:: Set the iteration parameters
set ITER=0
set PREV_ITER=0
set WGT=1.0
set PREV_WGT=0.00


:: ------------------------------------------------------------------------------------------------------
::
:: Step 6:  Execute the RunIteration batch file
::
:: ------------------------------------------------------------------------------------------------------

call CTRAMP\RunIteration.bat
if ERRORLEVEL 2 goto done

:: ------------------------------------------------------------------------------------------------------
::
:: Step 7:  Prepare for iteration 1 and execute RunIteration batch file
::
:: ------------------------------------------------------------------------------------------------------

: iter1

:: Set the iteration parameters
set ITER=1
set PREV_ITER=1
set WGT=1.0
set PREV_WGT=0.00
set SAMPLESHARE=0.15
set SEED=0

:: Runtime configuration: set the workplace shadow pricing parameters
python CTRAMP\scripts\preprocess\RuntimeConfiguration.py --iter %ITER%
if ERRORLEVEL 1 goto done

:: Call RunIteration batch file
call CTRAMP\RunIteration.bat
if ERRORLEVEL 2 goto done


:: ------------------------------------------------------------------------------------------------------
::
:: Step 8:  Prepare for iteration 2 and execute RunIteration batch file
::
:: ------------------------------------------------------------------------------------------------------

: iter2

:: Set the iteration parameters
set ITER=2
set PREV_ITER=1
set WGT=0.50
set PREV_WGT=0.50
set SAMPLESHARE=0.25
set SEED=0

:: Runtime configuration: set the workplace shadow pricing parameters
python CTRAMP\scripts\preprocess\RuntimeConfiguration.py --iter %ITER%
if ERRORLEVEL 1 goto done

:: Call RunIteration batch file
call CTRAMP\RunIteration.bat
if ERRORLEVEL 2 goto done

:: ------------------------------------------------------------------------------------------------------
::
:: Step 7.1.1:  Run transit assignment and metrics for iter2 outputs
::
:: ------------------------------------------------------------------------------------------------------
runtpp CTRAMP\scripts\assign\TransitAssign.job
if ERRORLEVEL 2 goto done

call RunAccessibility
if ERRORLEVEL 2 goto done

call RunMetrics
if ERRORLEVEL 2 goto done

call ExtractKeyFiles
if ERRORLEVEL 2 goto done

:: save iter2 outputs
move accessibilities accessibilities_iter%ITER%
move core_summaries  core_summaries_iter%ITER%
move metrics         metrics_iter%ITER%
move extractor       extractor_iter%ITER%

:: ------------------------------------------------------------------------------------------------------
::
:: Step 9:  Prepare for iteration 3 and execute RunIteration batch file
::
:: ------------------------------------------------------------------------------------------------------

: iter3

:: Set the iteration parameters
set ITER=3
set PREV_ITER=2
set WGT=0.33
set PREV_WGT=0.67
set SAMPLESHARE=0.50
set SEED=0

:: Runtime configuration: set the workplace shadow pricing parameters
python CTRAMP\scripts\preprocess\RuntimeConfiguration.py --iter %ITER%
if ERRORLEVEL 1 goto done

:: Call RunIteration batch file
call CTRAMP\RunIteration.bat
if ERRORLEVEL 2 goto done



:: ------------------------------------------------------------------------------------------------------
::
:: Step 9.1: Kill java processes
::
:: ------------------------------------------------------------------------------------------------------
copy /Y CTRAMP\runtime\pskill_exe.txt                   CTRAMP\runtime\pskill.exe
CTRAMP\runtime\pskill.exe java

:: ------------------------------------------------------------------------------------------------------
::
:: Step 10:  Assign transit trips to the transit network
::
:: ------------------------------------------------------------------------------------------------------

: trnAssign

runtpp CTRAMP\scripts\assign\TransitAssign.job
if ERRORLEVEL 2 goto done


:: ------------------------------------------------------------------------------------------------------
::
:: Step 11:  Build simplified skim databases
::
:: ------------------------------------------------------------------------------------------------------

: database

runtpp CTRAMP\scripts\database\SkimsDatabase.job
if ERRORLEVEL 2 goto done


:: ------------------------------------------------------------------------------------------------------
::
:: Step 12:  Build destination choice logsums
::
:: ------------------------------------------------------------------------------------------------------

: logsums

call RunAccessibility
if ERRORLEVEL 2 goto done


:: ------------------------------------------------------------------------------------------------------
::
:: Step 13:  Core summaries
::
:: ------------------------------------------------------------------------------------------------------

: core_summaries
::
:: call RunCoreSummaries
:: if ERRORLEVEL 2 goto done
::

:: ------------------------------------------------------------------------------------------------------
::
:: Step 14:  Cobra Metrics
::
:: ------------------------------------------------------------------------------------------------------

:: These files are invalid (from iter2).  Flush to make RunMetrics regenerate it.
del main\tripsEVinc1.tpp
del trn\quickboards.xls

call RunMetrics
if ERRORLEVEL 2 goto done

:: ------------------------------------------------------------------------------------------------------
::
:: Step 15:  Directory clean up
::
:: ------------------------------------------------------------------------------------------------------


: cleanup

:: Put the PATH back the way you found it
set PATH=%OLD_PATH%

:: Move all the TP+ printouts to the \logs folder
copy *.prn logs\*.prn

:: Delete all the temporary TP+ printouts and cluster files
del *.prn
del *.script.*
del *.script

:: ------------------------------------------------------------------------------------------------------
::
:: Step 16:  Extractor
::
:: ------------------------------------------------------------------------------------------------------
call ExtractKeyFiles
if ERRORLEVEL 2 goto done

:: Success target and message
:success
ECHO FINISHED SUCCESSFULLY!

:: Complete target and message
:done
ECHO FINISHED.  