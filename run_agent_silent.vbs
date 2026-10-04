Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\tomorr\Desktop\couch_agent"
WshShell.Run "python agent.py", 0, False