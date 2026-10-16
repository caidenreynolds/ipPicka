:start
@echo off
Color 2
set name=none
echo Set Network/Ethernet IP
echo (Run as admin to change IP settings)

:checkip
ipconfig
pause

:setName
echo ------------------------------
echo - (press enter to skip) -
set /p name=  Enter network name:
echo ------------------------------

:option
echo ------------------------------
echo --Select option for %name%--
echo ------------------------------
echo    2:Change Network Name
echo    1:Change Network IP address
echo    0:Check IP Configuration
echo   -1:Exit
echo -----------------------------
set /p result=Enter Option:
if %result%==0 goto checkip
if %result%==1 goto setip
if %result%==2 goto setName
goto end

:setip
echo ------------------------------
set /p pcIP=  Enter new IP address: 
set /p subnet=  Enter subnet mask: 
set /p gate=  Enter default gateway:  
pause
echo ------------------------------
@echo on
netsh interface ipv4 set address %name% static %pcIP% %subnet% %gate%
echo ------------------------------
@echo off
pause
goto checkip

:end
