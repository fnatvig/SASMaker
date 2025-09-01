import sys
import os

print("SASMaker v1.0")
print("Interfaces Setup")
numIEDs = int(input("Number of IEDs: (2-8) "))

print("Enabling dummy kernel module")
os.system ("sudo modprobe dummy")

print("Creating a virtual interface")
os.system ("sudo ip link add veth1 type dummy")

print("Giving the virtual interface a MAC address")
os.system ("sudo ifconfig veth1 hw ether A2:2E:D6:80:A8:FF")

print("Giving the interface an alias and IP address")
os.system ("sudo ip addr add 192.168.1.100/24 brd + dev veth1 label veth1:0")

print("put the interface up")
os.system ("sudo ip link set dev veth1 up")

for x in range (numIEDs):
        ied = x+1
        print("Creating and enabling the virtual interface for IED"+str(ied))
        os.system("sudo ip link add link veth1 address 'A2:2E:D6:80:A8:"+str(ied*11)+"' veth1."+str(ied)+" type macvlan mode bridge")
        os.system("sudo ifconfig veth1."+str(ied)+" up")
