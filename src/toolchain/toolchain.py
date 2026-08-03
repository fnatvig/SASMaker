import time
import os
import sys
import subprocess
from multiprocessing import Process
from array import *


milli_sec = int(round(time.time() * 1000000))/1000000
print(milli_sec)

def run_one_toolchain(folder,interface, timestamp, port,duration):
    cmd = [
        f"./{folder}/goose_publisher_toolchain",
        interface,
        str(milli_sec + 2),
        str(port),
        folder,
        duration,
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)

processes = []

#Take input from user in main module
#Hardcoded for now

#Folder where to grab configurations, interface, portnumber, duration
#The folder depends on the IED so one folder per type of IED..

# arg1=["SASMaker_IED1", "veth1.1", "102", "20"]
# arg2=["SASMaker_IED2", "veth1.2", "103", "20"]
# arg3=["SASMaker_IED3", "veth1.3", "104", "20"]


# args=[arg1,arg2, arg3]
# print (args)

args = []
i = 1
for arg in sys.argv[1:-1]:
   args.append([arg, f"veth1.{i}", f"{100+i+1}", sys.argv[-1]])
   i+=1


for i in args:
   p = Process(target=run_one_toolchain, args=(i[0], i[1],milli_sec,i[2],i[3]))
   p.start()
   processes.append(p)

for p in processes:
   p.join()

if any(p.exitcode != 0 for p in processes):
   sys.exit(1)
