@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo  推送作品集到 GitHub
echo ============================================
echo.

echo [1/3] 检查本地提交...
git log --oneline -3
if errorlevel 1 (
  echo.
  echo [错误] 当前目录不是 git 仓库，或 git 未安装。
  pause
  exit /b 1
)
echo.

echo [2/3] 切换远程地址为 HTTPS（浏览器登录，不需要 SSH 密钥）
git remote set-url origin https://github.com/Lex3300/game-ops-portfolio.git
git remote -v
echo.

echo [3/3] 开始推送...
echo.
echo   接下来如果弹出 GitHub 登录窗口，请选择
echo   "Sign in with your browser"，在浏览器里点 Authorize 即可。
echo   （只需授权一次，凭据会保存在 Windows 凭据管理器里）
echo.
git push -u origin main
if errorlevel 1 (
  echo.
  echo ============================================
  echo  [失败] 推送没有成功，常见原因：
  echo.
  echo  1. 仓库还没创建：去 https://github.com/new
  echo     名字填 game-ops-portfolio，可见性选 Public
  echo  2. 仓库里已有文件（建时勾了 README）：
  echo     先执行  git pull --rebase origin main  再重跑本脚本
  echo  3. 登录窗口被关掉了：重跑本脚本，重新授权
  echo ============================================
  pause
  exit /b 1
)

echo.
echo ============================================
echo  推送完成，链接：
echo    仓库主页   https://github.com/Lex3300/game-ops-portfolio
echo    在线看板   https://htmlpreview.github.io/?https://github.com/Lex3300/game-ops-portfolio/blob/main/index.html
echo.
echo  注意：仓库必须是 Public，面试官才能打开以上链接。
echo ============================================
pause
