import time
import os
import simulationParser
from multiprocessing import Process
from array import *
milli_sec = int(round(time.time() * 1000000))/1000000
print(milli_sec)

def run_one_toolchain(folder,interface, timestamp, port,duration):
    cmd = 'sudo ./'+folder+'/goose_publisher_toolchain '+interface+' '+str(milli_sec+2)+' '+str(port)+' '+folder+' '+duration
    print (cmd);
    os.system(cmd)

processes = []

#Take input from user in main module
#Hardcoded for now

#Folder where to grab configurations, interface, portnumber, duration
#The folder depends on the IED so one folder per type of IED..
arg1=["SASMaker_IED1", "veth1.1", "102", "60"]
arg2=["SASMaker_IED2", "veth1.2", "103", "60"]
arg3=["SASMaker_IED3", "veth1.3", "104", "60"]

args=[arg1,arg2, arg3]
print (args)

for i in args:
   p = Process(target=run_one_toolchain, args=(i[0], i[1],milli_sec,i[2],i[3]))
   p.start()
   processes.append(p)

for p in processes:
   p.join()
