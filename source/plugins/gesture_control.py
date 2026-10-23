"""Reviewed local adaptation plugin. Starting cameras requires the human UI."""
PLUGIN={'name':'gesture_control','description':'Read gesture status or stop gesture cameras/control. To start, tell the user to press GESTURES in the setup drawer and choose a camera themselves.',
 'parameters':{'type':'OBJECT','properties':{'action':{'type':'STRING','enum':['status','stop']}},'required':['action']},'tier':'core'}
def run(parameters,player=None,session_memory=None):
    from core.gestures import service
    action=parameters.get('action')
    if action=='stop':service.stop()
    elif action!='status':return 'Use the GESTURES button on the PC to grant camera and input permission. I cannot grant it myself.'
    state=service.status()
    return f"Gestures: {state['mode']}; Windows input {'enabled' if state['control'] else 'disabled'}. {state['message']}"
