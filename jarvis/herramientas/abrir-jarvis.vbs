' ============================================================
' JARVIS - Lanzador de la aplicacion de escritorio
' 1) Comprueba si el servidor responde en el puerto 8200.
' 2) Si no, lo arranca oculto (servidor-oculto.vbs) y espera.
' 3) Abre el centro de mando como aplicacion (Edge --app).
' Asi el acceso directo funciona SIEMPRE, este o no el servidor
' corriendo (soluciona el ERR_CONNECTION_REFUSED).
' ============================================================
Option Explicit
Dim fso, shell, carpeta, i, edge

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
carpeta = fso.GetParentFolderName(WScript.ScriptFullName) ' ...\herramientas

Function ServidorResponde()
  On Error Resume Next
  Dim h
  Set h = CreateObject("MSXML2.XMLHTTP")
  h.open "GET", "http://localhost:8200/api/config", False
  h.send
  ServidorResponde = (Err.Number = 0)
  If ServidorResponde Then ServidorResponde = (h.status = 200)
  On Error GoTo 0
End Function

' Arrancar el servidor si hace falta y esperar a que responda (max 20 s)
If Not ServidorResponde() Then
  shell.Run "wscript.exe """ & carpeta & "\servidor-oculto.vbs""", 0, False
  For i = 1 To 40
    WScript.Sleep 500
    If ServidorResponde() Then Exit For
  Next
End If

' Abrir como aplicacion (ventana propia, sin pestanas)
edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
If Not fso.FileExists(edge) Then edge = "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
If fso.FileExists(edge) Then
  shell.Run """" & edge & """ --app=http://localhost:8200", 1, False
Else
  shell.Run "http://localhost:8200", 1, False ' navegador por defecto
End If
