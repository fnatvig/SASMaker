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


tree = ET.parse('../../test.scd')
root = tree.getroot()

print(root)

for subNetwork in root.iter('{http://www.iec.ch/61850/2003/SCL}SubNetwork'):
    print('Subnetwork: ' + subNetwork.attrib['name'])
    
# Substation name and numIEDs

#family = substation name
#numIEDs = number of IEDs

