#Author-D. L. Ehnebuske
#Description-Fusion 360 add-in to generate finger-joint tabs along a rectangular edge

import adsk.core, adsk.fusion, traceback, math

tolerance = 0.001 #Tolerance in comparing double-length floating point numbers

tabWidthInputId = 'tabWidthValueCommandInput'
mtlThickInputId = 'mtlThickValueCommandInput'
selectedFaceInputId = 'selectedFaceCommandInput'
startWithTabInputId = 'startWithTabCommandInput'
errorMsgInputId = 'errorMsgCommandInput'
tabGenCommandId = 'tabGenCommandButton'
panelId = 'TabCreatePanel'

# global set of event handlers to keep them referenced for the duration
handlers = []

# Distance between two Point3d objects, a and b.
def d(a, b):
    return math.sqrt((a.x - b.x)**2 + (a.y - b.y)**2 + (a.z - b.z)**2)

# Actually lay out and cut the slots to make the tabs on the selected faces.
# It is assumed that the inputs have all been validated.
#
# tabWidth:     The width each tab and gap should be (mm). 
# mtlThick:     The thickness of the material being cut (mm). 
# startWithTab: True if the margins (the areas at ends of the face) are to be 
#               tabs; False if they are to be cut away.
# faces:        A list of BRepFace objects representing the selected faces.
def doIt(tabWidth, mtlThick, startWithTab, faces):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        
        faceLen = []
        faceWid = []
        vert = []
        sketch = []
        nFaces = len(faces)

        # For each selected face, determine face length, width, orientation, 
        # origin, margin and number of tabs
        for i in range(nFaces):
            pRange = faces[i].evaluator.parametricRange()
        
            vert.append(False)
            faceLen.append(pRange.maxPoint.x - pRange.minPoint.x)
            faceWid.append(pRange.maxPoint.y - pRange.minPoint.y)
            if (pRange.maxPoint.y > pRange.maxPoint.x):
                vert[i] = True
                t = faceLen[i]
                faceLen[i] = faceWid[i]
                faceWid[i] = t

        # Create a sketch on each selected face that creates the profiles we 
        # need to cut the gaps between the tabs
        for i in range(nFaces):
            # Create a new sketch on face[i].
            sketch.append(faces[i].body.parentComponent.sketches.add(faces[i]))
            
            # Hard-won knowledge: When a sketch is made on a rectangular face, 
            # (0,0) and the endpoints of the edges of the face are projected 
            # into the sketchPoints. This is not documented that I can find, 
            # but it's true.
            o = sketch[i].sketchPoints.item(1).geometry
            for j in range(1, sketch[i].sketchPoints.count):
                if sketch[i].sketchPoints.item(j).geometry.x < o.x:
                    o.x = sketch[i].sketchPoints.item(j).geometry.x
                if sketch[i].sketchPoints.item(j).geometry.y < o.y:
                    o.y = sketch[i].sketchPoints.item(j).geometry.y

            nTabs = int(faceLen[i] // (2 * tabWidth))
            margin = (faceLen[i] - 2 * tabWidth * nTabs + tabWidth) / 2
            if vert[i]:
                o.y += margin
            else:
                o.x += margin

            # Get the collection of lines in the sketch
            lines = sketch[i].sketchCurves.sketchLines
        
            # Define the extrusion extent to be -tabDepth.
            distance = adsk.core.ValueInput.createByReal(-mtlThick)
        
            # Create the profiles we need for the tabs and gaps
            for j in range(nTabs):
                lines.addTwoPointRectangle(o, adsk.core.Point3D.create(
                    o.x + (mtlThick if vert[i] else tabWidth), 
                    o.y + (tabWidth if vert[i] else mtlThick), 
                    o.z))
                #update origin for next tab
                if vert[i]:
                    o.y += 2 * tabWidth
                else:
                    o.x += 2 * tabWidth

        # Cut the gaps between tabs on each selected face
        for i in range(nFaces):
            # Collect and then sort all the profiles we created
            pList = [sketch[i].profiles.item(j) for j in range(sketch[i].profiles.count)]
            if vert[i]:
                pList.sort(key=lambda profile: profile.boundingBox.minPoint.y, reverse=True)
            else:
                pList.sort(key=lambda profile: profile.boundingBox.minPoint.x, reverse=True)

            # Select the ones we want to use to make the gaps
            profs = adsk.core.ObjectCollection.create()
            for j in range(1 if startWithTab else 0, len(pList), 2):
                profs.add(pList[j])
            
            # Cut the gaps. Do it in one operation to keep the timeline neat
            extrudes = faces[i].body.parentComponent.features.extrudeFeatures
            extrudes.addSimple(
                profs, 
                distance, 
                adsk.fusion.FeatureOperations.CutFeatureOperation)
        return True

    except:
        if ui:
            ui.messageBox('TabGen execution failed: {}'.format(traceback.format_exc()))
    

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        
        class InputChangedHandler(adsk.core.InputChangedEventHandler):
            def __init__(self):
                super().__init__()
            def notify(self, args):
                ui = None
                try:
                    app = adsk.core.Application.get()
                    ui = app.userInterface
                    cmdInput = args.input
                    # If it is the selection input that got changed, check 
                    # that the selections are all a rectangles; deslelect 
                    # those that are not.
                    if cmdInput.id == selectedFaceInputId:
                        for i in range(cmdInput.selectionCount):
                            face = cmdInput.selection(i).entity
                            vertices = face.vertices
                            bad = True
                            if vertices.count == 4:
                                p0 = vertices.item(0).geometry.asVector()
                                p1 = vertices.item(1).geometry.asVector()
                                p2 = vertices.item(2).geometry.asVector()
                                if abs(d(p0, p1) * d(p1, p2) - face.area) < tolerance:
                                    bad = False
                            if bad:
                                selections = [cmdInput.selection(j).entity for j in range(cmdInput.selectionCount)]
                                selections.remove(cmdInput.selection(i).entity)
                                cmdInput.clearSelection()
                                for c in selections:
                                    cmdInput.addSelection(c)
                except:
                    if ui:
                        ui.messageBox('TabGen input changed event failed: {}'.format(traceback.format_exc()))

        class ValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
            def __init__(self):
                super().__init__()
            def notify(self, args):
                ui = None
                try:
                    app = adsk.core.Application.get()
                    ui = app.userInterface
                    # Validate that the tabs are being cut on the edge of 
                    # material and that the face is long enough for at least
                    # one tab
                    commandInputs = args.inputs
                    selInput = commandInputs.itemById(selectedFaceInputId)
                    faces = [selInput.selection(j).entity for j in range(selInput.selectionCount)]
                    tabWidth = commandInputs.itemById(tabWidthInputId).value
                    mtlThick = commandInputs.itemById(mtlThickInputId).value
                    errMsg = commandInputs.itemById(errorMsgInputId)
                    e1 = ''
                    e2 = ''
                    for face in faces:
                        pRange = face.evaluator.parametricRange()
                        dimA = pRange.maxPoint.x - pRange.minPoint.x
                        dimB = pRange.maxPoint.y - pRange.minPoint.y
                        if abs(dimA - mtlThick) > tolerance and abs(dimB - mtlThick) > tolerance:
                            e1 = 'Can only cut tabs on the edge of material.'
                            args.areInputsValid = False
                        if dimA < 2 * tabWidth and dimB < 2 * tabWidth:
                            e2 = 'Edges must be at least 2 * the tab width.'
                            args.areInputsValid = False
                    errMsg.text = e1 + '\n' + e2
                except:
                    if ui:
                        ui.messageBox('TabGen validate inputs failed: {}'.format(traceback.format_exc()))
            
        class CommandExecuteHandler(adsk.core.CommandEventHandler):
            def __init__(self):
                super().__init__()
            def notify(self, args):
                ui = None
                try:
                    app = adsk.core.Application.get()
                    ui = app.userInterface
                    command = args.firingEvent.sender
                    commandInputs = command.commandInputs
                    selInput = commandInputs.itemById(selectedFaceInputId)
                    faces = [selInput.selection(j).entity for j in range(selInput.selectionCount)]
                    tabWidth = commandInputs.itemById(tabWidthInputId).value
                    mtlThick = commandInputs.itemById(mtlThickInputId).value
                    startWithTab = commandInputs.itemById(startWithTabInputId).value
                    doIt(tabWidth, mtlThick, startWithTab, faces)
                except:
                    if ui:
                        ui.messageBox('TabGen executon failed: {}'.format(traceback.format_exc()))

        class CommandCreatedEventHandlerPanel(adsk.core.CommandCreatedEventHandler):
            def __init__(self):
                super().__init__() 
            def notify(self, args):
                ui = None
                try:
                    app = adsk.core.Application.get()
                    ui = app.userInterface
                    cmd = args.command
                    cmd.helpFile = 'help.html'
                    
                    # Add onExecute event handler
                    onExecute = CommandExecuteHandler()
                    cmd.execute.add(onExecute)
                    handlers.append(onExecute)
                    # Add onInputChanged handler
                    onInputChanged = InputChangedHandler()
                    cmd.inputChanged.add(onInputChanged)
                    handlers.append(onInputChanged)
                    # Add onValidateInputs event handler
                    onValidateInputs = ValidateInputsHandler()
                    cmd.validateInputs.add(onValidateInputs)
                    handlers.append(onValidateInputs)

                    # Set up the inputs
                    commandInputs = cmd.commandInputs
                    selComInput = commandInputs.addSelectionInput(
                        selectedFaceInputId, 
                        'Face: ', 
                        'Faces on which to cut tabs')
                    selComInput.addSelectionFilter('PlanarFaces')
                    selComInput.setSelectionLimits(0)
                    commandInputs.addFloatSpinnerCommandInput(tabWidthInputId, 'Tab Width: ', 'mm', 2.0, 20.0, 0.1, 8.0)
                    commandInputs.addFloatSpinnerCommandInput(mtlThickInputId, 'Material Thickness: ', 'mm', 0.5, 6.0, 0.1, 3.0)
                    commandInputs.addBoolValueInput(startWithTabInputId, 'Start with tab: ', True)
                    commandInputs.addTextBoxCommandInput(errorMsgInputId, '', '', 2, True)
                    
                except:
                    if ui:
                        ui.messageBox('TabGen initialization failed: {}'.format(traceback.format_exc()))

        # Create the command definition and add a button to the MODIFY panel.
        cmdDef = ui.commandDefinitions.addButtonDefinition(
            tabGenCommandId, 
            'Generate Tabs', 
            'Creates finger-joint tabs and gaps on rectangular faces')        
        createPanel = ui.allToolbarPanels.itemById('SolidModifyPanel')
        createPanel.controls.addCommand(cmdDef)
        
        # Set up the command created event handler
        onCommandCreated = CommandCreatedEventHandlerPanel()
        cmdDef.commandCreated.add(onCommandCreated)
        handlers.append(onCommandCreated)
        
        # If the command is being manually started let the user know it's done
        if context['IsApplicationStartup'] == False:
            ui.messageBox('The "Generate Tabs" command has been added\nto the MODIFY panel of the MODEL workspace.')


    except:
        if ui:
            ui.messageBox('TabGen add-in start failed: {}'.format(traceback.format_exc()))

def stop(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        modifyPanel = ui.allToolbarPanels.itemById('SolidModifyPanel')
        tabGenButton = modifyPanel.controls.itemById(tabGenCommandId)       
        if tabGenButton:
            tabGenButton.deleteMe()        
        
        cmdDef = ui.commandDefinitions.itemById(tabGenCommandId)
        if cmdDef:
            cmdDef.deleteMe()

    except:
        if ui:
            ui.messageBox('TabGen add-in stop failed: {}'.format(traceback.format_exc()))
