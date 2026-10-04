# `services.workflow_engine` 零参函数试探调用

**目的**：签名只能说明「收什么返什么」，**不能给出数据内容**。
对无副作用的零参访问器直接调用，可恢复**真实数据**（例如竞赛步骤清单）。

| 结果 | 数量 |
|---|---|
| 试探的零参函数 | 5 |
| 成功返回 | **5** |
| 抛错/超时 | 0 |

## ★ 成功恢复的真实数据

### `_comp_en_steps()` → `list`

```json
"[StepDef(skill_name='comp-prob-analysis', display_name='Problem Analysis', output_files=['PROBLEM_ANALYSIS.md'], primary_output='PROBLEM_ANALYSIS.md', has_checkpoint=True, checkpoint_type='approve'), StepDef(skill_name='comp-modeling', display_name='Modeling & Solution', output_files=['MODELING_REPORT.md'], primary_output='MODELING_REPORT.md', has_checkpoint=True, checkpoint_type='feedback'), StepDef(skill_name='comp-code', display_name='Programming', output_files=['code/main.py', 'RESULTS.md'], primary_output='RESULTS.md', has_checkpoint=True, checkpoint_type='approve'), StepDef(skill_name='paper-figure', display_name='Figure Generation', output_files=['figures/latex_includes.tex'], primary_output='figures/', has_checkpoint=False, checkpoint_type=None), StepDef(skill_name='paper-figure-drawio', display_name='Flow & Architecture Diagrams', output_files=['figures/latex_includes.tex'], primary_output='figures/', has_checkpoint=False, checkpoint_type=None), StepDef(skill_name='comp-review', display_name='Logic Adversarial Review', output_files=['COMP_REVIEW.md'], primary_output='COMP_REVIEW.md', has_checkpoint=False, checkpoint_type=None), StepDef(skill_name='comp-paper-en', display_name='Paper Writing (English)', output_files=['paper/main.tex'], primary_output='paper/main.tex', has_checkpoint=True, checkpoint_type='approve'), StepDef(skill_name='comp-compile-en', display_name='Compile & Compliance Check', output_files=['paper/main.pdf'], primary_output='paper/main.pdf', has_checkpoint=False, checkpoint_type=None)]"
```

### `checker_environment()` → `dict`

