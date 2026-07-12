' ============================================================
' JARVIS - Arranque del servidor en segundo plano (sin ventana)
' Usado por el acceso directo de la carpeta Inicio de Windows.
' Rutas relativas: funciona igual en Creative OS/jarvis y en el
' repo independiente JARVIS-BETA.
' ============================================================
Option Explicit
Dim fso, shell, carpeta, raiz, nodo

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

carpeta = fso.GetParentFolderName(WScript.ScriptFullName) ' ...\herramientas
raiz = fso.GetParentFolderName(carpeta)                    ' raiz de jarvis

' Node portable del equipo; si no existe, intenta el node del PATH.
nodo = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\nodejs-portable\node.exe"
If Not fso.FileExists(nodo) Then nodo = "node"

shell.CurrentDirectory = raiz
' 0 = ventana oculta, False = no esperar (queda de fondo)
shell.Run """" & nodo & """ """ & raiz & "\core\server.js""", 0, False
