from sasmaker import Substation
from sasmaker.builder import snap_child_to_slot
from sasmaker.plotting import plot_one_line
from sasmaker.simulation import Simulation, sample_ieds, trigger_busbar_protection, trigger_ied_cb_trip, trigger_ied_cb_close
from sasmaker.util import generate_values_df, create_interfaces, spawn_script
from benign_switching import *
from attack_scheduler import *

import warnings
import sys
from scipy.sparse.linalg import MatrixRankWarning
import xml.etree.ElementTree as ET

warnings.filterwarnings("ignore", category=MatrixRankWarning)

##BUILD BASED ON https://github.com/EngLi/scl-parser/blob/main/scl_parser_v1.py 

#------------------SCD FILES------------------
#Update the scd file below
tree = ET.parse('../../test.scd')
root = tree.getroot()

#print(root)

#Create dictionary of IEDHardwares
IEDHardwares = {}
#Create dictionary of IED OS
IEDOS = {}
#Create dictionary of LDs
LDs = {}
#Create dictionary of Servers
Servers = {}
#Create dictionary of APs
APs = {}

# Substation name and numIEDs

#family = substation name
#numIEDs = number of IEDs

#------------------Communication section of the SCD file-----------------
for subNetwork in root.iter('{http://www.iec.ch/61850/2003/SCL}SubNetwork'):
    print('Subnetwork Name: '+ subNetwork.attrib['name'])
    for accessPoint in subNetwork.iter('{http://www.iec.ch/61850/2003/SCL}ConnectedAP'):
        #Create and add assets to the model
        print('AP Name: '+ accessPoint.attrib['apName'])
        #The IED has not been created already
        if (not (accessPoint.attrib['iedName'] in IEDHardwares)):
            print('IED Name: '+ accessPoint.attrib['iedName'])
            #iedAsset = lang_classes_factory.ns.IEDHardware(name = accessPoint.attrib['iedName'])
            #instance_model.add_asset(iedAsset)
            #iedOSAppAsset = lang_classes_factory.ns.IcsApplication(name = accessPoint.attrib['iedName']+" OS")
            #instance_model.add_asset(iedOSAppAsset)
            #Adding IED to IEDOS
            #ied_iedOS_assoc = lang_classes_factory.ns.SysExecution(
            #hostHardware = [iedAsset], sysExecutedApps = [iedOSAppAsset])
            #instance_model.add_association(ied_iedOS_assoc)
        #The IED was already created (It communicates on multiple APs)
        else:
            #Pick out the already created assets
            print('IED Name: '+ accessPoint.attrib['iedName'])
            #iedAsset = IEDHardwares[accessPoint.attrib['iedName']]
            #iedOSAppAsset = IEDOS[accessPoint.attrib['iedName']]

        #Create associations between assets
        #ap_iedOS_assoc = lang_classes_factory.ns.ApplicationConnection(
        #    appConnections = [aPAsset], applications = [iedOSAppAsset])
        #subnet_ap_assoc = lang_classes_factory.ns.NetworkConnection(
         #   networks = [subNetAsset], netConnections = [aPAsset])
        
        #Add the associations to the model
        #instance_model.add_association(ap_iedOS_assoc)
        #instance_model.add_association(subnet_ap_assoc)
        
        #create a dictionary of the IED Hardware with string, we can use these to create 
        #IED Hardware to connect to the LDs
        IEDHardwares[accessPoint.attrib['iedName']] = accessPoint.attrib['iedName']
        #IED OS dictionnary
        #IEDOS[accessPoint.attrib['iedName']] = iedOSAppAsset
#----------------------------------------------------------------------------