```json
{
 "ALLUSERSPROFILE": "C:\\ProgramData",
 "APPDATA": "C:\\Users\\SAKE\\AppData\\Roaming",
 "CHOCOLATEYINSTALL": "C:\\ProgramData\\chocolatey",
 "CHOCOLATEYLASTPATHUPDATE": "134327243865552778",
 "COMMONPROGRAMFILES": "C:\\Program Files\\Common Files",
 "COMMONPROGRAMFILES(X86)": "C:\\Program Files (x86)\\Common Files",
 "COMMONPROGRAMW6432": "C:\\Program Files\\Common Files",
 "COMPUTERNAME": "FORESAKE",
 "COMSPEC": "C:\\WINDOWS\\system32\\cmd.exe",
 "DRIVERDATA": "C:\\Windows\\System32\\Drivers\\DriverData",
 "DSH_HOME": "C:\\Users\\SAKE\\.dsh",
 "DSH_PROFILE": "desktop",
 "DSH_PROFILE_DIR": "C:\\Users\\SAKE\\.dsh\\profiles\\desktop",
 "DSH_SESSION_ID": "session-1451ea1a-5730-4bcd-8f9f-4713b6e94b6d",
 "DSH_SHELL": "1",
 "DSH_WEB_URL": "http://127.0.0.1:19387",
 "EFC_32124_1592913036": "1",
 "EFC_32124_4126798990": "1",
 "ELECTRON_RUN_AS_NODE": "1",
 "GIT_PAGER": "cat",
 "HOMEDRIVE": "C:",
 "HOMEPATH": "\\Users\\SAKE",
 "LOCALAPPDATA": "C:\\Users\\SAKE\\AppData\\Local",
 "LOGONSERVER": "\\\\FORESAKE",
 "NO_COLOR": "1",
 "NUMBER_OF_PROCESSORS": "16",
 "ONEDRIVE": "C:\\Users\\SAKE\\OneDrive",
 "ONEDRIVECONSUMER": "C:\\Users\\SAKE\\OneDrive",
 "OS": "Windows_NT",
 "PAGER": "cat",
 "PATH": "E:\\02_Installers\\DailyApps\\Modex-MH-Agent\\runtime\\texlive\\miktex\\bin\\x64;C:\\Python314\\Scripts\\;C:\\Python314\\;C:\\WINDOWS\\system32;C:\\WINDOWS;C:\\WINDOWS\\System32\\Wbem;C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\;C:\\WINDOWS\\System32\\OpenSSH\\;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA App\\NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\Program Files\\nodejs\\;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\Git\\cmd;D:\\04_IDEs\\MATLAB\\R2026a\\runtime\\win64;D:\\04_IDEs\\MATLAB\\R2026a\\bin;C:\\Program Files\\GitHub CLI\\;C:\\Python314\\Scripts\\;C:\\Python314\\;C:\\WINDOWS\\system32;C:\\WINDOWS;C:\\WINDOWS\\System32\\Wbem;C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\;C:\\WINDOWS\\System32\\OpenSSH\\;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA App\\NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\Program Files\\nodejs\\;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Users\\SAKE\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\SAKE\\AppData\\Roaming\\npm;D:\\04_IDEs\\VSCode\\bin;D:\\04_IDEs\\texlive\\2026\\bin\\windows;E:\\02_Installers\\DailyApps\\psmux;C:\\Users\\SAKE\\AppData\\Local\\Microsoft\\WinGet\\Packages\\jqlang.jq_Microsoft.Winget.Source_8wekyb3d8bbwe;C:\\Users\\SAKE\\.dotnet\\tools;C:\\Users\\SAKE\\AppData\\Local\\Microsoft\\WinGet\\Packages\\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe;C:\\Users\\SAKE\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-9.0.2-full_build\\bin;",
 "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.CPL",
 "PROCESSOR_ARCHITECTURE": "AMD64",
 "PROCESSOR_IDENTIFIER": "AMD64 Family 25 Model 97 Stepping 2, AuthenticAMD",
 "PROCESSOR_LEVEL": "25",
 "PROCESSOR_REVISION": "6102",
 "PROGRAMDATA": "C:\\ProgramData",
 "PROGRAMFILES": "C:\\Program Files",
 "PROGRAMFILES(X86)": "C:\\Program Files (x86)",
 "PROGRAMW6432": "C:\\Program Files",
 "PSMODULEPATH": "C:\\Users\\SAKE\\Documents\\WindowsPowerShell\\Modules;C:\\Program Files\\WindowsPowerShell\\Modules;C:\\WINDOWS\\system32\\WindowsPowerShell\\v1.0\\Modules",
 "PUBLIC": "C:\\Users\\Public",
 "PYTHONIOENCODING": "utf-8",
 "SESSIONNAME": "Console",
 "SYSTEMDRIVE": "C:",
 "SYSTEMROOT": "C:\\WINDOWS",
 "TEMP": "C:\\Users\\SAKE\\AppData\\Local\\Temp",
 "TMP": "C:\\Users\\SAKE\\AppData\\Local\\Temp",
 "USERDOMAIN": "FORESAKE",
 "USERDOMAIN_ROAMINGPROFILE": "FORESAKE",
 "USERNAME": "SAKE",
 "USERPROFILE": "C:\\Users\\SAKE",
 "VIPSHOME": "\\\\?\\D:\\12_Agents\\DeepSeek Harness\\resources\\app.asar.unpacked\\dsh\\node_modules\\@img\\sharp-win32-x64",
 "WINDIR": "C:\\WINDOWS",
 "PYTHONUTF8": "1"
}
```

### `get_db()` → `coroutine`

```json
"<_cython_3_2_5.coroutine object at 0x00000149CA856C20>"
```

### `prepare_task_payers()` → `coroutine`

```json
"<_cython_3_2_5.coroutine object at 0x00000149CA856B90>"
```

### `require_execution_mode()` → `ExecutionIdentity`

```json
"ExecutionIdentity(mode='key', account_id=None, revision=0)"
```

