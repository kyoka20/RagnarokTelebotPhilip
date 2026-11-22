' Menjalankan jaga_bot.ps1 tanpa memunculkan jendela apa pun (dipanggil Task Scheduler).
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & folder & "\jaga_bot.ps1""", 0, False
