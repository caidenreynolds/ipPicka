@echo off
:menu
echo Select an IP configuration:
echo 1 - 192.168.1.244
echo 2 - 169.254.0.1
echo 3 - 10.203.1.8
echo 4 - 192.168.0.244
echo 5 - 192.168.2.244
echo 6 - 192.168.158.244
set /p choice="Enter your choice: "
if %choice%==1 goto config1
if %choice%==2 goto config2
if %choice%==3 goto config3
if %choice%==4 goto config4
if %choice%==5 goto config5
if %choice%==6 goto config6
echo Invalid choice.
goto menu

:config1
netsh interface ip set address name="Ethernet 4" static 192.168.1.244 255.255.255.0
echo Configuration set to 192.168.1.244
pause
goto end

:config2
netsh interface ip set address name="Ethernet 4" static 169.254.0.1 255.255.0.0
echo Configuration set to 169.254.0.1
pause
goto end

:config3
netsh interface ip set address name="Ethernet 4" static 10.203.1.8 255.255.255.0
echo Configuration set to 10.203.1.8
pause
goto end

:config4
netsh interface ip set address name="Ethernet 4" static 192.168.0.244 255.255.255.0 192.168.0.201
echo Configuration set to 192.168.0.244
pause
goto end

:config5
netsh interface ip set address name="Ethernet 4" static 192.168.2.244 255.255.255.0
echo Configuration set to 192.168.2.244
pause
goto end

:config6
netsh interface ip set address name="Ethernet 4" static 192.168.158.244 255.255.255.0
echo Configuration set to 192.168.158.244
pause
goto end

:end
