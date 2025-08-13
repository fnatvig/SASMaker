# Setting up the IEC61850ToolChain

- Link to the toolchain: https://github.com/smartgridadsc/IEC61850ToolChain/tree/master
- Link to the toolchain paper: https://ieeexplore.ieee.org/document/9302989
- Based on: https://libiec61850.com/

## Basic
1. Install some sort of linux, e.g. virtualbox with kali linux
2. Clone the repo and update the run.py file, which is missing some parentheses in the print commands.
3. Create a virtual network interface card (VINC) to create interfaces for each IED, Ive used this guide: https://linuxconfig.org/configuring-virtual-network-interfaces-in-linux
```
#enabling dummy kernel module
sudo modprobe dummy
#create a virtual interface
sudo ip link add veth1 type dummy
#give the virtual interface a MAC address
sudo ifconfig veth1 hw ether A2:2E:D6:80:A8:FF
#give the interface an alias and IP address
sudo ip addr add 192.168.1.100/24 brd + dev veth1 label veth1:0
#put the interface up
sudo ip link set dev veth1 up
#create the virtual interface for IED1
sudo ip link add link veth1 address "A2:2E:D6:80:A8:11" veth1.1 type macvlan mode bridge
sudo ifconfig veth1.1 up
#create the virtual interface for IED2
sudo ip link add link veth1 address "A2:2E:D6:80:A8:22" veth1.2 type macvlan mode bridge
sudo ifconfig veth1.2 up
```

4. After these commands the virtual interface is up and running, now we need to edit the files to make the toolchain use this interface for its data
- Update `toolchain/simulationConfiguration.xml` to have only the IEDs that we want the tool to use
- Update `toolchain/IED1/AttackScenarioConfiguration.xml` to reflect the changed interface names from the original (veth1 instead of ens33)
5. The tool is run with `sudo python run.py`

## Making changes
1. Adjusting the type of attack is in the `AttackScenarioConfiguration.xml` file
2. The payload that the IED will send out during normal operations is defined in value.cvs (I think this is what they call the Power System Data Log)
3. 01:0c:cd:01:00:01 is the broadcast address that is being used by the IEDs, which are setup as clients
4. Each IED has a model description file, which is generated from the .iid file. From my understanding the .iid file describes the capability of the specific IED but does not detail how it communicates.
