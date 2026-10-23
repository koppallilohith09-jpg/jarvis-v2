from core.local_capabilities import tool
TOOL={
    'name':'local_productivity','tier':'core',
    'description':'Use local tools for Word/PDF/PowerPoint/Excel creation, persistent calendar/reminders, ICS export, saved app-opening routines, system diagnostics, local-model inventory, clipboard processing and a local daily briefing. Pass an explicit command. Does not send messages, use cloud AI, or run generated code.',
    'brief':'Local documents, calendar, reminders, routines, clipboard and diagnostics.',
    'parameters':{'type':'OBJECT','properties':{'command':{'type':'STRING','description':'Examples: create a PDF about TOPIC; remind me in 5 minutes to TASK; schedule TITLE on 2026-10-30 at 14:30; show my schedule; daily briefing; system diagnostics; save routine study: open Notepad; open YouTube; run routine study.'}},'required':['command']},
    'handler':tool,
}
