' Lanza un script de PowerShell sin ninguna ventana: ni consola fija ni el parpadeo negro que
' deja `powershell.exe -WindowStyle Hidden` al abrirse. Lo usan el acceso del escritorio y el
' menu del icono de bandeja (`icono_bandeja.ps1`).
'
' Uso:  wscript.exe eim_oculto.vbs "<ruta del .ps1>" [argumentos del script...]
Option Explicit
Dim sh, args, cmd, i, a
Set sh = CreateObject("WScript.Shell")
Set args = WScript.Arguments
If args.Count = 0 Then
  WScript.Echo "Falta la ruta del .ps1 que hay que lanzar."
  WScript.Quit 1
End If
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & args(0) & """"
For i = 1 To args.Count - 1
  a = args(i)
  If InStr(a, " ") > 0 And Left(a, 1) <> """" Then a = """" & a & """"
  cmd = cmd & " " & a
Next
' 0 = sin ventana, False = no esperar a que termine.
sh.Run cmd, 0, False