#------------------Substation section of the SCD file-----------------
for substatTree in root.iter('{http://www.iec.ch/61850/2003/SCL}Substation'):
    #Create and add substation
    print('Substation Name'+ substatTree.attrib['name'])

    #Finds PowerTransformers on substation and bay level
    for ptIter in substatTree.iter('{http://www.iec.ch/61850/2003/SCL}PowerTransformer'):
        print('PT Name: '+  ptIter.attrib['name'])
        #add transformer to substation association
        #trans_substat_assoc = lang_classes_factory.ns.SubstatIncludesEq(
        #substation = [substatAsset], equipment = [ptAsset])  
        #instance_model.add_association(trans_substat_assoc)
    #Create all LNs that exist on substation level (For HMI etc)
    for lnFindAll in substatTree.findall('{http://www.iec.ch/61850/2003/SCL}LNode'):  
        #LLN0 does not have an lnInst, in this case we set the value as "0"  
        if (lnFindAll.attrib['lnClass'] == "LLN0"):
            lnInstance = "0"
        else:
            lnInstance = lnFindAll.attrib['lnInst']
        print('Logical Node on substation level: '+ lnFindAll.attrib['lnClass']+"_"+ lnFindAll.attrib['ldInst']+"_"+lnInstance)

        #add LN to substation association
        #ln_substat_assoc = lang_classes_factory.ns.SubstatLevelLN(
        #substation = [substatAsset], logicalNode = [lnAsset])  
        #instance_model.add_association(ln_substat_assoc)
        #Create a dictionary of LogicalDevices to avoid duplicates. Multiple LNs can exist in the same LD. 
        #if (lnFindAll.attrib['iedName']+ "_"+lnFindAll.attrib['ldInst'] in LDs):
            #Add association between LN and LD
            #dont add the LD again but find it and associate to it.
            #ln_ld_assoc = lang_classes_factory.ns.AppExecution(
            #hostApp = [LDs[lnFindAll.attrib['iedName']+ "_"+lnFindAll.attrib['ldInst']]], appExecutedApps = [lnAsset])
            #instance_model.add_association(ln_ld_assoc)
        #else:     
            #Create the LD asset and add it to the dictionnary
            #ldAsset = lang_classes_factory.ns.LogicalDevice(name = (lnFindAll.attrib['iedName']+ "_"+lnFindAll.attrib['ldInst']))
            #instance_model.add_asset(ldAsset)
            #LDs[(lnFindAll.attrib['iedName']+ "_"+lnFindAll.attrib['ldInst'])] = ldAsset
            #Add association between LN and LD
            #ln_ld_assoc = lang_classes_factory.ns.AppExecution(
            #    hostApp = [ldAsset], appExecutedApps = [lnAsset])
            #instance_model.add_association(ln_ld_assoc)

    #Voltagelevels
    for vlTree in root.iter('{http://www.iec.ch/61850/2003/SCL}VoltageLevel'):
        #Create the Voltage Level asset and add it to the model
        print('Voltage Level: '+ vlTree.attrib['name'])

        #Connect all voltage levels to the substation
        #vl_substat_assoc = lang_classes_factory.ns.SubstatIncludesVL(
        #    voltageLevel = [vlAsset], substation = [substatAsset])  
        #instance_model.add_association(vl_substat_assoc)

        #Bay
        for bayTree in vlTree.iter('{http://www.iec.ch/61850/2003/SCL}Bay'):
            #Create the bay and add it to the model
            print('Bay Name: '+ bayTree.attrib['name'])
          
            #Connect all bays to voltagelevels
            #bay_vl_assoc = lang_classes_factory.ns.VLIncludesBay(
            #    bay = [bayAsset], voltageLevel = [vlAsset])
            #instance_model.add_association(bay_vl_assoc)

            #--------All LNodes on bay level-----------
            for lnIter in bayTree.findall('{http://www.iec.ch/61850/2003/SCL}LNode'):
                #LLN0 does not have an lnInst, in this case we set the value as "0"  
                if (lnIter.attrib['lnClass'] == "LLN0"):
                    lnInstance = "0"
                else:
                    lnInstance = lnIter.attrib['lnInst']
                print('LN bay level: '+ lnIter.attrib['lnClass']+"_"+lnIter.attrib['ldInst']+"_"+lnInstance)

            #-----------------------------------------
            #All conducting equipment for each bay

            for conEq in bayTree.iter('{http://www.iec.ch/61850/2003/SCL}ConductingEquipment'):
                #---------------Circuit breaker-------------------
                if conEq.attrib['type'] == "CBR":
                    print("   circuitBreaker: " + conEq.attrib['name'])
                    #For Circuit breakers, add a ActuatorCB
                    #actCBAsset = lang_classes_factory.ns.ActuatorCB(name = 'CB Actuator')
                    #instance_model.add_asset(actCBAsset)
                    #act_cb_assoc = lang_classes_factory.ns.CloseOrTrip(
                    #actuatorCB = [actCBAsset], circuitBreaker = [eqAsset])
                    #instance_model.add_association(act_cb_assoc)
                #---------------Transformer-------------------
                elif conEq.attrib['type'] == "VTR":
                    print("   transformer: " + conEq.attrib['name'])
                #---------------Other equipment-------------------
                else:
                    print("   conductingEquipment: "+conEq.attrib['name'], conEq.attrib['type'])
#--------------------------------------------------------------

#------------------IED section of the SCD file-----------------
#Not needed?
#--------------------------------------------------------------
